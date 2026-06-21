from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException

from .auth import _resolve_org_id, _validate_agent_auth, _validate_admin_key, _get_org_or_fail
from .helpers import utc_now, _as_utc, _is_device_active, _with_device_activity
from .models import DeviceRegisterRequest, DeviceApprovalRequest, DeviceHeartbeatRequest

try:
    from services.local.local_db import (
        device_approval_requests_collection,
        device_results_collection,
        devices_collection,
    )
except ImportError:
    from backend.services.local.local_db import (
        device_approval_requests_collection,
        device_results_collection,
        devices_collection,
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
            "$setOnInsert": {"id": str(uuid4()), "created_at": now},
        },
        upsert=True,
    )


@router.post("/devices/register")
async def register_device(
    req: DeviceRegisterRequest,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, req.organisation_id)
    _validate_agent_auth(authorization, org_id)

    existing = devices_collection.find_one(
        {"device_id": req.device_id, "organisation_id": org_id}
    )
    approved = bool(existing.get("approved", False)) if existing else False

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
            "$setOnInsert": {"created_at": utc_now(), "organisation_id": org_id},
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
    return {"devices": [_with_device_activity(d) for d in devices]}


@router.get("/organisations/{organisation_id}/devices")
async def list_devices_for_organisation(organisation_id: str):
    org = _get_org_or_fail(organisation_id)
    devices = list(
        devices_collection.find({"organisation_id": org["id"]}, {"_id": 0}).sort("updated_at", -1)
    )
    return {
        "organisation": {"id": org["id"], "name": org.get("name", "")},
        "devices": [_with_device_activity(d) for d in devices],
    }


@router.post("/devices/heartbeat")
async def heartbeat_device(
    req: DeviceHeartbeatRequest,
    organisation_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_agent_auth(authorization, org_id)
    _get_registered_device_or_fail(req.device_id, org_id)

    now = utc_now()
    devices_collection.update_one(
        {"device_id": req.device_id, "organisation_id": org_id},
        {"$set": {"last_seen": now, "updated_at": now}},
    )
    return {
        "device_id": req.device_id,
        "activity_status": "active",
        "is_active": True,
        "last_seen": now,
        "active_window_seconds": 180,
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

    new_status = "approved" if req.approved else "rejected"
    device_approval_requests_collection.update_many(
        {"device_id": req.device_id, "organisation_id": org_id, "status": "pending"},
        {"$set": {"status": new_status, "resolved_at": utc_now(), "updated_at": utc_now()}},
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


@router.get("/devices/scan-reports/daily")
async def list_device_daily_scan_reports(
    organisation_id: Optional[str] = None,
    date: Optional[str] = None,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    target_day = utc_now().date()
    if date:
        try:
            target_day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format; expected YYYY-MM-DD")

    day_start = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    devices = list(
        devices_collection.find(
            {"organisation_id": org_id},
            {"_id": 0, "device_id": 1, "hostname": 1, "approved": 1},
        )
    )
    if not devices:
        return {"date": target_day.isoformat(), "reports": []}

    device_ids = [d.get("device_id") for d in devices if d.get("device_id")]
    daily_results = list(
        device_results_collection.find(
            {
                "organisation_id": org_id,
                "result_scope": "standalone",
                "device_id": {"$in": device_ids},
                "updated_at": {"$gte": day_start, "$lt": day_end},
            },
            {"_id": 0, "device_id": 1, "status": 1, "updated_at": 1, "scanned_files": 1, "matches": 1},
        ).sort("updated_at", -1)
    )

    latest_by_device = {}
    for result in daily_results:
        key = result.get("device_id")
        if key and key not in latest_by_device:
            latest_by_device[key] = result

    reports = []
    for device in devices:
        device_id = device.get("device_id", "")
        result = latest_by_device.get(device_id)
        matches = result.get("matches", []) if result else []
        pii_types = sorted({m.get("type", "") for m in matches if m.get("type")})
        is_active = _is_device_active(device.get("last_seen"))

        reports.append({
            "device_id": device_id,
            "hostname": device.get("hostname", ""),
            "approved": bool(device.get("approved", False)),
            "is_active": is_active,
            "activity_status": "active" if is_active else "inactive",
            "last_seen": device.get("last_seen"),
            "scanned_today": result is not None,
            "last_scan_at": result.get("updated_at") if result else None,
            "status": result.get("status", "not_scanned") if result else "not_scanned",
            "scanned_files": result.get("scanned_files", 0) if result else 0,
            "matches_count": len(matches),
            "pii_types": pii_types,
        })

    reports.sort(key=lambda r: (not r.get("scanned_today", False), r.get("device_id", "")))
    return {"date": target_day.isoformat(), "reports": reports}