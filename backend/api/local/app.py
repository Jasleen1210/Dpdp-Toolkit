from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

try:
    from services.local.local_db import (
        device_approval_requests_collection,
        device_results_collection,
        device_tasks_collection,
        devices_collection,
    )
    from services.combined.db import org_memberships_collection, organizations_collection
except ImportError:
    from backend.services.local.local_db import (
        device_approval_requests_collection,
        device_results_collection,
        device_tasks_collection,
        devices_collection,
    )
    from backend.services.combined.db import org_memberships_collection, organizations_collection

router = APIRouter()

class DeviceRegisterRequest(BaseModel):
    device_id: str
    hostname: str
    agent_version: str
    organisation_id: Optional[str] = None


class DeviceApprovalRequest(BaseModel):
    device_id: str
    approved: bool = True


class CreateTaskRequest(BaseModel):
    query: str
    device_ids: List[str] = Field(default_factory=list)
    expires_in_hours: int = 24


class MatchItem(BaseModel):
    type: str
    value: str
    file: str


class SubmitResultRequest(BaseModel):
    task_id: str
    device_id: str
    status: str
    scanned_files: int = 0
    matches: List[MatchItem] = Field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt_value):
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        try:
            dt_value = datetime.fromisoformat(dt_value)
        except ValueError:
            return None
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc)


def _parse_iso_datetime(value: Optional[str]):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _as_utc(dt)


def _get_org_or_fail(org_id: Optional[str]):
    if not org_id:
        raise HTTPException(status_code=400, detail="Missing organisation")

    org = organizations_collection.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=403, detail="Invalid organisation")
    return org


def _resolve_org_id(
    x_org_id: Optional[str],
    req_org_id: Optional[str] = None,
) -> str:
    if req_org_id and x_org_id and req_org_id != x_org_id:
        raise HTTPException(status_code=403, detail="Device organisation mismatch")

    org_id = req_org_id or x_org_id
    _get_org_or_fail(org_id)
    return org_id  # type: ignore[return-value]


