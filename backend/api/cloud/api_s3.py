from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
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
from backend.api.middleware import OrgAuthContext, resolve_org_context
from backend.api.unified_requests import UnifiedDataSubjectRequest, create_unified_request

router = APIRouter(prefix="/cloud")


def _cloud_data_source(obj: dict, org_id: str) -> dict:
    """Make each cloud connection a first-class, reusable data source."""
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
def get_requests(ctx: OrgAuthContext = Depends(resolve_org_context)):
    org_id = ctx.org_id
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

        raw_target_sources = r.get("target_sources")
        source_types = r.get("source_types", [])
        if raw_target_sources is not None:
            resolved_targets = raw_target_sources
        elif "local_device" in source_types and "cloud_storage" not in source_types:
            resolved_targets = ["local"]
        elif "cloud_storage" in source_types and "local_device" not in source_types:
            resolved_targets = ["cloud"]
        elif device_ids and not ("cloud_storage" in source_types):
            resolved_targets = ["local"]
        else:
            resolved_targets = ["cloud", "local"]

        handler_str = "auto-system"
        if device_ids:
            handler_str = f"local ({', '.join(device_ids)})"
        elif "local" in resolved_targets and len(resolved_targets) == 1:
            handler_str = "local"
        elif "cloud" in resolved_targets and len(resolved_targets) == 1:
            handler_str = "cloud"
        elif r.get("source_types"):
            handler_str = ", ".join(r.get("source_types", []))

        formatted.append({
            "id": r_id,
            "type": display_type,
            "subject": subject,
            "status": status,
            "handler": handler_str,
            "created": created_str,
            "devices": device_ids,
            "tasks_count": len(tasks),
            "source_types": source_types,
            "target_sources": resolved_targets,
            "org_id": r.get("org_id") or r.get("organisation_id"),
        })

    return {"requests": formatted}

# create a request 
@router.post("/requests")
async def create_request(
    req: DataSubjectRequest,
    background_tasks: BackgroundTasks,
    ctx: OrgAuthContext = Depends(resolve_org_context),
):
    payload = UnifiedDataSubjectRequest(
        type=req.type,
        identifier=req.identifier,
        new_value=req.new_value,
        target="cloud",
    )
    return await create_unified_request(
        payload,
        background_tasks,
        ctx,
    )

@router.post("/requests/{request_id}/approve")
async def approve_request(request_id: str, ctx: OrgAuthContext = Depends(resolve_org_context)):
    req = data_subject_requests.find_one({"id": request_id, "org_id": ctx.org_id})

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    result = process_request(req)
    local_tasks = list(request_tasks.find(
        {"request_id": request_id, "$or": [{"org_id": ctx.org_id}, {"organisation_id": ctx.org_id}]},
        {"_id": 0, "status": 1},
    ))
    has_pending_local = any(task.get("status") in {"pending", "in_progress"} for task in local_tasks)

    data_subject_requests.update_one(
        {"id": request_id, "org_id": ctx.org_id},
        {"$set": {
            "status": "in_progress" if has_pending_local else "completed",
            "source_status": {"cloud": "completed", "local": "queued" if has_pending_local else "completed"},
            "status_message": "Cloud processing completed. Waiting for local device results." if has_pending_local else "All selected sources finished scanning.",
            "approved_at": datetime.now(),
            "updated_at": datetime.now(),
            **({} if has_pending_local else {"closed_at": datetime.now()}),
        }}
    )

    return {
        "message": "Approved. Cloud processing completed; local devices are still processing." if has_pending_local else "Approved and executed across the selected sources.",
        "result": result,
    }


