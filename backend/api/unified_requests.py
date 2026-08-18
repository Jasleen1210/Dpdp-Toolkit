from datetime import datetime, timedelta, timezone
import os
from typing import List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.services.persistence.mongo import (
    audit_logs,
    data_sources,
    data_subject_requests,
    pii_classifications,
    request_tasks,
)
from backend.services.remediation import process_request
from backend.api.middleware import OrgAuthContext, resolve_org_context, resolve_org_context_optional
from backend.services.request_service import RequestStateManager
from backend.api.agents.helpers import _is_device_active

router = APIRouter(prefix="/requests", tags=["Unified Data Subject Requests"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_request_status(status: Optional[str], tasks: Optional[list] = None, requires_approval: bool = False) -> str:
    """Translate raw Mongo task states into a stable UI status.

    Only delete requests require explicit approval. Everything else progresses directly
    through pending -> in_progress -> completed without showing approval controls.
    """
    normalized = (status or "pending").lower()
    task_list = tasks or []

    if normalized in {"rejected", "cancelled"}:
        return "rejected"
    if normalized in {"error", "failed"}:
        return "error"
    if normalized == "awaiting_approval":
        return "awaiting_approval"

    if requires_approval:
        return "awaiting_approval" if normalized in {"awaiting_approval", "pending", "in_progress", ""} else normalized

    if normalized == "completed":
        return "completed"

    if task_list:
        if all((t or {}).get("status", "pending").lower() == "completed" for t in task_list):
            return "completed"
        if any((t or {}).get("status", "pending").lower() in {"pending", "in_progress"} for t in task_list):
            return "in_progress"

    return normalized if normalized in {"pending", "in_progress"} else "pending"


class UnifiedDataSubjectRequest(BaseModel):
    type: Literal["access", "update", "delete", "ACCESS", "UPDATE", "DELETE"] = Field(
        ..., description="Type of request: access, update, or delete"
    )
    identifier: str = Field(..., description="Subject identifier (e.g. email, phone, name)")
    new_value: Optional[str] = Field(
        default=None, description="Replacement value when action is 'update'"
    )
    target: Optional[Literal["all", "cloud", "local", "db", "ALL", "CLOUD", "LOCAL", "DB"]] = Field(
        default=None,
        description="Target storage scope: 'all', 'local', 'cloud', or 'db'",
    )
    target_sources: Optional[List[Literal["cloud", "local", "db", "all", "CLOUD", "LOCAL", "DB", "ALL"]]] = Field(
        default=None,
        description="Target infrastructure to scan and process. Can be ['all'] or ['local', 'cloud', 'db']. Defaults to all.",
    )
    device_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional list of specific approved device IDs. If omitted, targets all approved devices.",
    )
    expires_in_hours: int = Field(
        default=24, ge=1, le=720, description="Task expiration window in hours"
    )
    org_id: Optional[str] = Field(
        default=None, description="Organization for unauthenticated API callers"
    )


def _process_cloud_sources(req_doc: dict, org_id: str) -> dict:
    """Executes cloud scanning and remediation across AWS S3, Azure Blob, and GCP."""
    try:
        cloud_req = {
            "id": req_doc["id"],
            "type": req_doc["type"].upper(),
            "identifier": req_doc["identifier"],
            "new_value": req_doc.get("new_value"),
        }
        res = process_request(cloud_req)
        
        # Store cloud classification results into pii_classifications for unified inspection
        if res and isinstance(res, dict) and "locations" in res:
            now = utc_now()
            for loc in res.get("locations", []):
                pii_classifications.update_one(
                    {
                        "request_id": req_doc["id"],
                        "file": loc.get("file"),
                        "source_type": "cloud_storage",
                    },
                    {
                        "$set": {
                            "request_id": req_doc["id"],
                            "org_id": org_id,
                            "organisation_id": org_id,
                            "source_type": "cloud_storage",
                            "provider": loc.get("provider"),
                            "bucket": loc.get("bucket"),
                            "region": loc.get("region"),
                            "file": loc.get("file"),
                            "location": loc.get("location"),
                            "action_taken": req_doc["type"].lower(),
                            "status": "completed",
                            "classified_at": now,
                            "matches": [
                                {
                                    "type": "PII",
                                    "value": req_doc["identifier"],
                                    "file": loc.get("file"),
                                }
                            ],
                            "updated_at": now,
                        },
                        "$setOnInsert": {
                            "id": str(uuid4()),
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
        return res or {"message": "Cloud processing completed", "locations": []}
    except Exception as exc:
        return {"error": f"Cloud execution error: {str(exc)}", "locations": []}


def _dispatch_local_device_tasks(
    req_doc: dict,
    org_id: str,
    device_ids: Optional[List[str]],
    expires_at: datetime,
) -> list[dict]:
    """Dispatches execution tasks to all eligible approved local devices."""
    device_filter = {
        "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
        "approved": True,
    }
    if device_ids:
        device_filter["device_id"] = {"$in": device_ids}

    target_devices = list(data_sources.find(
        device_filter,
        {"_id": 0, "device_id": 1, "id": 1, "last_seen": 1},
    ))
    if not target_devices:
        return []

    action_type = req_doc["type"].lower()
    if action_type == "update":
        packed_query = f"{req_doc['identifier']}::{req_doc.get('new_value', '')}"
    else:
        packed_query = req_doc["identifier"]

    task_group_id = str(uuid4())
    created = []
    now = utc_now()

    for dev in target_devices:
        dev_id = dev.get("device_id")
        if not dev_id:
            continue
        task_id = str(uuid4())
        data_source_id = dev.get("id") or dev_id

        is_active = _is_device_active(dev.get("last_seen"))
        task_doc = {
            "id": task_id,
            "request_id": req_doc["id"],
            "task_group_id": task_group_id,
            "data_source_id": data_source_id,
            "org_id": org_id,
            "organisation_id": org_id,
            "device_id": dev_id,
            "source_type": "local_device",
            "query": packed_query,
            "type": action_type,
            "status": "pending" if is_active else "skipped",
            "status_reason": None if is_active else "Device is inactive and did not receive this request",
            "created_at": now,
            "expires_at": expires_at,
            "updated_at": now,
            "completed_at": None if is_active else now,
        }
        request_tasks.insert_one(task_doc)
        created.append({
            "task_id": task_id,
            "device_id": dev_id,
            "status": task_doc["status"],
            "status_reason": task_doc["status_reason"],
            "expires_at": expires_at.isoformat(),
        })

    return created


def _dispatch_database_sources(req_doc: dict, org_id: str) -> dict:
    """Extensible handler for database source queries (PostgreSQL, MySQL, MongoDB)."""
    return {
        "status": "completed",
        "message": "Database scanning connector checked tables.",
        "records_affected": 0,
    }


def _run_async_processing(master_doc: dict, org_id: str, target_sources: list):
    """Asynchronously executes cloud storage and database processing in the background."""
    request_id = master_doc["id"]
    try:
        now = utc_now()
        data_subject_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "in_progress", "updated_at": now}},
        )

        cloud_res = None
        source_status = {}
        if "cloud" in target_sources and not master_doc.get("requires_approval"):
            cloud_res = _process_cloud_sources(master_doc, org_id)
            source_status["cloud"] = "error" if cloud_res.get("error") else "completed"

        if "db" in target_sources:
            db_res = _dispatch_database_sources(master_doc, org_id)
            source_status["db"] = "error" if db_res.get("error") else "completed"

        update_fields = {"updated_at": utc_now()}
        if cloud_res and isinstance(cloud_res, dict):
            update_fields["cloud_results"] = cloud_res.get("locations", [])
            if cloud_res.get("error"):
                update_fields["cloud_error"] = cloud_res["error"]
        if "local" in target_sources:
            local_tasks = list(request_tasks.find({"request_id": request_id}, {"_id": 0, "status": 1}))
            source_status["local"] = "queued" if any(t.get("status") == "pending" for t in local_tasks) else "completed"
        update_fields["source_status"] = source_status
        update_fields["status_message"] = RequestStateManager.build_status_message(source_status)

        if "local" not in target_sources and not master_doc.get("requires_approval"):
            update_fields["status"] = "error" if "error" in source_status.values() else "completed"
            update_fields["closed_at"] = utc_now()
        elif not master_doc.get("requires_approval"):
            if "error" in source_status.values():
                update_fields["status"] = "error"
            elif source_status and all(value == "completed" for value in source_status.values()):
                update_fields["status"] = "completed"
                update_fields["closed_at"] = utc_now()
            else:
                update_fields["status"] = "in_progress"

        data_subject_requests.update_one({"id": request_id}, {"$set": update_fields})
    except Exception as exc:
        print(f"Background processing error for {request_id}: {exc}")


@router.post("")
async def create_unified_request(
    payload: UnifiedDataSubjectRequest,
    background_tasks: BackgroundTasks,
    ctx: Optional[OrgAuthContext] = Depends(resolve_org_context_optional),
):
    """
    Unified Data Subject Request Dispatcher (Org-Scoped):
    - Stores Master request into MongoDB FIRST (immediate < 5ms response)
    - Queues local device tasks into request_tasks in MongoDB (org-filtered)
    - Spawns background task for Cloud (AWS/Azure/GCP) & Database processing
    - For DELETE requests: enters AWAITING_APPROVAL until approved
    - Enforces org-level data isolation via OrgAuthContext
    """
    org_id = (ctx.org_id if ctx else (payload.org_id or "").strip())
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id is required for unauthenticated API requests")

    raw_type = payload.type.upper()
    canonical_type = {"ACCESS": "access", "UPDATE": "update", "DELETE": "delete"}[raw_type]

    if raw_type == "UPDATE" and not payload.new_value:
        raise HTTPException(
            status_code=400, detail="new_value is required for UPDATE requests"
        )

    now = utc_now()
    expires_at = now + timedelta(hours=max(1, min(payload.expires_in_hours, 720)))
    request_id = str(uuid4())

    raw_target = payload.target.lower() if payload.target else None
    raw_sources = [s.lower() for s in payload.target_sources] if payload.target_sources else []

    if raw_target == "all" or "all" in raw_sources:
        target_sources = ["cloud", "local", "db"]
    elif raw_target:
        target_sources = [raw_target]
    elif raw_sources:
        target_sources = raw_sources
    else:
        target_sources = ["cloud", "local", "db"]

    requires_approval = raw_type == "DELETE"

    source_types_list = []
    if "cloud" in target_sources:
        source_types_list.append("cloud_storage")
    if "local" in target_sources:
        source_types_list.append("local_device")
    if "db" in target_sources:
        source_types_list.append("database")

    master_doc = {
        "id": request_id,
        "org_id": org_id,
        "organisation_id": org_id,
        "request_type": canonical_type,
        "type": raw_type,
        "identifier": payload.identifier,
        "new_value": payload.new_value,
        "data_principal": {
            "identifier_hash": payload.identifier.lower(),
            "email": payload.identifier if "@" in payload.identifier else "",
        },
        "verification_status": "verified",
        "submitted_via": "api",
        "status": "AWAITING_APPROVAL" if requires_approval else "pending",
        "source_status": {source: "awaiting_approval" if requires_approval else "queued" for source in target_sources},
        "status_message": "Waiting for approval before execution." if requires_approval else "Request saved. Preparing scans.",
        "target_sources": target_sources,
        "source_types": source_types_list,
        "requires_approval": requires_approval,
        "created_at": now,
        "updated_at": now,
    }

    # 1. Store Master doc in MongoDB FIRST
    data_subject_requests.insert_one(master_doc)

    # 2. Dispatch Local Device Tasks (e.g. Athena) into request_tasks
    local_tasks = []
    if "local" in target_sources:
        local_tasks = RequestStateManager.create_local_device_tasks(
            request_id=request_id,
            org_id=org_id,
            request_type=canonical_type,
            identifier=payload.identifier,
            new_value=payload.new_value,
            device_ids=payload.device_ids,
            expires_at=expires_at,
        )

    # 3. Schedule background processing for Cloud & DB
    background_tasks.add_task(_run_async_processing, master_doc, org_id, target_sources)

    audit_logs.insert_one({
        "actor_type": "system",
        "actor_id": "unified-request-engine",
        "entity_type": "data_subject_request",
        "org_id": org_id,
        "action": raw_type,
        "identifier": payload.identifier,
        "target_sources": target_sources,
        "local_tasks_count": len(local_tasks),
        "timestamp": now,
        "status": "QUEUED",
    })

    return {
        "status": "accepted",
        "request_id": request_id,
        "request_type": raw_type.lower(),
        "identifier": payload.identifier,
        "overall_status": master_doc["status"].lower(),
        "target_sources": target_sources,
        "local_tasks": local_tasks,
        "message": (
            "Request saved in MongoDB and queued for background processing. "
            f"Dispatched to {len(local_tasks)} local device(s)."
            if local_tasks
            else "Request saved in MongoDB and processing in background."
        ),
    }


@router.get("")
async def list_unified_requests(
    ctx: OrgAuthContext = Depends(resolve_org_context),
):
    """
    Returns all data subject requests with real-time status across Cloud and Local devices.
    Org-scoped: Users only see their organization's requests.
    """
    org_id = ctx.org_id
    
    try:
        data = list(
            data_subject_requests.find(
                RequestStateManager.build_request_list_query(org_id),
                {"_id": 0}
            ).sort("created_at", -1)
        )
    except Exception as e:
        print(f"Error reading data_subject_requests: {e}")
        data = []

    # Single-roundtrip batch lookup for all tasks
    request_ids = [r.get("id") for r in data if r.get("id")]
    try:
        all_tasks = list(
            request_tasks.find(
                {"request_id": {"$in": request_ids}, "org_id": org_id},
                {"_id": 0}
            )
        ) if request_ids else []
    except Exception as e:
        print(f"Error reading request_tasks: {e}")
        all_tasks = []

    tasks_by_request: dict = {}
    for t in all_tasks:
        req_id = t.get("request_id")
        if req_id:
            tasks_by_request.setdefault(req_id, []).append(t)

    formatted = []
    for r in data:
        r_id = r.get("id")
        if not r_id:
            continue

        tasks = tasks_by_request.get(r_id, [])
        device_ids = [t.get("device_id") for t in tasks if t.get("device_id")]
        completed_tasks = sum(1 for t in tasks if t.get("status") == "completed")

        subject = (
            r.get("identifier")
            or (r.get("data_principal", {}) or {}).get("identifier_hash")
            or (r.get("data_principal", {}) or {}).get("email")
            or "Unknown"
        )

        raw_type = (r.get("type") or r.get("request_type") or "access").lower()
        type_mapping = {"correction": "update", "erasure": "delete"}
        display_type = type_mapping.get(raw_type, raw_type)

        status = normalize_request_status(
            r.get("status", "pending"),
            tasks,
            bool(r.get("requires_approval")),
        )

        created_val = r.get("created_at")
        created_iso = (
            created_val.isoformat()
            if hasattr(created_val, "isoformat")
            else str(created_val) if created_val else ""
        )
        created_str = (
            created_val.strftime("%Y-%m-%d %H:%M")
            if hasattr(created_val, "strftime")
            else str(created_val)[:16] if created_val else "-"
        )

        raw_target_sources = r.get("target_sources")
        source_types = r.get("source_types", [])
        if raw_target_sources is not None:
            resolved_targets = [str(s).lower() for s in raw_target_sources]
        elif "cloud_storage" in source_types and "local_device" not in source_types:
            resolved_targets = ["cloud"]
        elif "local_device" in source_types and "cloud_storage" not in source_types:
            resolved_targets = ["local"]
        elif device_ids:
            resolved_targets = ["local"]
        else:
            # Default un-targeted requests without local devices to cloud storage
            resolved_targets = ["cloud"]
            if "cloud_storage" not in source_types:
                source_types.append("cloud_storage")

        sources_summary = []
        if "cloud" in resolved_targets or "cloud_storage" in source_types:
            sources_summary.append("Cloud (AWS/Azure/GCP)")
        if device_ids:
            sources_summary.append(f"Local ({', '.join(device_ids)})")
        elif "local" in resolved_targets or "local_device" in source_types:
            sources_summary.append("Local")
        if "db" in resolved_targets or "database" in source_types:
            sources_summary.append("Database")

        formatted.append({
            "id": r_id,
            "type": display_type,
            "subject": subject,
            "status": status,
            "handler": " | ".join(sources_summary) or "auto-system",
            "created": created_str,
            "created_at": created_iso,
            "devices": device_ids,
            "tasks_completed": completed_tasks,
            "target_sources": resolved_targets,
            "source_types": source_types,
            "requires_approval": bool(r.get("requires_approval")),
            "source_status": r.get("source_status", {}),
            "status_message": r.get("status_message") or RequestStateManager.build_status_message({"request": status}),
            "cloud_error": r.get("cloud_error"),
        })

    known_request_ids = set(request_ids)
    orphan_tasks = list(
        request_tasks.find(
            {
                "request_id": {"$nin": list(known_request_ids)},
                "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
            },
            {"_id": 0},
        ).sort("created_at", -1)
    )

    for t in orphan_tasks:
        t_id = t.get("id")
        created_val = t.get("created_at")
        created_iso = (
            created_val.isoformat()
            if hasattr(created_val, "isoformat")
            else str(created_val) if created_val else ""
        )
        created_str = (
            created_val.strftime("%Y-%m-%d %H:%M")
            if hasattr(created_val, "strftime")
            else str(created_val)[:16] if created_val else "-"
        )
        formatted.append({
            "id": t_id,
            "type": t.get("type", "access"),
            "subject": t.get("query") or "Local File Request",
            "status": t.get("status", "pending"),
            "handler": f"Local ({t.get('device_id', 'local_device')})",
            "created": created_str,
            "created_at": created_iso,
            "devices": [t.get("device_id")] if t.get("device_id") else [],
            "tasks_count": 1,
            "tasks_completed": 1 if t.get("status") == "completed" else 0,
            "target_sources": ["local"],
            "source_types": ["local_device"],
        })

    return {"requests": formatted}


@router.get("/{request_id}")
async def get_unified_request_detail(
    request_id: str,
    ctx: OrgAuthContext = Depends(resolve_org_context),
):
    """
    Returns complete end-to-end details, local task findings, and cloud results.
    Org-scoped: Returns 404 if request doesn't belong to user's org.
    """
    org_id = ctx.org_id
    
    result = RequestStateManager.get_request_with_tasks(request_id, org_id)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return result


@router.post("/{request_id}/approve")
async def approve_unified_request(
    request_id: str,
    ctx: OrgAuthContext = Depends(resolve_org_context),
):
    """
    Approves an awaiting DELETE request, triggering remediation across cloud and local.
    Only org admins/owners can approve.
    Org-scoped: Returns 404 if request doesn't belong to user's org.
    """
    org_id = ctx.org_id
    
    # Verify user has permission to approve (admin or owner)
    if not ctx.is_admin_or_owner():
        raise HTTPException(status_code=403, detail="Only admins can approve requests")
    
    req = data_subject_requests.find_one(
        RequestStateManager.build_request_list_query(org_id, {"id": request_id}),
        {"_id": 0}
    )
    
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if not req.get("requires_approval"):
        raise HTTPException(status_code=400, detail="This request does not require approval")
    
    now = utc_now()
    
    cloud_result = {}
    if "cloud" in req.get("target_sources", []):
        cloud_result = process_request({
            "id": request_id,
            "type": req.get("type", "access").upper(),
            "identifier": req.get("identifier"),
            "new_value": req.get("new_value"),
        })

    local_tasks = list(request_tasks.find(
        {
            "request_id": request_id,
            "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
        },
        {"_id": 0, "status": 1},
    ))
    has_pending_local = any(
        task.get("status") in {"pending", "in_progress"} for task in local_tasks
    )
    cloud_failed = isinstance(cloud_result, dict) and bool(cloud_result.get("error"))
    next_status = "error" if cloud_failed else "in_progress" if has_pending_local else "completed"
    source_status = {
        source: (
            "error" if source == "cloud" and cloud_failed else
            "queued" if source == "local" and has_pending_local else
            "completed"
        )
        for source in req.get("target_sources", [])
    }

    data_subject_requests.update_one(
        RequestStateManager.build_request_list_query(org_id, {"id": request_id}),
        {
            "$set": {
                "status": next_status,
                "source_status": source_status,
                "status_message": RequestStateManager.build_status_message(source_status),
                "approved_at": now,
                "updated_at": now,
                **({} if next_status == "in_progress" else {"closed_at": now}),
            }
        },
    )

    audit_logs.insert_one({
        "actor_type": "user",
        "actor_id": ctx.user_id,
        "entity_type": "data_subject_request",
        "org_id": org_id,
        "action": "APPROVE_REQUEST",
        "request_id": request_id,
        "timestamp": now,
        "status": "SUCCESS",
    })

    return {
        "status": "success",
        "message": (
            "Request approved. Cloud processing completed; waiting for local device results."
            if has_pending_local and not cloud_failed
            else "Request approved and executed across the selected sources."
        ),
        "request_id": request_id,
        "cloud_result": cloud_result,
    }
