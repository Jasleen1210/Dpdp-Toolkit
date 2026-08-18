from datetime import datetime
import os
import re

from backend.services.cloud_storage.cloud_service import (
    get_object_metadata,
    list_cloud_objects,
    read_file,
    write_file,
)
from backend.services.persistence.mongo import audit_logs, pii_classifications
from backend.services.pii_detection import detect_pii_full
from backend.services.pii import build_pii_summary, summarize_pii_instances


def find_matching_records(identifier):
    matches = []
    query = identifier.strip().lower()
    if not query:
        return []

    # Get all cloud objects across AWS, Azure, GCP, and connected storage
    cloud_objs = list_cloud_objects()
    seen_files = set()

    # Extract digits for flexible phone number matching
    query_digits = re.sub(r"\D", "", query)
    is_phone_query = len(query_digits) >= 10

    for obj in cloud_objs:
        file_path = obj.get("file")
        if not file_path or file_path in seen_files:
            continue
        seen_files.add(file_path)

        try:
            content = read_file(file_path)
        except Exception:
            continue

        if not content:
            continue

        content_lower = content.lower()
        matched = False

        if query in content_lower:
            matched = True
        elif is_phone_query:
            content_digits = re.sub(r"\D", "", content_lower)
            if query_digits in content_digits:
                matched = True

        if matched:
            matches.append({
                "file": file_path,
                "platform": obj.get("platform", "cloud"),
                "provider": obj.get("provider", "AWS"),
                "bucket": obj.get("bucket", "unknown"),
                "region": obj.get("region", "global"),
                "location": obj.get("location", file_path),
                "object_key": obj.get("object_key", file_path),
                "pii": obj.get("pii", {"PII": True}),
                "matched_values": [{"type": "PII", "value": identifier}],
                "matched_instances": {"PII": 1},
            })

    return matches


def refresh_file_mapping(path):
    try:
        content = read_file(path)
        metadata = get_object_metadata(path)

        pii_result = detect_pii_full({
            "file": path,
            "content": content,
        })["pii"]

        pii_classifications.update_one(
            {"file": path},
            {
                "$set": {
                    **metadata,
                    **build_pii_summary(pii_result),
                },
                "$unset": {"detected_values": ""},
            },
            upsert=True,
        )
    except Exception:
        pass


def refresh_all_cloud_mappings():
    try:
        cloud_objects = list_cloud_objects()
        current_files = [obj["file"] for obj in cloud_objects]
        pii_classifications.delete_many({"source_type": "cloud_storage", "file": {"$nin": current_files}})
        for obj in cloud_objects:
            refresh_file_mapping(obj["file"])
    except Exception:
        pass


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
    # Direct replacement
    new_content = re.sub(re.escape(identifier), replacement, content, flags=re.IGNORECASE)
    
    # If phone number with spaces/hyphens, also replace common spacing variants
    digits = re.sub(r"\D", "", identifier)
    if len(digits) >= 10:
        # Match standard patterns like +91 98765 43210, 98765-43210, 9876543210
        pattern = r"(?:\+91[\s\-]?)?" + r"[\s\-]?".join(list(digits[-10:]))
        new_content = re.sub(pattern, replacement, new_content, flags=re.IGNORECASE)

    return new_content


def delete_data(identifier):
    matches = find_matching_records(identifier)

    for m in matches:
        path = m["file"]
        content = read_file(path)

        content = replace_query_value(content, identifier, "[REDACTED]")

        for pii in m.get("matched_values", []):
            if pii.get("value"):
                content = content.replace(pii["value"], "[REDACTED]")

        write_file(path, content)
        refresh_file_mapping(path)

    audit_logs.insert_one({
        "actor_type": "system",
        "actor_id": "cloud-action-engine",
        "entity_type": "data_subject_request",
        "org_id": os.environ.get("ORG_ID", "dpdp-org"),
        "action": "DELETE",
        "identifier": identifier,
        "files_affected": len(matches),
        "timestamp": datetime.now(),
        "status": "SUCCESS",
    })

    return build_request_response(
        "DELETE",
        identifier,
        matches,
        status="APPROVED_AND_REMOVED",
    )


def access_data(identifier):
    matches = find_matching_records(identifier)

    audit_logs.insert_one({
        "actor_type": "system",
        "actor_id": "cloud-action-engine",
        "entity_type": "data_subject_request",
        "org_id": os.environ.get("ORG_ID", "dpdp-org"),
        "action": "ACCESS",
        "identifier": identifier,
        "files_affected": len(matches),
        "timestamp": datetime.now(),
        "status": "SUCCESS",
    })

    return build_request_response("ACCESS", identifier, matches)


def update_data(identifier, new_value):
    matches = find_matching_records(identifier)

    for m in matches:
        path = m["file"]
        content = read_file(path)

        content = replace_query_value(content, identifier, new_value)

        for pii in m.get("matched_values", []):
            if pii.get("value"):
                content = content.replace(pii["value"], new_value)

        write_file(path, content)
        refresh_file_mapping(path)

    audit_logs.insert_one({
        "actor_type": "system",
        "actor_id": "cloud-action-engine",
        "entity_type": "data_subject_request",
        "org_id": os.environ.get("ORG_ID", "dpdp-org"),
        "action": "UPDATE",
        "identifier": identifier,
        "files_affected": len(matches),
        "timestamp": datetime.now(),
        "status": "SUCCESS",
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
    identifier = req.get("identifier", "")
    raw_type = str(req.get("type") or req.get("request_type") or "ACCESS").upper()

    if raw_type in ("DELETE", "ERASURE"):
        return delete_data(identifier)
    elif raw_type in ("ACCESS",):
        return access_data(identifier)
    elif raw_type in ("UPDATE", "CORRECTION"):
        new_val = req.get("new_value")
        if not new_val:
            return {"error": "new_value required for update"}
        return update_data(identifier, new_val)
    return {"error": f"Unknown request type {raw_type}"}
