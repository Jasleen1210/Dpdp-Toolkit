from datetime import datetime
import re

from backend.services.cloud.mock_cloud_service import (
    get_object_metadata,
    list_cloud_objects,
    read_file,
    write_file,
)
from backend.services.cloud.db import collection, logs_collection
from backend.services.detector import detect_pii_full
from backend.services.pii_summary import build_pii_summary, summarize_pii_instances

def find_matching_records(identifier):
    matches = []
    query = identifier.lower()

    docs = collection.find({})

    for doc in docs:
        matched_values = []
        content = read_file(doc["file"])
        pii_result = detect_pii_full({
            "file": doc["file"],
            "content": content,
        })["pii"]

        for pii in pii_result:
            if query in pii.get("value", "").lower():
                matched_values.append(pii)

        if matched_values or query in content.lower():
            matches.append({
                "file": doc["file"],
                "platform": doc.get("platform", "unknown"),
                "provider": doc.get("provider", "Unknown"),
                "bucket": doc.get("bucket", "unknown"),
                "region": doc.get("region", "unknown"),
                "location": doc.get("location", "unknown"),
                "object_key": doc.get("object_key", doc["file"]),
                "pii": doc.get("pii", {}),
                "matched_values": matched_values,
                "matched_instances": summarize_pii_instances(matched_values),
            })

    return matches

def refresh_file_mapping(path):
    content = read_file(path)
    metadata = get_object_metadata(path)

    pii_result = detect_pii_full({
        "file": path,
        "content": content
    })["pii"]

    collection.update_one(
        {"file": path},
        {
            "$set": {
                **metadata,
                **build_pii_summary(pii_result),
            },
            "$unset": {"detected_values": ""},
        },
        upsert=True
    )

def refresh_all_cloud_mappings():
    cloud_objects = list_cloud_objects()
    current_files = [obj["file"] for obj in cloud_objects]
    collection.delete_many({"file": {"$nin": current_files}})

    for obj in cloud_objects:
        refresh_file_mapping(obj["file"])

def build_request_response(action, identifier, matches, status="SUCCESS", new_value=None):
    pii_type_frequency = {}
    platform_frequency = {}
    location_frequency = {}
    locations = []

    for match in matches:
        platform_frequency[match["provider"]] = platform_frequency.get(match["provider"], 0) + 1
        location_frequency[match["location"]] = location_frequency.get(match["location"], 0) + 1

        for pii_type, present in match.get("pii", {}).items():
            if present:
                pii_type_frequency[pii_type] = pii_type_frequency.get(pii_type, 0) + 1

        locations.append({
            "platform": match["platform"],
            "provider": match["provider"],
            "bucket": match["bucket"],
            "region": match["region"],
            "location": match["location"],
            "object_key": match["object_key"],
            "file": match["file"],
            "matched_instances": match.get("matched_instances", []),
        })

    response = {
        "action": action,
        "identifier": identifier,
        "status": status,
        "message": f"{action.title()} request processed for {identifier}.",
        "locations": locations,
        "stats": {
            "total_locations": len(locations),
            "provider_frequency": platform_frequency,
            "location_frequency": location_frequency,
            "pii_type_frequency": pii_type_frequency,
        },
    }

    if new_value is not None:
        response["new_value"] = new_value

    return response

def replace_query_value(content, identifier, replacement):
    return re.sub(re.escape(identifier), replacement, content, flags=re.IGNORECASE)

def delete_data(identifier):
    refresh_all_cloud_mappings()
    matches = find_matching_records(identifier)

    for m in matches:
        path = m["file"]
        content = read_file(path)

        content = replace_query_value(content, identifier, "[REDACTED]")

        for pii in m["matched_values"]:
            content = content.replace(pii["value"], "[REDACTED]")

        write_file(path, content)
        
        refresh_file_mapping(path)

    logs_collection.insert_one({
        "action": "DELETE",
        "identifier": identifier,
        "files_affected": len(matches),
        "timestamp": datetime.now(),
        "status": "SUCCESS"
    })

    return build_request_response(
        "DELETE",
        identifier,
        matches,
        status="APPROVED_AND_REMOVED",
    )

def access_data(identifier):
    refresh_all_cloud_mappings()
    matches = find_matching_records(identifier)

    logs_collection.insert_one({
        "action": "ACCESS",
        "identifier": identifier,
        "files_affected": len(matches),
        "timestamp": datetime.now(),
        "status": "SUCCESS"
    })

    return build_request_response("ACCESS", identifier, matches)

def update_data(identifier, new_value):
    refresh_all_cloud_mappings()
    matches = find_matching_records(identifier)

    for m in matches:
        path = m["file"]
        content = read_file(path)

        content = replace_query_value(content, identifier, new_value)

        for pii in m["matched_values"]:
            content = content.replace(pii["value"], new_value)

        write_file(path, content)

        refresh_file_mapping(path)

    logs_collection.insert_one({
        "action": "UPDATE",
        "identifier": identifier,
        "files_affected": len(matches),
        "timestamp": datetime.now(),
        "status": "SUCCESS"
    })

    return build_request_response(
        "UPDATE",
        identifier,
        matches,
        new_value=new_value,
    ) | {
        "message": f"Data successfully changed from {identifier} to {new_value} across {len(matches)} cloud location(s)."
    }

def process_request(req):
    identifier = req["identifier"]
    req_type = req["type"].upper()

    if req_type == "DELETE":
        return delete_data(identifier)
    elif req_type == "ACCESS":
        return access_data(identifier)
    elif req_type == "UPDATE":
        if not req.get("new_value"):
            return {"error": "new_value required"}
        return update_data(identifier, req["new_value"])
