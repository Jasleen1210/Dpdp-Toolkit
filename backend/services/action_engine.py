from datetime import datetime
from backend.services.cloud.mock_s3_service import list_files, read_file
from backend.services.cloud.db import collection, logs_collection
from backend.services.detector import detect_pii_full

def get_pii_flags(pii_result):
    pii_flags = {
        "Name": False,
        "Phone": False,
        "Email": False,
        "Credit Card": False,
        "Aadhaar": False,
        "PAN": False,
        "IP Address": False
    }

    for item in pii_result:
        pii_flags[item["type"]] = True

    return pii_flags

def find_matching_records(identifier):
    matches = []

    docs = collection.find({})

    for doc in docs:
        matched_values = []

        for pii in doc.get("detected_values", []):
            if pii["value"].lower() == identifier.lower():
                matched_values.append(pii)

        if matched_values:
            matches.append({
                "file": doc["file"],
                "pii": doc["pii"],
                "matched_values": matched_values
            })

    return matches

def refresh_file_mapping(path):
    content = read_file(path)

    pii_result = detect_pii_full({
        "file": path,
        "content": content
    })["pii"]

    collection.update_one(
        {"file": path},
        {
            "$set": {
                "pii": get_pii_flags(pii_result),
                "detected_values": pii_result
            }
        }
    )

def delete_data(identifier):
    matches = find_matching_records(identifier)

    for m in matches:
        path = m["file"]
        content = read_file(path)

        for pii in m["matched_values"]:
            content = content.replace(pii["value"], "[REDACTED]")

        with open(path, "w") as f:
            f.write(content)
        
        refresh_file_mapping(path)

    logs_collection.insert_one({
        "action": "DELETE",
        "identifier": identifier,
        "files_affected": len(matches),
        "timestamp": datetime.now(),
        "status": "SUCCESS"
    })

    return matches

def access_data(identifier):
    matches = find_matching_records(identifier)

    logs_collection.insert_one({
        "action": "ACCESS",
        "identifier": identifier,
        "files_affected": len(matches),
        "timestamp": datetime.now(),
        "status": "SUCCESS"
    })

    return matches

def update_data(identifier, new_value):
    matches = find_matching_records(identifier)

    for m in matches:
        path = m["file"]
        content = read_file(path)

        for pii in m["matched_values"]:
            content = content.replace(pii["value"], new_value)

        with open(path, "w") as f:
            f.write(content)

        refresh_file_mapping(path)
    return matches

def process_request(req):
    identifier = req["identifier"]
    req_type = req["type"]

    if req_type == "DELETE":
        return delete_data(identifier)
    elif req_type == "ACCESS":
        return access_data(identifier)
    elif req_type == "UPDATE":
        if not req.get("new_value"):
            return {"error": "new_value required"}
        return update_data(identifier, req["new_value"])