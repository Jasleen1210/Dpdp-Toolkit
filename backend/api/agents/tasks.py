from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
 
from fastapi import APIRouter, Header, HTTPException
 
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
from backend.services.persistence.mongo import (
    data_source_vulnerabilities as device_vulnerabilities_collection,
    data_sources as devices_collection,
    data_subject_requests,
    pii_classifications as device_results_collection,
    redaction_records as device_delete_redactions_collection,
    request_tasks as device_tasks_collection,
    agent_cron_runs as device_cron_runs_collection,
    agent_cron_run_vulnerabilities as cron_run_vulnerabilities_collection,
)
 
router = APIRouter()
 
 
def _create_data_subject_request(
    org_id: str,
    request_type: str,
    identifier: str,
    now,
    expires_at,
    submitted_via: str = "api",
    source_types: Optional[list] = None,
    target_sources: Optional[list] = None,
) -> str:
    """Create the master request once; individual sources receive request_tasks."""
    request_id = str(uuid4())
    canonical_type = request_type.lower()
    data_subject_requests.insert_one({
        "id": request_id,
        "org_id": org_id,
        "organisation_id": org_id,
        "request_type": canonical_type,
        "data_principal": {
            "identifier_hash": identifier.lower(),
            "email": identifier if "@" in identifier else "",
        },
        "verification_status": "verified",
        "status": "in_progress",
        "sla_due_at": expires_at,
        "submitted_via": submitted_via,
        "source_types": source_types or ["local_device"],
        "target_sources": target_sources or ["local"],
        "created_at": now,
        "updated_at": now,
        # Transitional fields consumed by existing agent/API clients.
        "type": request_type.upper(),
        "identifier": identifier,
    })
    return request_id
 
 
def _iso(dt):
    if not dt:
        return None
 
    # If it's already an ISO string format, just pass it right back
    if isinstance(dt, str):
        return dt
 
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
 
    return dt.isoformat()
 
 
def _get_registered_device_or_fail(device_id: str, org_id: str):
    device = devices_collection.find_one({
        "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
        "source_type": "local_device",
        "source_key": device_id,
    }, {"_id": 0})
    if not device:
        # Fallback to device_id key
        device = devices_collection.find_one({
            "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
            "device_id": device_id,
        }, {"_id": 0})
    if not device:
        raise HTTPException(
            status_code=404,
            detail="Device not registered"
        )
    if not device.get("approved", False):
        raise HTTPException(
            status_code=403,
            detail="Device is not approved"
        )
    return device
 
# @router.post("/tasks")
# async def create_distributed_task(
#     req: CreateTaskRequest,
#     organisation_id: Optional[str] = None,
#     x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
#     x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
# ):
#     org_id = _resolve_org_id(x_org_id, organisation_id)
#     _validate_admin_key(x_admin_key, org_id)
 
#     now = utc_now()
#     expires_at = now + timedelta(hours=max(1, min(req.expires_in_hours, 24)))
#     device_filter = {"$or": [{"org_id": org_id}, {"organisation_id": org_id}], "approved": True}
#     if req.device_ids:
#         device_filter["device_id"] = {"$in": req.device_ids}
 
#     target_devices = list(devices_collection.find(device_filter, {"_id": 0, "device_id": 1, "id": 1}))
#     if not target_devices:
#         detail = (
#             "No eligible approved devices found for requested device IDs"
#             if req.device_ids
#             else "No eligible approved devices found"
#         )
#         raise HTTPException(status_code=400, detail=detail)
 
#     task_group_id = str(uuid4())
#     request_id = _create_data_subject_request(
#         org_id=org_id,
#         request_type="access",
#         identifier=req.query,
#         now=now,
#         expires_at=expires_at,
#         submitted_via="api",
#         source_types=["local_device"],
#     )
#     created = []
#     for device in target_devices:
#         task_id = str(uuid4())
#         data_source_id = device.get("id") or device["device_id"]
#         device_tasks_collection.insert_one({
#             "id": task_id,
#             "request_id": request_id,
#             "data_source_id": data_source_id,
#             "org_id": org_id,
#             "task_group_id": task_group_id,
#             "organisation_id": org_id,
#             "device_id": device["device_id"],
#             "source_type": "local_device",
#             "query": req.query,
#             "type": "access",
#             "status": "pending",
#             "created_at": now,
#             "expires_at": expires_at,
#             "updated_at": now,
#             "completed_at": None,
#         })
#         created.append({
#             "id": task_id,
#             "request_id": request_id,
#             "device_id": device["device_id"],
#             "expires_at": expires_at,
#         })
 
