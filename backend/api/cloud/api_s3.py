from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from datetime import datetime, timedelta

from uuid import uuid4

from backend.services.cloud_storage.cloud_service import list_cloud_objects, read_file
from backend.services.persistence.mongo import (
    audit_logs,
    data_sources,
    data_subject_requests,
    pii_classifications,
    request_tasks,
    scan_jobs,
)
from backend.services.pii_detection import detect_pii_full
from backend.services.pii import build_pii_summary

from backend.services.remediation import process_request

router = APIRouter(prefix="/cloud")


def _cloud_org_id() -> str:
    """Cloud routes are currently service-authenticated; retain the configured org scope."""
    import os

    return os.getenv("ORG_ID", "dpdp-org").strip() or "dpdp-org"


def _cloud_data_source(obj: dict) -> dict:
    """Make each cloud connection a first-class, reusable data source."""
    org_id = _cloud_org_id()
    source_key = "::".join(str(obj.get(key, "")) for key in ("provider", "bucket", "region"))
    now = datetime.now()
    data_sources.update_one(
        {"org_id": org_id, "source_type": "cloud_storage", "source_key": source_key},
        {"$set": {"org_id": org_id, "organisation_id": org_id, "source_type": "cloud_storage", "source_key": source_key,
                  "provider": obj.get("provider"), "bucket": obj.get("bucket"), "region": obj.get("region"), "updated_at": now},
         "$setOnInsert": {"id": str(uuid4()), "created_at": now, "approved": True}},
        upsert=True,
    )
    return data_sources.find_one({"org_id": org_id, "source_type": "cloud_storage", "source_key": source_key}, {"_id": 0})


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
    org_id = _cloud_org_id()
    data = list(data_subject_requests.find({"$or": [{"org_id": org_id}, {"organisation_id": org_id}]}, {"_id": 0}).sort("created_at", -1))

    formatted = []

    for r in data:
        r_id = r.get("id")
        if not r_id:
            continue
        tasks = list(request_tasks.find({"request_id": r_id}, {"_id": 0}))
        device_ids = [t.get("device_id") for t in tasks if t.get("device_id")]

        subject = (
            r.get("identifier")
            or (r.get("data_principal", {}) or {}).get("identifier_hash")
            or (r.get("data_principal", {}) or {}).get("email")
            or "Unknown"
        )

        raw_type = (r.get("type") or r.get("request_type") or "access").lower()
        type_mapping = {"correction": "update", "erasure": "delete"}
        display_type = type_mapping.get(raw_type, raw_type)

        status = r.get("status", "pending").lower()
        if tasks:
            all_done = all(t.get("status") == "completed" for t in tasks)
            if all_done and status not in ("awaiting_approval", "rejected"):
                status = "completed"
            elif any(t.get("status") == "in_progress" for t in tasks):
                status = "in_progress"

        created_val = r.get("created_at")
        created_str = (
            created_val.strftime("%Y-%m-%d")
            if hasattr(created_val, "strftime")
            else str(created_val)[:10] if created_val else "-"
        )

        handler_str = "auto-system"
        if device_ids:
            handler_str = f"local ({', '.join(device_ids)})"
        elif r.get("source_types"):
            handler_str = ", ".join(r.get("source_types", []))

        formatted.append({
            "id": r_id,
            "type": display_type,
            "subject": subject,
            "status": status,
            "sla_remaining": "48h",
            "handler": handler_str,
            "created": created_str,
            "devices": device_ids,
            "tasks_count": len(tasks),
            "source_types": r.get("source_types", ["local_device" if device_ids else "cloud_storage"]),
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

    canonical_type = {"ACCESS": "access", "UPDATE": "correction", "DELETE": "erasure"}[request_type]
    now = datetime.now()
    new_req = {
        "id": str(uuid4()),
        "org_id": _cloud_org_id(),
        "request_type": canonical_type,
        "data_principal": {"identifier_hash": req.identifier.lower()},
        "verification_status": "verified",
        "submitted_via": "api",
        "type": request_type,
        "identifier": req.identifier,
        "new_value": req.new_value,
        "status": "PENDING",
        "created_at": now,
        "updated_at": now,
        "sla_due_at": now + timedelta(days=30),
        "requires_approval": request_type == "DELETE"
    }

    data_subject_requests.insert_one(new_req)

    new_req.pop("_id", None)
    result = None
    if not new_req["requires_approval"]:
        result = process_request(new_req)
        new_req["status"] = "COMPLETED"
        data_subject_requests.update_one(
            {"id": new_req["id"]},
            {"$set": {"status": "COMPLETED"}}
        )
    else:
        new_req["status"] = "AWAITING_APPROVAL"
        data_subject_requests.update_one(
            {"id": new_req["id"]},
            {"$set": {"status": "AWAITING_APPROVAL"}}
        )
        result = {
            "action": "DELETE",
            "identifier": new_req["identifier"],
            "status": "AWAITING_APPROVAL",
            "message": "Delete request has been submitted and is awaiting approval. It will be processed within 24-48 hours.",
        }

    return {"request": new_req, "result": result }

@router.post("/requests/{request_id}/approve")
async def approve_request(request_id: str):
    req = data_subject_requests.find_one({"id": request_id, "org_id": _cloud_org_id()})

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    result = process_request(req)

    data_subject_requests.update_one(
        {"id": request_id, "org_id": _cloud_org_id()},
        {"$set": {"status": "COMPLETED", "approved_at": datetime.now(), "updated_at": datetime.now(), "closed_at": datetime.now()}}
    )

    return {
        "message": "Approved and executed. Matching data was removed from cloud locations.",
        "result": result,
    }


@router.post("/scan-cloud")
async def scan_cloud():
    cloud_objects = list_cloud_objects()
    current_files = [obj["file"] for obj in cloud_objects]
    results = []

    pii_classifications.delete_many({"org_id": _cloud_org_id(), "source_type": "cloud_storage", "file": {"$nin": current_files}})

    for obj in cloud_objects:
        path = obj["file"]
        content = read_file(path)

        file_data = {
            "file": path,
            "content": content
        }

        pii_result = detect_pii_full(file_data)["pii"]

        source = _cloud_data_source(obj)
        doc = {
            **obj,
            "org_id": _cloud_org_id(),
            "data_source_id": source["id"],
            "source_type": "cloud_storage",
            "location": path,
            "file": path,
            **build_pii_summary(pii_result),
        }

        # Store in MongoDB (UPSERT)
        pii_classifications.update_one(
            {"org_id": _cloud_org_id(), "data_source_id": source["id"], "location": path},
            {
                "$set": doc,
                "$unset": {"detected_values": ""},
            },
            upsert=True
        )
        results.append(doc)

    scan_jobs.insert_one({"id": str(uuid4()), "org_id": _cloud_org_id(), "source_type": "cloud_storage", "status": "completed", "task_type": "classification", "started_at": datetime.now(), "completed_at": datetime.now(), "result_summary": {"records_found": len(results), "locations": current_files}})
    return {
        "message": "Cloud platforms scanned successfully",
        "total_files": len(results),
        "providers": sorted({r["provider"] for r in results}),
        "results": results
    }


# Get all scanned results
@router.get("/results")
async def get_results():
    data = list(pii_classifications.find({"org_id": _cloud_org_id(), "source_type": "cloud_storage"}, {"_id": 0}))
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
    logs = list(audit_logs.find({}, {"_id": 0}))
    return {"logs": logs}
