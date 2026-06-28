from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from bson import ObjectId

from .auth import _resolve_org_id, _validate_agent_auth, _validate_admin_key
from .helpers import utc_now, _as_utc, _parse_iso_datetime
from .models import (
    CreateTaskRequest,
    SubmitResultRequest,
    StandaloneScanResultRequest,
    CronRunRequest,
    VulnerabilityReportPayload,
    RemediationTaskRequest,
    UserRemediationRequest,
)

from datetime import timezone

from datetime import timezone, datetime

def _iso(dt):
    if not dt:
        return None

    # If it's already an ISO string format, just pass it right back
    if isinstance(dt, str):
        return dt

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.isoformat()

try:
    from services.local.local_db import (
        device_results_collection,
        device_tasks_collection,
        devices_collection,
        device_cron_logs_collection,
        device_vulnerabilities_collection,
    )
except ImportError:
    from backend.services.local.local_db import (
        device_results_collection,
        device_tasks_collection,
        devices_collection,
        device_cron_logs_collection,
        device_vulnerabilities_collection,
    )

router = APIRouter()


def _get_registered_device_or_fail(device_id: str, org_id: str):
    device = devices_collection.find_one(
        {"device_id": device_id, "organisation_id": org_id},
        {"_id": 0},
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not registered")
    if not device.get("approved", False):
        raise HTTPException(status_code=403, detail="Device is not approved")
    return device


@router.post("/tasks")
async def create_distributed_task(
    req: CreateTaskRequest,
    organisation_id: Optional[str] = None,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    expires_at = utc_now() + timedelta(hours=max(1, min(req.expires_in_hours, 24)))
    device_filter = {"organisation_id": org_id, "approved": True}
    if req.device_ids:
        device_filter["device_id"] = {"$in": req.device_ids}

    target_devices = list(devices_collection.find(device_filter, {"_id": 0, "device_id": 1}))
    if not target_devices:
        detail = (
            "No eligible approved devices found for requested device IDs"
            if req.device_ids
            else "No eligible approved devices found"
        )
        raise HTTPException(status_code=400, detail=detail)

    task_group_id = str(uuid4())
    created = []
    for device in target_devices:
        task_id = str(uuid4())
        device_tasks_collection.insert_one({
            "id": task_id,
            "task_group_id": task_group_id,
            "organisation_id": org_id,
            "device_id": device["device_id"],
            "query": req.query,
            "status": "pending",
            "created_at": utc_now(),
            "expires_at": expires_at,
            "completed_at": None,
        })
        created.append({"id": task_id, "device_id": device["device_id"], "expires_at": expires_at})

    return {"task_group_id": task_group_id, "tasks_created": len(created), "tasks": created}


@router.get("/tasks")
async def list_distributed_tasks(
    device_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
    organisation_id: Optional[str] = None,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    query_filter = {"organisation_id": org_id}
    if device_id:
        query_filter["device_id"] = device_id
    if status:
        query_filter["status"] = status

    tasks = list(
        device_tasks_collection.find(query_filter, {"_id": 0})
        .sort("created_at", -1)
        .limit(max(1, min(limit, 1000)))
    )
    if not tasks:
        return {"tasks": []}

    results = list(device_results_collection.find(
        {"task_id": {"$in": [t["id"] for t in tasks]}, "organisation_id": org_id},
        {"_id": 0},
    ))
    result_map = {r["task_id"]: r for r in results}

    merged = []
    for task in tasks:
        result = result_map.get(task["id"])
        matches = result.get("matches", []) if result else []
        merged.append({
            "id": task["id"],
            "task_group_id": task.get("task_group_id"),
            "device_id": task.get("device_id"),
            "query": task.get("query"),
            "paths": task.get("paths", []),
            "status": task.get("status", "pending"),
            "created_at": task.get("created_at"),
            "expires_at": task.get("expires_at"),
            "completed_at": task.get("completed_at"),
            "scanned_files": result.get("scanned_files", 0) if result else 0,
            "matches_count": len(matches),
            "pii_types": sorted({m.get("type", "") for m in matches if m.get("type")}),
            "matches": matches,
        })

    return {"tasks": merged}


@router.get("/devices/tasks")
async def get_device_tasks(
    device_id: str,
    since: Optional[str] = None,
    organisation_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_agent_auth(authorization, org_id)
    _get_registered_device_or_fail(device_id, org_id)

    now = utc_now()

    devices_collection.update_one(
        {"device_id": device_id, "organisation_id": org_id},
        {"$set": {"last_seen": now, "updated_at": now}},
    )

    tasks = list(
        device_tasks_collection.find(
            {
                "device_id": device_id,
                "organisation_id": org_id,
                "status": "pending",
                "expires_at": {"$gt": now},
            },
            {
                "_id": 0,
                "id": 1,
                "query": 1,
                "created_at": 1,
                "expires_at": 1,
                "paths": 1,
                "type": 1,
                "status": 1,
            },
        )
    )

    updates_query = {
        "device_id": device_id,
        "organisation_id": org_id,
    }

    since_dt = _parse_iso_datetime(since)

    if since and not since_dt:
        raise HTTPException(
            status_code=400,
            detail="Invalid since format; expected ISO datetime",
        )

    if since_dt:
        updates_query["updated_at"] = {"$gt": since_dt}

    updates = list(
        device_tasks_collection.find(
            updates_query,
            {
                "_id": 0,
                "id": 1,
                "task_group_id": 1,
                "device_id": 1,
                "status": 1,
                "updated_at": 1,
                "completed_at": 1,
                "expires_at": 1,
            },
        ).sort("updated_at", -1)
    )

    # Convert datetimes to RFC3339 strings with timezone
    for task in tasks:
        task["created_at"] = _iso(task.get("created_at"))
        task["expires_at"] = _iso(task.get("expires_at"))

    for update in updates:
        update["updated_at"] = _iso(update.get("updated_at"))
        update["completed_at"] = _iso(update.get("completed_at"))
        update["expires_at"] = _iso(update.get("expires_at"))

    return {
        "tasks": tasks,
        "updates": updates,
        "has_updates": len(updates) > 0,
        "next_cursor": (
            _iso(updates[0].get("updated_at"))
            if updates
            else _iso(now)
        ),
    }

@router.post("/results")
async def submit_device_result(
    req: SubmitResultRequest,
    organisation_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    # 1. Authenticate the Go Agent and confirm device validation
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_agent_auth(authorization, org_id)
    _get_registered_device_or_fail(req.device_id, org_id)

    # 2. Locate the designated task matching this device execution sequence
    task = device_tasks_collection.find_one(
        {"id": req.task_id, "device_id": req.device_id, "organisation_id": org_id},
        {"_id": 0},
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.get("status") == "completed":
        return {"message": "result already submitted", "task_id": req.task_id}

    # 3. Handle expiration constraints
    expires_at = _as_utc(task.get("expires_at"))
    now = utc_now()
    if expires_at and now > expires_at:
        device_tasks_collection.update_one(
            {"id": req.task_id, "device_id": req.device_id, "organisation_id": org_id},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        raise HTTPException(status_code=410, detail="Task expired")

    # 4. Normalize match payloads cleanly whether they arrive as Pydantic models or raw dict structures
    processed_matches = []
    if req.matches:
        for m in req.matches:
            if hasattr(m, "dict"):
                processed_matches.append(m.dict())
            elif hasattr(m, "model_dump"):
                processed_matches.append(m.model_dump())
            else:
                processed_matches.append(dict(m))

    # 5. Insert scan metadata into the device results tracking collection
    device_results_collection.insert_one({
        "task_id": req.task_id,
        "device_id": req.device_id,
        "organisation_id": org_id,
        "status": req.status,
        "scanned_files": getattr(req, "scanned_files", 0) or len(processed_matches),
        "matches": processed_matches,  # 🔑 This securely drops file paths into your Mongo DB
        "received_at": now,
    })

    # 6. Finalize task workflow transition to completed status
    device_tasks_collection.update_one(
        {"id": req.task_id, "device_id": req.device_id, "organisation_id": org_id},
        {"$set": {
            "status": "completed", 
            "completed_at": now, 
            "updated_at": now
        }},
    )
    
    return {"message": "result accepted", "task_id": req.task_id}

@router.put("/results/latest")
async def upsert_latest_scan_result(
    req: StandaloneScanResultRequest,
    organisation_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_agent_auth(authorization, org_id)
    _get_registered_device_or_fail(req.device_id, org_id)

    result_doc = {
        "device_id": req.device_id,
        "organisation_id": org_id,
        "status": req.status,
        "scanned_files": req.scanned_files,
        "matches": [m.dict() for m in req.matches],
        "result_scope": "standalone",
        "updated_at": utc_now(),
    }
    device_results_collection.update_one(
        {"device_id": req.device_id, "organisation_id": org_id, "result_scope": "standalone"},
        {"$set": result_doc, "$setOnInsert": {"created_at": utc_now()}},
        upsert=True,
    )
    return {"message": "standalone result updated", "device_id": req.device_id}


@router.get("/tasks/{task_group_id}/results")
async def get_task_group_results(
    task_group_id: str,
    organisation_id: Optional[str] = None,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    tasks = list(device_tasks_collection.find(
        {"task_group_id": task_group_id, "organisation_id": org_id}, {"_id": 0}
    ))
    if not tasks:
        raise HTTPException(status_code=404, detail="Task group not found")

    results = list(device_results_collection.find(
        {"task_id": {"$in": [t["id"] for t in tasks]}, "organisation_id": org_id},
        {"_id": 0},
    ))
    return {"task_group_id": task_group_id, "tasks": tasks, "results": results}


@router.post("/devices/cron-runs")
async def register_cron_run(
    req: CronRunRequest,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, None)
    _validate_agent_auth(authorization, org_id)
    _get_registered_device_or_fail(req.device_id, org_id)

    if req.run_id:
        try:
            device_cron_logs_collection.update_one(
                {"_id": ObjectId(req.run_id), "organisation_id": org_id},
                {"$set": {
                    "status": req.status,
                    "duration_elapsed": req.duration,
                    "error_message": req.error,
                    "reported_at": utc_now(),
                }},
            )
            return {"status": "acknowledged", "run_id": req.run_id, "run_status": req.status}
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid run_id format")

    result = device_cron_logs_collection.insert_one({
        "device_id": req.device_id,
        "organisation_id": org_id,
        "task_type": req.task_type,
        "status": req.status,
        "started_at": _as_utc(req.started_at),
        "duration_elapsed": None,
        "error_message": None,
        "reported_at": utc_now(),
    })
    return {"status": "acknowledged", "run_id": str(result.inserted_id), "run_status": req.status}


@router.post("/vulnerabilities/report")
async def report_vulnerabilities(
    payload: VulnerabilityReportPayload,
    organisation_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_agent_auth(authorization, org_id)
    _get_registered_device_or_fail(payload.device_id, org_id)

    vulns = [v.dict() for v in payload.vulnerabilities]
    device_vulnerabilities_collection.update_one(
        {"device_id": payload.device_id, "organisation_id": org_id},
        {"$set": {
            "device_id": payload.device_id,
            "organisation_id": org_id,
            "cron_run_id": payload.cron_run_id,
            "vulnerabilities": vulns,
            "summary": {
                "total_vulnerabilities": len(vulns),
                "total_exposed_matches": sum(v.match_count for v in payload.vulnerabilities),
                "max_priority_score": max((v.priority_score for v in payload.vulnerabilities), default=0.0),
            },
            "updated_at": utc_now(),
        }},
        upsert=True,
    )
    return {"status": "success"}


@router.post("/tasks/remediations")
async def create_modification_task(
    payload: RemediationTaskRequest,
    organisation_id: Optional[str] = None,
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    now = utc_now()

    if payload.action_type == "update":
        if not payload.new_value:
            raise HTTPException(status_code=400, detail="Missing 'new_value' for update task")
        packed_query = f"{payload.target_value}::{payload.new_value}"
    else:
        packed_query = payload.target_value

    task_doc = {
        "id": str(uuid4()),
        "task_group_id": str(uuid4()),
        "organisation_id": org_id,        # ← was hardcoded
        "device_id": payload.device_id,
        "query": packed_query,
        "status": "pending",
        "type": payload.action_type,
        "created_at": now,
        "expires_at": now + timedelta(days=1),
        "updated_at": now,
    }

    device_tasks_collection.insert_one(task_doc)
    return {"status": "task_created", "task_id": task_doc["id"]}
    now = utc_now()

    if payload.action_type == "update":
        if not payload.new_value:
            raise HTTPException(
                status_code=400,
                detail="Missing 'new_value' for update task"
            )
        packed_query = f"{payload.target_value}::{payload.new_value}"

    elif payload.action_type == "delete":
        packed_query = payload.target_value

    elif payload.action_type == "access":
        packed_query = payload.target_value

    task_doc = {
        "id": str(uuid4()),
        "task_group_id": str(uuid4()),
        "organisation_id": "25a30439-8273-4c11-abbf-bb0a5bb689d1",
        "device_id": payload.device_id,
        "query": packed_query,
        "status": "pending",
        "type": payload.action_type,
        "created_at": now,
        "expires_at": now + timedelta(days=1),
        "updated_at": now,
    }
    device_tasks_collection.insert_one(task_doc)
    return {"status": "task_created", "task_id": task_doc["id"]}

@router.get("/vulnerabilities/{device_id}")
async def get_device_vulnerabilities(
    device_id: str,
    organisation_id: Optional[str] = None,
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    doc = device_vulnerabilities_collection.find_one(
        {"device_id": device_id, "organisation_id": org_id},
        {"_id": 0},
    )
    if not doc:
        return {"device_id": device_id, "vulnerabilities": [], "summary": {}}

    return {
        "device_id": device_id,
        "cron_run_id": doc.get("cron_run_id"),
        "summary": doc.get("summary", {}),
        "vulnerabilities": doc.get("vulnerabilities", []),
        "updated_at": doc.get("updated_at"),
    }