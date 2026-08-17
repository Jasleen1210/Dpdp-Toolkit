"""
Org-level authentication and authorization middleware.
Enforces org-level data isolation and validates user permissions.
"""
from typing import Optional
from fastapi import HTTPException, Header
from backend.services.persistence.mongo import (
    sessions as sessions_collection,
    users as users_collection,
    org_memberships as org_memberships_collection,
)


class OrgAuthContext:
    """
    Context object passed through request lifecycle to enforce org-level isolation.
    Ensures all data operations are scoped to authenticated org.
    """
    def __init__(self, org_id: str, user_id: str, role: str):
        self.org_id = org_id
        self.user_id = user_id
        self.role = role  # "owner", "admin", "member"
    
    def is_admin_or_owner(self) -> bool:
        return self.role in {"owner", "admin"}


def _resolve_session_token(authorization: Optional[str]) -> tuple[str, dict]:
    """
    Validates bearer token and returns (token, user_doc).
    Raises HTTPException if invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "", 1).strip()
    
    session = sessions_collection.find_one(
        {"token": token, "revoked": False},
        {"_id": 0}
    )
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or revoked session token")
    
    user = users_collection.find_one({"id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return token, user


def resolve_org_context(
    authorization: Optional[str] = Header(None),
    x_org_id: Optional[str] = Header(None, alias="X-Org-Id"),
) -> OrgAuthContext:
    """
    Validates bearer token and X-Org-Id header, ensures user is member of org.
    Returns OrgAuthContext for secure org-scoped operations.
    
    Usage:
        @router.get("/some-endpoint")
        async def my_endpoint(ctx: OrgAuthContext = Depends(resolve_org_context)):
            # All operations now scoped to ctx.org_id
            results = collection.find({"org_id": ctx.org_id})
    """
    token, user = _resolve_session_token(authorization)
    
    if not x_org_id:
        raise HTTPException(status_code=400, detail="X-Org-Id header is required")
    
    org_id = x_org_id.strip()
    
    # Verify user is member of requested org
    membership = org_memberships_collection.find_one(
        {
            "user_id": user["id"],
            "$or": [
                {"organisation_id": org_id},
                {"organization_id": org_id},
            ]
        },
        {"_id": 0}
    )
    
    if not membership:
        raise HTTPException(
            status_code=403,
            detail=f"User {user['email']} is not a member of organization {org_id}"
        )
    
    role = membership.get("role", "member").lower()
    return OrgAuthContext(org_id=org_id, user_id=user["id"], role=role)


def resolve_org_context_optional(
    authorization: Optional[str] = Header(None),
    x_org_id: Optional[str] = Header(None, alias="X-Org-Id"),
) -> Optional[OrgAuthContext]:
    """
    Optional version of resolve_org_context. Returns None if auth fails gracefully.
    Useful for endpoints that support both authenticated and unauthenticated access.
    """
    try:
        return resolve_org_context(authorization, x_org_id)
    except HTTPException:
        return None
