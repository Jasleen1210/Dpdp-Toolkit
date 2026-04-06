import os
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone

from backend.api.cloud_api.api_s3 import router as cloud_router
from backend.services.detector import detect_pii_full

from backend.services.local.local_db import (
    devices_collection,
    device_tasks_collection,
    device_results_collection,
)

app = FastAPI()

ORG_ID = os.getenv("ORG_ID", "dpdp-org")
DEVICE_SHARED_TOKEN = os.getenv("DEVICE_SHARED_TOKEN", "")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
APPROVED_DEVICE_IDS = {
    d.strip() for d in os.getenv("APPROVED_DEVICE_IDS", "").split(",") if d.strip()
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# cloud apis-> pii classify and dpdp request handling
app.include_router(cloud_router)

# ----------------------------
# Device orchestration APIs
# ----------------------------

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
    paths: List[str] = Field(default_factory=list)
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


def utc_now():
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


def _validate_org(org_id: Optional[str]):
    if org_id != ORG_ID:
        raise HTTPException(status_code=403, detail="Invalid organisation")


def _validate_agent_auth(authorization: Optional[str], org_id: Optional[str]):
    _validate_org(org_id)

    if not DEVICE_SHARED_TOKEN:
        raise HTTPException(status_code=500, detail="Server token not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.replace("Bearer ", "", 1).strip()
    if token != DEVICE_SHARED_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid agent token")


def _validate_admin_key(admin_key: Optional[str]):
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=500, detail="Admin API key not configured")
    if admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")


def _get_registered_device_or_fail(device_id: str):
    device = devices_collection.find_one(
        {"device_id": device_id, "organisation_id": ORG_ID},
        {"_id": 0},
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not registered")
    if not device.get("approved", False):
        raise HTTPException(status_code=403, detail="Device is not approved")
    return device


@app.post("/devices/register")
async def register_device(
    req: DeviceRegisterRequest,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    _validate_agent_auth(authorization, x_org_id)

    if req.organisation_id and req.organisation_id != ORG_ID:
        raise HTTPException(status_code=403, detail="Device organisation mismatch")

    existing = devices_collection.find_one({"device_id": req.device_id, "organisation_id": ORG_ID})
    if existing:
        approved = bool(existing.get("approved", False))
    else:
        approved = req.device_id in APPROVED_DEVICE_IDS

    devices_collection.update_one(
        {"device_id": req.device_id, "organisation_id": ORG_ID},
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
                "organisation_id": ORG_ID,
            },
        },
        upsert=True,
    )

    return {
        "device_id": req.device_id,
        "organisation_id": ORG_ID,
        "approved": approved,
        "message": "device registered" if approved else "device pending approval",
    }


@app.get("/devices")
async def list_devices(
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    _validate_org(x_org_id)

    devices = list(
        devices_collection.find({"organisation_id": ORG_ID}, {"_id": 0}).sort("updated_at", -1)
    )
    return {"devices": devices}


@app.post("/devices/approve")
async def approve_device(
    req: DeviceApprovalRequest,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    _validate_admin_key(x_admin_key)
    _validate_org(x_org_id)

    result = devices_collection.update_one(
        {"device_id": req.device_id, "organisation_id": ORG_ID},
        {"$set": {"approved": req.approved, "updated_at": utc_now()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")

    return {"device_id": req.device_id, "approved": req.approved}


@app.post("/tasks")
async def create_distributed_task(
    req: CreateTaskRequest,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    _validate_admin_key(x_admin_key)
    _validate_org(x_org_id)

    expires_hours = max(1, min(req.expires_in_hours, 24))
    expires_at = utc_now() + timedelta(hours=expires_hours)

    device_filter = {"organisation_id": ORG_ID, "approved": True}
    if req.device_ids:
        device_filter["device_id"] = {"$in": req.device_ids}

    target_devices = list(devices_collection.find(device_filter, {"_id": 0, "device_id": 1}))
    if not target_devices:
        raise HTTPException(status_code=400, detail="No eligible approved devices found")

    task_group_id = str(uuid4())
    created = []

    for device in target_devices:
        task_id = str(uuid4())
        task_doc = {
            "id": task_id,
            "task_group_id": task_group_id,
            "organisation_id": ORG_ID,
            "device_id": device["device_id"],
            "query": req.query,
            "paths": req.paths,
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


@app.get("/tasks")
async def list_distributed_tasks(
    device_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    _validate_admin_key(x_admin_key)
    _validate_org(x_org_id)

    query_filter = {"organisation_id": ORG_ID}
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
            {"task_id": {"$in": task_ids}, "organisation_id": ORG_ID},
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


@app.get("/devices/tasks")
async def get_device_tasks(
    device_id: str,
    since: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    _validate_agent_auth(authorization, x_org_id)
    _get_registered_device_or_fail(device_id)

    now = utc_now()
    devices_collection.update_one(
        {"device_id": device_id, "organisation_id": ORG_ID},
        {"$set": {"last_seen": now, "updated_at": now}},
    )

    tasks = list(
        device_tasks_collection.find(
            {
                "device_id": device_id,
                "organisation_id": ORG_ID,
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
        "organisation_id": ORG_ID,
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


@app.post("/results")
async def submit_device_result(
    req: SubmitResultRequest,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    _validate_agent_auth(authorization, x_org_id)
    _get_registered_device_or_fail(req.device_id)

    task = device_tasks_collection.find_one(
        {
            "id": req.task_id,
            "device_id": req.device_id,
            "organisation_id": ORG_ID,
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
            {"id": req.task_id, "device_id": req.device_id, "organisation_id": ORG_ID},
            {"$set": {"status": "expired", "updated_at": utc_now()}},
        )
        raise HTTPException(status_code=410, detail="Task expired")

    result_doc = {
        "task_id": req.task_id,
        "device_id": req.device_id,
        "organisation_id": ORG_ID,
        "status": req.status,
        "scanned_files": req.scanned_files,
        "matches": [m.dict() for m in req.matches],
        "received_at": utc_now(),
    }
    device_results_collection.insert_one(result_doc)

    device_tasks_collection.update_one(
        {"id": req.task_id, "device_id": req.device_id, "organisation_id": ORG_ID},
        {"$set": {"status": "completed", "completed_at": utc_now(), "updated_at": utc_now()}},
    )

    return {"message": "result accepted", "task_id": req.task_id}


@app.get("/tasks/{task_group_id}/results")
async def get_task_group_results(
    task_group_id: str,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    _validate_admin_key(x_admin_key)
    _validate_org(x_org_id)

    tasks = list(
        device_tasks_collection.find(
            {"task_group_id": task_group_id, "organisation_id": ORG_ID},
            {"_id": 0},
        )
    )
    if not tasks:
        raise HTTPException(status_code=404, detail="Task group not found")

    task_ids = [t["id"] for t in tasks]
    results = list(
        device_results_collection.find(
            {"task_id": {"$in": task_ids}, "organisation_id": ORG_ID},
            {"_id": 0},
        )
    )

    return {
        "task_group_id": task_group_id,
        "tasks": tasks,
        "results": results,
    }