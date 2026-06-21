from typing import Optional
from fastapi import HTTPException

try:
    from services.combined.db import org_memberships_collection, organizations_collection
except ImportError:
    from backend.services.combined.db import org_memberships_collection, organizations_collection


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
    return org_id


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

    member = org_memberships_collection.find_one(
        {
            "$and": [
                {"$or": [{"organisation_id": org["id"]}, {"organization_id": org["id"]}]},
                {"$or": [{"admin_api_key": admin_key}, {"admin_key": admin_key}]},
            ]
        },
        {"_id": 0, "user_id": 1},
    )
    if member:
        return

    expected_key = org.get("admin_api_key", "")
    if expected_key and admin_key == expected_key:
        return

    raise HTTPException(status_code=401, detail="Invalid admin key")