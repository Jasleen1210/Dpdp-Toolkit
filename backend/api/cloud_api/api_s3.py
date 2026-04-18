from fastapi import APIRouter
from pydantic import BaseModel

from datetime import datetime

from uuid import uuid4

from backend.services.cloud.mock_s3_service import list_files, read_file
from backend.services.cloud.db import collection, requests_collection, logs_collection
from backend.services.detector import detect_pii_full

from backend.services.action_engine import process_request

router = APIRouter(prefix="/cloud")

# Convert PII → flags
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


@router.get("/requests")
def get_requests():
    data = list(requests_collection.find({}, {"_id": 0}))

    formatted = []

    for r in data:
        formatted.append({
            "id": r["id"],
            "type": r["type"].lower(),
            "subject": r["identifier"],
            "status": r["status"].lower(),
            "sla_remaining": "48h",
            "handler": "auto-system",
            "created": r["created_at"].strftime("%Y-%m-%d")
        })

    return {"requests": formatted}

@router.post("/requests/{request_id}/approve")
async def approve_request(request_id: str):
    req = requests_collection.find_one({"id": request_id})

    if not req:
        return {"error": "Not found"}

    process_request(req)

    requests_collection.update_one(
        {"id": request_id},
        {"$set": {"status": "COMPLETED"}}
    )

    return {"message": "Approved and executed"}

# create a request 
@router.post("/requests")
async def create_request(req: dict):
    new_req = {
        "id": str(uuid4()),
        "type": req["type"],  # DELETE / ACCESS / UPDATE
        "identifier": req["identifier"],
        "status": "PENDING",
        "created_at": datetime.now(),
        "requires_approval": req["type"] == "DELETE"
    }

    requests_collection.insert_one(new_req)

    # Auto process if no approval needed
    if not new_req["requires_approval"]:
        process_request(new_req)
        new_req["status"] = "COMPLETED"
        requests_collection.update_one(
            {"id": new_req["id"]},
            {"$set": {"status": "COMPLETED"}}
        )
    else:
        new_req["status"] = "AWAITING_APPROVAL"
        requests_collection.update_one(
            {"id": new_req["id"]},
            {"$set": {"status": "AWAITING_APPROVAL"}}
        )

    return {"request": new_req}

# Scan entire cloud (mock S3)
@router.post("/scan-cloud")
async def scan_cloud():
    files = list_files()
    results = []

    for path in files:
        content = read_file(path)

        file_data = {
            "file": path,
            "content": content
        }

        pii_result = detect_pii_full(file_data)["pii"]
        pii_flags = get_pii_flags(pii_result)

        doc = {
            "file": path,
            "pii": pii_flags
        }

        # Store in MongoDB (UPSERT)
        collection.update_one(
            {"file": path},
            {"$set": doc},
            upsert=True
        )
        results.append(doc)

    return {
        "message": "Cloud scanned successfully",
        "total_files": len(results),
        "results": results
    }


# Get all scanned results
@router.get("/results")
async def get_results():
    data = list(collection.find({}, {"_id": 0}))
    return {"results": data}


# Search user data (DPDP use-case)
class SearchRequest(BaseModel):
    query: str  # email / phone / name

@router.post("/search")
async def search_data(req: SearchRequest):
    query = req.query.lower()
    matched_files = []

    files = list_files()

    for path in files:
        content = read_file(path).lower()

        if query in content:
            pii_result = detect_pii_full({
                "file": path,
                "content": content
            })["pii"]

            pii_flags = get_pii_flags(pii_result)

            matched_files.append({
                "file": path,
                "pii": pii_flags
            })

    return {
        "query": req.query,
        "matches": matched_files
    }

# Health check
@router.get("/")
async def root():
    return {"status": "Backend running smoothly!"}

# ACTION ENGINE
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

    # simulate delete (remove from DB only for now)
    for f in files:
        collection.delete_one({"file": f})

    logs_collection.insert_one({
        "request_type": "DELETE",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return len(files)


def access_data(identifier):
    files = find_matching_files(identifier)

    logs_collection.insert_one({
        "request_type": "ACCESS",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return files


def update_data(identifier, new_value):
    files = find_matching_files(identifier)

    # simulate update (just log for now)
    logs_collection.insert_one({
        "request_type": "UPDATE",
        "user": identifier,
        "files_affected": len(files),
        "status": "success"
    })

    return len(files)

# Logs
@router.get("/logs")
async def get_logs():
    logs = list(logs_collection.find({}, {"_id": 0}))
    return {"logs": logs}