def _validate_agent_auth(authorization: Optional[str], org_id: Optional[str]):
    org = _get_org_or_fail(org_id)
    expected_token = org.get("agent_token", "")
    if not expected_token:
        raise HTTPException(status_code=500, detail="Org agent token not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.replace("Bearer ", "", 1).strip()
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid agent token")


def _validate_admin_key(admin_key: Optional[str], org_id: Optional[str]):
    if not admin_key:
        raise HTTPException(status_code=401, detail="Missing admin key")

    org = _get_org_or_fail(org_id)

    # Preferred path: per-membership admin keys.
    member = org_memberships_collection.find_one(
        {
            "$and": [
                {
                    "$or": [
                        {"organisation_id": org["id"]},
                        {"organization_id": org["id"]},
                    ]
                },
                {
                    "$or": [
                        {"admin_api_key": admin_key},
                        {"admin_key": admin_key},
                    ]
                },
            ]
        },
        {"_id": 0, "user_id": 1},
    )
    if member:
        return

    # Backward-compatible fallback for legacy org-level keys.
    expected_key = org.get("admin_api_key", "")
    if expected_key and admin_key == expected_key:
        return

    raise HTTPException(status_code=401, detail="Invalid admin key")


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


def _upsert_approval_request(device_id: str, org_id: str, hostname: str, agent_version: str):
    now = utc_now()
    device_approval_requests_collection.update_one(
        {"device_id": device_id, "organisation_id": org_id, "status": "pending"},
        {
            "$set": {
                "device_id": device_id,
                "organisation_id": org_id,
                "hostname": hostname,
                "agent_version": agent_version,
                "status": "pending",
                "updated_at": now,
            },
            "$setOnInsert": {
                "id": str(uuid4()),
                "created_at": now,
            },
        },
        upsert=True,
    )


@router.get("/")
async def root():
    return {"status": "Backend running smoothly!"}


@router.post("/devices/register")
async def register_device(
    req: DeviceRegisterRequest,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, req.organisation_id)
    _validate_agent_auth(authorization, org_id)

    existing = devices_collection.find_one({"device_id": req.device_id, "organisation_id": org_id})
    if existing:
        approved = bool(existing.get("approved", False))
    else:
        approved = False

    devices_collection.update_one(
        {"device_id": req.device_id, "organisation_id": org_id},
        {
            "$set": {
                "hostname": req.hostname,
                "agent_version": req.agent_version,
                "approved": approved,
                "last_seen": utc_now(),
                "updated_at": utc_now(),
            },
            "$setOnInsert": {
                "created_at": utc_now(),
                "organisation_id": org_id,
            },
        },
        upsert=True,
    )

    if not approved:
        _upsert_approval_request(req.device_id, org_id, req.hostname, req.agent_version)

    return {
        "device_id": req.device_id,
        "organisation_id": org_id,
        "approved": approved,
        "message": "device registered" if approved else "device pending approval",
    }


@router.get("/devices")
async def list_devices(
    organisation_id: Optional[str] = None,
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)

    devices = list(
        devices_collection.find({"organisation_id": org_id}, {"_id": 0}).sort("updated_at", -1)
    )
    return {"devices": devices}


@router.get("/organisations/{organisation_id}/devices")
async def list_devices_for_organisation(
    organisation_id: str,
):
    org = _get_org_or_fail(organisation_id)
    devices = list(
        devices_collection.find({"organisation_id": org["id"]}, {"_id": 0}).sort("updated_at", -1)
    )
    return {
        "organisation": {"id": org["id"], "name": org.get("name", "")},
        "devices": devices,
    }


@router.post("/devices/approve")
async def approve_device(
    req: DeviceApprovalRequest,
    organisation_id: Optional[str] = None,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    result = devices_collection.update_one(
        {"device_id": req.device_id, "organisation_id": org_id},
        {"$set": {"approved": req.approved, "updated_at": utc_now()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")

    if req.approved:
        device_approval_requests_collection.update_many(
            {"device_id": req.device_id, "organisation_id": org_id, "status": "pending"},
            {"$set": {"status": "approved", "resolved_at": utc_now(), "updated_at": utc_now()}},
        )
    else:
        device_approval_requests_collection.update_many(
            {"device_id": req.device_id, "organisation_id": org_id, "status": "pending"},
            {"$set": {"status": "rejected", "resolved_at": utc_now(), "updated_at": utc_now()}},
        )

    return {"device_id": req.device_id, "approved": req.approved}


@router.get("/devices/approval-requests")
async def list_device_approval_requests(
    organisation_id: Optional[str] = None,
    status: str = "pending",
    limit: int = 200,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    safe_limit = max(1, min(limit, 1000))
    query = {"organisation_id": org_id}
    if status and status != "all":
        query["status"] = status

    requests = list(
        device_approval_requests_collection.find(query, {"_id": 0})
        .sort("updated_at", -1)
        .limit(safe_limit)
    )

    return {"requests": requests}


@router.post("/tasks")
async def create_distributed_task(
    req: CreateTaskRequest,
    organisation_id: Optional[str] = None,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    expires_hours = max(1, min(req.expires_in_hours, 24))
    expires_at = utc_now() + timedelta(hours=expires_hours)

    device_filter = {"organisation_id": org_id, "approved": True}
    if req.device_ids:
        device_filter["device_id"] = {"$in": req.device_ids}

    target_devices = list(devices_collection.find(device_filter, {"_id": 0, "device_id": 1}))
    if not target_devices:
        if req.device_ids:
            raise HTTPException(
                status_code=400,
                detail="No eligible approved devices found for requested device IDs",
            )
        raise HTTPException(status_code=400, detail="No eligible approved devices found")

    task_group_id = str(uuid4())
    created = []

    for device in target_devices:
        task_id = str(uuid4())
        task_doc = {
            "id": task_id,
            "task_group_id": task_group_id,
            "organisation_id": org_id,
            "device_id": device["device_id"],
            "query": req.query,
            "status": "pending",
            "created_at": utc_now(),
            "expires_at": expires_at,
            "completed_at": None,
        }
        device_tasks_collection.insert_one(task_doc)
        created.append(
            {
                "id": task_id,
                "device_id": device["device_id"],
                "expires_at": expires_at,
            }
        )

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

    safe_limit = max(1, min(limit, 1000))
    tasks = list(
        device_tasks_collection.find(query_filter, {"_id": 0})
        .sort("created_at", -1)
        .limit(safe_limit)
    )

    if not tasks:
        return {"tasks": []}

    task_ids = [t["id"] for t in tasks]
    results = list(
        device_results_collection.find(
            {"task_id": {"$in": task_ids}, "organisation_id": org_id},
            {"_id": 0},
        )
    )
    result_map = {r["task_id"]: r for r in results}

    merged = []
    for task in tasks:
        result = result_map.get(task["id"])
        matches = result.get("matches", []) if result else []
        pii_types = sorted({m.get("type", "") for m in matches if m.get("type")})

        merged.append(
            {
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
                "pii_types": pii_types,
                "matches": matches,
            }
        )

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
            },
        )
    )

    updates_query = {
        "device_id": device_id,
        "organisation_id": org_id,
    }
    since_dt = _parse_iso_datetime(since)
    if since and not since_dt:
        raise HTTPException(status_code=400, detail="Invalid since format; expected ISO datetime")
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

    next_cursor = updates[0].get("updated_at") if updates else now

    return {
        "tasks": tasks,
        "updates": updates,
        "has_updates": len(updates) > 0,
        "next_cursor": next_cursor,
    }


@router.post("/results")
async def submit_device_result(
    req: SubmitResultRequest,
    organisation_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_agent_auth(authorization, org_id)
    _get_registered_device_or_fail(req.device_id, org_id)

    task = device_tasks_collection.find_one(
        {
            "id": req.task_id,
            "device_id": req.device_id,
            "organisation_id": org_id,
        },
        {"_id": 0},
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.get("status") == "completed":
        return {"message": "result already submitted", "task_id": req.task_id}

    expires_at = _as_utc(task.get("expires_at"))
    if expires_at and utc_now() > expires_at:
        device_tasks_collection.update_one(
            {"id": req.task_id, "device_id": req.device_id, "organisation_id": org_id},
            {"$set": {"status": "expired", "updated_at": utc_now()}},
        )
        raise HTTPException(status_code=410, detail="Task expired")

    result_doc = {
        "task_id": req.task_id,
        "device_id": req.device_id,
        "organisation_id": org_id,
        "status": req.status,
        "scanned_files": req.scanned_files,
        "matches": [m.dict() for m in req.matches],
        "received_at": utc_now(),
    }
    device_results_collection.insert_one(result_doc)

    device_tasks_collection.update_one(
        {"id": req.task_id, "device_id": req.device_id, "organisation_id": org_id},
        {"$set": {"status": "completed", "completed_at": utc_now(), "updated_at": utc_now()}},
    )

    return {"message": "result accepted", "task_id": req.task_id}


@router.get("/tasks/{task_group_id}/results")
async def get_task_group_results(
    task_group_id: str,
    organisation_id: Optional[str] = None,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    tasks = list(
        device_tasks_collection.find(
            {"task_group_id": task_group_id, "organisation_id": org_id},
            {"_id": 0},
        )
    )
    if not tasks:
        raise HTTPException(status_code=404, detail="Task group not found")

    task_ids = [t["id"] for t in tasks]
    results = list(
        device_results_collection.find(
            {"task_id": {"$in": task_ids}, "organisation_id": org_id},
            {"_id": 0},
        )
    )

    return {
        "task_group_id": task_group_id,
        "tasks": tasks,
        "results": results,
    }
