from db import files_collection, logs_collection

def find_user_files(identifier):
    return list(files_collection.find({
        "pii_values": identifier
    }))

def delete_data(identifier):
    files = find_user_files(identifier)

    for f in files:
        # simulate delete (remove from DB)
        files_collection.delete_one({"_id": f["_id"]})

    logs_collection.insert_one({
        "request_type": "DELETE",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return len(files)


def access_data(identifier):
    files = find_user_files(identifier)

    logs_collection.insert_one({
        "request_type": "ACCESS",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return files


def update_data(identifier, new_value):
    files = find_user_files(identifier)

    for f in files:
        updated_values = [
            new_value if v == identifier else v
            for v in f["pii_values"]
        ]

        files_collection.update_one(
            {"_id": f["_id"]},
            {"$set": {"pii_values": updated_values}}
        )

    logs_collection.insert_one({
        "request_type": "UPDATE",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return len(files)