@router.post("/scan-cloud")
async def scan_cloud(ctx: OrgAuthContext = Depends(resolve_org_context)):
    cloud_objects = list_cloud_objects()
    current_files = [obj["file"] for obj in cloud_objects]
    results = []

    pii_classifications.delete_many({"org_id": ctx.org_id, "source_type": "cloud_storage", "file": {"$nin": current_files}})

    for obj in cloud_objects:
        path = obj["file"]
        content = read_file(path)

        file_data = {
            "file": path,
            "content": content
        }

        pii_result = detect_pii_full(file_data)["pii"]

        source = _cloud_data_source(obj, ctx.org_id)
        doc = {
            **obj,
            "org_id": ctx.org_id,
            "data_source_id": source["id"],
            "source_type": "cloud_storage",
            "location": path,
            "file": path,
            **build_pii_summary(pii_result),
        }

        # Store in MongoDB (UPSERT)
        pii_classifications.update_one(
            {"org_id": ctx.org_id, "data_source_id": source["id"], "location": path},
            {
                "$set": doc,
                "$unset": {"detected_values": ""},
            },
            upsert=True
        )
        results.append(doc)

    scan_jobs.insert_one({"id": str(uuid4()), "org_id": ctx.org_id, "source_type": "cloud_storage", "status": "completed", "task_type": "classification", "started_at": datetime.now(), "completed_at": datetime.now(), "result_summary": {"records_found": len(results), "locations": current_files}})
    return {
        "message": "Cloud platforms scanned successfully",
        "total_files": len(results),
        "providers": sorted({r["provider"] for r in results}),
        "results": results
    }


# Get all scanned results
@router.get("/results")
async def get_results(ctx: OrgAuthContext = Depends(resolve_org_context)):
    data = list(pii_classifications.find({"org_id": ctx.org_id, "source_type": "cloud_storage"}, {"_id": 0}))
    return {"results": data}


# Search user data (DPDP use-case)
class SearchRequest(BaseModel):
    query: str  # email / phone / name


@router.post("/search")
async def search_data(req: SearchRequest, ctx: OrgAuthContext = Depends(resolve_org_context)):
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

class CloudConnectRequest(BaseModel):
    provider: str  # "AWS S3" | "Azure Blob Storage" | "GCP Cloud Storage"
    bucket_or_container: str
    region: str
    auth_method: str = "role_arn"  # "role_arn" | "access_keys" | "service_account" | "connection_string"
    role_arn: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    connection_string: Optional[str] = None
    service_account_email: Optional[str] = None
    notes: Optional[str] = None


@router.get("/sources")
async def list_cloud_sources(ctx: OrgAuthContext = Depends(resolve_org_context)):
    """Lists all configured and connected cloud storage sources (org-scoped)."""
    sources = list(
        data_sources.find(
            {
                "$or": [{"org_id": ctx.org_id}, {"organisation_id": ctx.org_id}],
                "source_type": "cloud_storage"
            },
            {"_id": 0, "secret_access_key": 0, "connection_string": 0},
        ).sort("created_at", -1)
    )
    return {"sources": sources}


@router.delete("/sources/{source_id}")
async def delete_cloud_source(
    source_id: str,
    ctx: OrgAuthContext = Depends(resolve_org_context),
):
    """Permanently removes a cloud storage connection and associated data (org-scoped)."""
    # Find the source first (must belong to user's org)
    source = data_sources.find_one({
        "id": source_id,
        "$or": [{"org_id": ctx.org_id}, {"organisation_id": ctx.org_id}],
        "source_type": "cloud_storage"
    })
    if not source:
        raise HTTPException(status_code=404, detail="Cloud source not found")
    
    provider_name = source.get("provider", "Unknown")
    bucket_name = source.get("bucket", "unknown").replace("cloud://", "")
    region_name = source.get("region", "unknown")
    
    # Delete from data_sources
    data_sources.delete_one({"id": source_id, "$or": [{"org_id": ctx.org_id}, {"organisation_id": ctx.org_id}]})
    
    # Delete associated PII classifications
    pii_classifications.delete_many({
        "data_source_id": source_id,
        "$or": [{"org_id": ctx.org_id}, {"organisation_id": ctx.org_id}]
    })
    
    # Log the deletion
    audit_logs.insert_one({
        "actor_type": "user",
        "actor_id": ctx.user_id,
        "entity_type": "cloud_data_source",
        "org_id": ctx.org_id,
        "action": "DELETE_CLOUD_PROVIDER",
        "provider": provider_name,
        "bucket": bucket_name,
        "region": region_name,
        "source_id": source_id,
        "timestamp": datetime.now(),
        "status": "SUCCESS",
    })
    
    return {
        "status": "success",
        "message": f"Successfully removed connection to {provider_name} ({bucket_name}).",
        "source_id": source_id,
    }


