from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from datetime import datetime

from uuid import uuid4

from backend.services.cloud.mock_cloud_service import list_cloud_objects, read_file
from backend.services.cloud.db import collection, requests_collection, logs_collection
from backend.services.detector import detect_pii_full
from backend.services.pii_summary import build_pii_summary

from backend.services.action_engine import process_request

router = APIRouter(prefix="/cloud")


class DataSubjectRequest(BaseModel):
    type: str
    identifier: str
    new_value: Optional[str] = None

# Convert PII → flags
def build_match_summary(matches):
    provider_frequency = {}
    location_frequency = {}
    pii_type_frequency = {}

    for match in matches:
        provider = match.get("provider", "Unknown")
        location = match.get("location", "unknown")
        provider_frequency[provider] = provider_frequency.get(provider, 0) + 1
        location_frequency[location] = location_frequency.get(location, 0) + 1

        for pii_type, present in match.get("pii", {}).items():
            if present:
                pii_type_frequency[pii_type] = pii_type_frequency.get(pii_type, 0) + 1

    return {
        "total_locations": len(matches),
        "provider_frequency": provider_frequency,
        "location_frequency": location_frequency,
        "pii_type_frequency": pii_type_frequency,
    }

@router.get("/requests")
def get_requests():
    data = list(requests_collection.find({}, {"_id": 0}).sort("created_at", -1))

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

# create a request 
@router.post("/requests")
async def create_request(req: DataSubjectRequest):
    request_type = req.type.upper()
    if request_type not in {"ACCESS", "UPDATE", "DELETE"}:
        raise HTTPException(
            status_code=400,
            detail="type must be one of ACCESS, UPDATE, or DELETE",
        )

    if request_type == "UPDATE" and not req.new_value:
        raise HTTPException(
            status_code=400,
            detail="new_value is required for UPDATE requests",
        )

    new_req = {
        "id": str(uuid4()),
        "type": request_type,
        "identifier": req.identifier,
        "new_value": req.new_value,
        "status": "PENDING",
        "created_at": datetime.now(),
        "requires_approval": request_type == "DELETE"
    }

    requests_collection.insert_one(new_req)

    new_req.pop("_id", None)
    result = None
    if not new_req["requires_approval"]:
        result = process_request(new_req)
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
        result = {
            "action": "DELETE",
            "identifier": new_req["identifier"],
            "status": "AWAITING_APPROVAL",
            "message": "Delete request is awaiting approval. Data remains in its cloud locations until approval is completed.",
        }

    return {"request": new_req, "result": result }

@router.post("/requests/{request_id}/approve")
async def approve_request(request_id: str):
    req = requests_collection.find_one({"id": request_id})

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    result = process_request(req)

    requests_collection.update_one(
        {"id": request_id},
        {"$set": {"status": "COMPLETED", "approved_at": datetime.now()}}
    )

    return {
        "message": "Approved and executed. Matching data was removed from cloud locations.",
        "result": result,
    }


# Scan entire cloud (mock S3)
@router.post("/scan-cloud")
async def scan_cloud():
    cloud_objects = list_cloud_objects()
    current_files = [obj["file"] for obj in cloud_objects]
    results = []

    collection.delete_many({"file": {"$nin": current_files}})

    for obj in cloud_objects:
        path = obj["file"]
        content = read_file(path)

        file_data = {
            "file": path,
            "content": content
        }

        pii_result = detect_pii_full(file_data)["pii"]

        doc = {
            **obj,
            "file": path,
            **build_pii_summary(pii_result),
        }

        # Store in MongoDB (UPSERT)
        collection.update_one(
            {"file": path},
            {
                "$set": doc,
                "$unset": {"detected_values": ""},
            },
            upsert=True
        )
        results.append(doc)

    return {
        "message": "Cloud platforms scanned successfully",
        "total_files": len(results),
        "providers": sorted({r["provider"] for r in results}),
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

    cloud_objects = list_cloud_objects()

    for obj in cloud_objects:
        path = obj["file"]
        content = read_file(path).lower()

        if query in content:
            pii_result = detect_pii_full({
                "file": path,
                "content": content
            })["pii"]

            matched_files.append({
                **obj,
                "file": path,
                **build_pii_summary(pii_result),
            })

    return {
        "query": req.query,
        "locations": matched_files,
        "stats": build_match_summary(matched_files),
        "matches": matched_files
    }

# Health check
@router.get("/")
async def root():
    return {"status": "Backend running smoothly!"}

# Logs
@router.get("/logs")
async def get_logs():
    logs = list(logs_collection.find({}, {"_id": 0}))
    return {"logs": logs}
