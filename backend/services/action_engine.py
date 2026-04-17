from datetime import datetime
from backend.services.cloud.mock_s3_service import list_files, read_file
from backend.services.cloud.db import collection, logs_collection


def find_matching_files(identifier):
    matches = []
    files = list_files()

    for path in files:
        content = read_file(path).lower()
        if identifier.lower() in content:
            matches.append(path)

    return matches


def delete_data(identifier):
    files = find_matching_files(identifier)

    for f in files:
        collection.delete_one({"file": f})

    logs_collection.insert_one({
        "action": "DELETE",
        "identifier": identifier,
        "files_affected": len(files),
        "timestamp": datetime.now(),
        "status": "SUCCESS"
    })

    return len(files)


def access_data(identifier):
    files = find_matching_files(identifier)

    logs_collection.insert_one({
        "action": "ACCESS",
        "identifier": identifier,
        "files_affected": len(files),
        "timestamp": datetime.now(),
        "status": "SUCCESS"
    })

    return files


def update_data(identifier, new_value):
    files = find_matching_files(identifier)

    logs_collection.insert_one({
        "action": "UPDATE",
        "identifier": identifier,
        "files_affected": len(files),
        "timestamp": datetime.now(),
        "status": "SUCCESS"
    })

    return len(files)


def process_request(req):
    identifier = req["identifier"]
    req_type = req["type"]

    if req_type == "DELETE":
        return delete_data(identifier)
    elif req_type == "ACCESS":
        return len(access_data(identifier))
    elif req_type == "UPDATE":
        return update_data(identifier, req.get("new_value"))