#     return {
#         "status": "tasks_created",
#         "request_id": request_id,
#         "task_group_id": task_group_id,
#         "tasks_created": len(created),
#         "tasks": created,
#     }
 
 
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
 
    query_filter = {"$or": [{"org_id": org_id}, {"organisation_id": org_id}]}
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
 
    task_ids = [t["id"] for t in tasks]
    results = list(
        device_results_collection.find(
            {
                "$and": [
                    {
                        "$or": [
                            {"request_task_id": {"$in": task_ids}},
                            {"task_id": {"$in": task_ids}},
                        ]
                    },
                    {
                        "$or": [
                            {"org_id": org_id},
                            {"organisation_id": org_id},
                        ]
                    },
                ]
            },
            {"_id": 0},
        )
    )
    result_map = {}
    for r in results:
        k = r.get("request_task_id") or r.get("task_id")
        if k:
            result_map[k] = r
 
    merged = []
    for task in tasks:
        result = result_map.get(task["id"])
        matches = result.get("matches", []) if result else []
        delete_replacements = result.get("delete_replacements", []) if result else []
        merged.append({
            "id": task["id"],
            "request_id": task.get("request_id"),
            "task_group_id": task.get("task_group_id"),
            "device_id": task.get("device_id"),
            "type": task.get("type", "access"),
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
            "delete_replacements": delete_replacements,
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
        {"device_id": device_id, "$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
        {"$set": {"last_seen": now, "updated_at": now}},
    )
 
    tasks = list(
        device_tasks_collection.find(
            {
                "device_id": device_id,
                "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
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
        "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
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
        {"id": req.task_id, "device_id": req.device_id, "$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
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
            {"id": req.task_id, "device_id": req.device_id, "$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
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
 
    processed_delete_replacements = []
    if getattr(req, "delete_replacements", None):
        for replacement in req.delete_replacements:
            if hasattr(replacement, "dict"):
                processed_delete_replacements.append(replacement.dict())
            elif hasattr(replacement, "model_dump"):
                processed_delete_replacements.append(replacement.model_dump())
            else:
                processed_delete_replacements.append(dict(replacement))
 
    # 5. Insert scan metadata into the canonical pii_classifications collection
    request_id = task.get("request_id")
    data_source_id = task.get("data_source_id", req.device_id)
 
    result_doc = {
        "id": str(uuid4()),
        "org_id": org_id,
        "organisation_id": org_id,
        "data_source_id": data_source_id,
        "request_task_id": task.get("id", req.task_id),
        "task_id": req.task_id,  # Compatibility field
        "request_id": request_id,
        "source_type": task.get("source_type", "local_device"),
        "device_id": req.device_id,
        "status": req.status,
        "scanned_files": getattr(req, "scanned_files", 0),
        "matches": processed_matches,  # Securely drops file paths and matches into Mongo
        "delete_replacements": processed_delete_replacements,
        "classified_at": now,
        "received_at": now,
        "created_at": now,
        "updated_at": now,
    }
    device_results_collection.insert_one(result_doc)
 
    if processed_delete_replacements:
        for replacement in processed_delete_replacements:
            device_delete_redactions_collection.update_one(
                {
                    "organisation_id": org_id,
                    "block_signature": replacement.get("block_signature"),
                    "original_value": replacement.get("original_value"),
                },
                {
                    "$setOnInsert": {
                        "created_at": now,
                        "organisation_id": org_id,
                        "block_signature": replacement.get("block_signature"),
                        "original_value": replacement.get("original_value"),
                        "masked_value": replacement.get("masked_value"),
                    },
                    "$set": {
                        "updated_at": now,
                        "last_task_id": req.task_id,
                        "last_device_id": req.device_id,
                        "last_file": replacement.get("file"),
                        "masked_value": replacement.get("masked_value"),
                    },
                },
                upsert=True,
            )
 
    # 6. Finalize task workflow transition to completed status
    device_tasks_collection.update_one(
        {"id": req.task_id, "device_id": req.device_id, "$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
        {"$set": {
            "status": "completed", 
            "completed_at": now, 
            "updated_at": now,
            "result_summary": {
                "records_found": len(processed_matches),
                "locations": [m.get("file") for m in processed_matches if m.get("file")],
            },
            "action_taken": "none" if task.get("type", "access") == "access" else task.get("type"),
        }},
    )
 
    # 7. Update data_subject_requests if all tasks completed
    if request_id:
        pending_count = device_tasks_collection.count_documents({
            "request_id": request_id,
            "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
            "status": {"$in": ["pending", "in_progress", "awaiting_approval"]},
        })
        if pending_count == 0:
            data_subject_requests.update_one(
                {"id": request_id, "$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
                {"$set": {"status": "completed", "updated_at": now}},
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
        {"task_group_id": task_group_id, "$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
        {"_id": 0}
    ))
    if not tasks:
        raise HTTPException(status_code=404, detail="Task group not found")
 
    task_ids = [t["id"] for t in tasks]
    results = list(device_results_collection.find(
        {
            "$or": [
                {"request_task_id": {"$in": task_ids}},
                {"task_id": {"$in": task_ids}},
            ],
            "$or": [
                {"org_id": org_id},
                {"organisation_id": org_id},
            ],
        },
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
    device = _get_registered_device_or_fail(req.device_id, org_id)
    data_source_id = device.get("id") or device.get("data_source_id") or req.device_id
    now = utc_now()
 
    if req.run_id:
        updated = device_cron_runs_collection.update_one(
            {"id": req.run_id, "$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
            {"$set": {
                "status": req.status,
                "completed_at": now,
                "duration_elapsed": req.duration,
                "error_message": req.error,
                "reported_at": now,
                "updated_at": now,
            }},
        )
        if updated.matched_count:
            return {"status": "acknowledged", "run_id": req.run_id, "run_status": req.status}
 
        device_cron_runs_collection.insert_one({
            "id": req.run_id,
            "org_id": org_id,
            "organisation_id": org_id,
            "device_id": req.device_id,
            "data_source_id": data_source_id,
            "task_type": req.task_type,
            "status": req.status,
            "started_at": _as_utc(req.started_at),
            "created_at": now,
            "updated_at": now,
            "duration_elapsed": req.duration,
            "error_message": req.error,
            "completed_at": now,
            "reported_at": now,
            "vulnerability_count": None,
        })
        return {"status": "acknowledged", "run_id": req.run_id, "run_status": req.status}
 
    run_id = str(uuid4())
    device_cron_runs_collection.insert_one({
        "id": run_id,
        "org_id": org_id,
        "device_id": req.device_id,
        "organisation_id": org_id,
        "data_source_id": data_source_id,
        "task_type": req.task_type,
        "status": req.status,
        "started_at": _as_utc(req.started_at),
        "created_at": now,
        "updated_at": now,
        "duration_elapsed": None,
        "error_message": None,
        "completed_at": None,
        "reported_at": now,
        "vulnerability_count": None,
    })
    return {"status": "acknowledged", "run_id": run_id, "run_status": req.status}
 
 
@router.get("/devices/cron-runs")
async def list_cron_runs(
    device_id: Optional[str] = None,
    limit: int = 100,
    organisation_id: Optional[str] = None,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)
 
    query_filter = {"$or": [{"organisation_id": org_id}, {"org_id": org_id}]}
    if device_id:
        query_filter["device_id"] = device_id
 
    runs = list(
        device_cron_runs_collection.find(query_filter, {"_id": 0})
        .sort("started_at", -1)
        .limit(max(1, min(limit, 500)))
    )
    return {
        "runs": [
            {
                "run_id": run.pop("id", ""),
                **run,
            }
            for run in runs
        ]
    }
 
 
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
    now = utc_now()
    vulnerability_doc = {
        "device_id": payload.device_id,
        "organisation_id": org_id,
        "vulnerabilities": vulns,
        "summary": {
            "total_vulnerabilities": len(vulns),
            "total_exposed_matches": sum(v.match_count for v in payload.vulnerabilities),
            "max_priority_score": max((v.priority_score for v in payload.vulnerabilities), default=0.0),
        },
        "updated_at": now,
    }
    if payload.cron_run_id:
        vulnerability_doc["cron_run_id"] = payload.cron_run_id
    device_vulnerabilities_collection.update_one(
        {"device_id": payload.device_id, "organisation_id": org_id},
        {"$set": vulnerability_doc},
        upsert=True,
    )
    if payload.cron_run_id:
        cron_run_vulnerabilities_collection.update_one(
            {
                "cron_run_id": payload.cron_run_id,
                "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
            },
            {"$set": {
                "org_id": org_id,
                "organisation_id": org_id,
                "device_id": payload.device_id,
                "cron_run_id": payload.cron_run_id,
                "vulnerabilities": vulns,
                "summary": vulnerability_doc["summary"],
                "updated_at": now,
            }},
            upsert=True,
        )
        device_cron_runs_collection.update_one(
            {
                "id": payload.cron_run_id,
                "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
            },
            {"$set": {
                "vulnerability_count": len(vulns),
                "updated_at": now,
            }},
        )
    return {"status": "success"}
 
 
@router.get("/vulnerabilities/cron-runs/{run_id}")
async def get_cron_run_vulnerabilities(
    run_id: str,
    organisation_id: Optional[str] = None,
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)
 
    query = {
        "cron_run_id": run_id,
        "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
    }
    doc = cron_run_vulnerabilities_collection.find_one(query, {"_id": 0})
    if doc is None:
        doc = device_vulnerabilities_collection.find_one(query, {"_id": 0})
 
    if doc is None:
        return {
            "cron_run_id": run_id,
            "device_id": "",
            "detail_retained": False,
            "summary": {},
            "vulnerabilities": [],
        }
 
    return {
        "cron_run_id": run_id,
        "device_id": doc.get("device_id", ""),
        "detail_retained": True,
        "summary": doc.get("summary", {}),
        "vulnerabilities": doc.get("vulnerabilities", []),
        "updated_at": doc.get("updated_at"),
    }
 
 
# @router.post("/tasks/remediations")
# async def create_modification_task(
#     payload: RemediationTaskRequest,
#     organisation_id: Optional[str] = None,
#     x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
#     x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
# ):
#     org_id = _resolve_org_id(x_org_id, organisation_id)
#     _validate_admin_key(x_admin_key, org_id)
 
#     now = utc_now()
#     expires_at = now + timedelta(days=1)
 
#     # ---------------------------------------------------------
#     # 1. Validate action + build query
#     # ---------------------------------------------------------
 
#     if payload.action_type == "update":
#         if not payload.new_value:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Missing 'new_value' for update task"
#             )
 
#         packed_query = f"{payload.target_value}::{payload.new_value}"
 
#     elif payload.action_type in {"delete", "access"}:
#         packed_query = payload.target_value
 
#     else:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Unsupported action_type: {payload.action_type}"
#         )
 
#     # ---------------------------------------------------------
#     # 2. Find the registered canonical data source
#     # ---------------------------------------------------------
 
#     device = _get_registered_device_or_fail(
#         payload.device_id,
#         org_id
#     )
 
#     data_source_id = device.get("id")
 
#     if not data_source_id:
#         raise HTTPException(
#             status_code=500,
#             detail=(
#                 f"Registered device '{payload.device_id}' "
#                 "does not have a canonical data source id"
#             )
#         )
 
#     # ---------------------------------------------------------
#     # 3. Create master data-subject request
#     # ---------------------------------------------------------
 
#     request_id = _create_data_subject_request(
#         org_id=org_id,
#         request_type=payload.action_type,
#         identifier=payload.target_value,
#         now=now,
#         expires_at=expires_at,
#         submitted_via="api",
#     )
 
#     # ---------------------------------------------------------
#     # 4. Create source-specific task
#     # ---------------------------------------------------------
 
#     task_id = str(uuid4())
#     task_group_id = str(uuid4())
 
#     task_doc = {
#         "id": task_id,
 
#         # Canonical relationship fields
#         "request_id": request_id,
#         "data_source_id": data_source_id,
 
#         "task_group_id": task_group_id,
 
#         "org_id": org_id,
#         "organisation_id": org_id,
 
#         "device_id": payload.device_id,
 
#         "source_type": "local_device",
 
#         "query": packed_query,
#         "status": "pending",
#         "type": payload.action_type,
 
#         "created_at": now,
#         "expires_at": expires_at,
#         "updated_at": now,
#         "completed_at": None,
#     }
 
#     device_tasks_collection.insert_one(task_doc)
 
#     return {
#         "status": "task_created",
#         "task_id": task_id,
#         "request_id": request_id,
#         "task_group_id": task_group_id,
#         "data_source_id": data_source_id,
#     }
    
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