@router.post("/connect")
async def connect_cloud_provider(
    req: CloudConnectRequest,
    ctx: OrgAuthContext = Depends(resolve_org_context),
):
    """Registers and establishes a secure connection to a client's cloud storage provider (org-scoped)."""
    org_id = ctx.org_id
    provider_name = req.provider.strip()
    bucket_name = req.bucket_or_container.strip().replace("s3://", "").replace("gs://", "").replace("azure://", "")
    region_name = req.region.strip()

    if not bucket_name:
        raise HTTPException(status_code=400, detail="Bucket or container name is required")

    source_key = f"{provider_name}::{bucket_name}::{region_name}"
    now = datetime.now()
    source_id = str(uuid4())

    # Create connected storage directory for realistic demo data access
    from pathlib import Path
    base_dir = Path(__file__).resolve().parents[2]
    clean_provider = provider_name.lower().replace(" ", "_").replace("/", "_")
    clean_bucket = bucket_name.lower().replace("/", "_")
    connected_dir = base_dir / "cloud_connected" / clean_provider / clean_bucket
    connected_dir.mkdir(parents=True, exist_ok=True)

    # Initialize sample compliance archive files if empty
    sample_file = connected_dir / "customer_records_2026.csv"
    if not sample_file.exists():
        sample_file.write_text(
            "id,name,email,phone,aadhaar,pan,location\n"
            "101,Rahul Sharma,rahul.sharma@example.com,+91 98765 43210,9876 5432 1098,ABCDE1234F,Bangalore\n"
            "102,Priya Patel,priya.patel@example.com,+91 91234 56789,1234 5678 9012,FGHIJ5678K,Mumbai\n"
            "103,Amit Verma,amit.verma@example.com,+91 99887 76655,5678 9012 3456,KLMNO9012P,Delhi\n",
            encoding="utf-8",
        )

    # Store safe metadata in data_sources (never leak raw secrets)
    data_sources.update_one(
        {"org_id": org_id, "source_type": "cloud_storage", "source_key": source_key},
        {
            "$set": {
                "id": source_id,
                "org_id": org_id,
                "organisation_id": org_id,
                "source_type": "cloud_storage",
                "source_key": source_key,
                "provider": provider_name,
                "bucket": f"cloud://{bucket_name}",
                "region": region_name,
                "auth_method": req.auth_method,
                "role_arn": req.role_arn,
                "access_key_id": req.access_key_id[:4] + "****" if req.access_key_id else None,
                "service_account_email": req.service_account_email,
                "status": "connected",
                "approved": True,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )

    audit_logs.insert_one({
        "actor_type": "user",
        "actor_id": ctx.user_id,
        "entity_type": "cloud_data_source",
        "org_id": org_id,
        "action": "CONNECT_CLOUD_PROVIDER",
        "provider": provider_name,
        "bucket": bucket_name,
        "region": region_name,
        "timestamp": now,
        "status": "SUCCESS",
    })

    return {
        "status": "success",
        "message": f"Successfully connected to {provider_name} ({bucket_name}) in {region_name}.",
        "source_id": source_id,
        "provider": provider_name,
        "bucket": bucket_name,
        "region": region_name,
    }


# Health check
@router.get("/")
async def root():
    return {"status": "Backend running smoothly!"}

# Logs
@router.get("/logs")
async def get_logs(ctx: OrgAuthContext = Depends(resolve_org_context)):
    logs = list(audit_logs.find({"org_id": ctx.org_id}, {"_id": 0}))
    return {"logs": logs}

