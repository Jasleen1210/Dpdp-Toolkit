from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, status

from backend.api.identity.auth_org import (
    _require_org_membership,
    _require_session,
)
from backend.api.db_api.models import DatabaseSourceCreate, DatabaseDataManageRequest, DatabaseMaskRequest
from backend.services.db.service import (
    DatabaseServiceError,
    DatabaseSourceNotFoundError,
    create_database_source,
    create_configured_supabase_source,
    list_database_findings,
    list_database_scan_runs,
    list_database_sources,
    scan_database_source,
    delete_update_database_source,
)

router = APIRouter(prefix="/database", tags=["database-discovery"])


def _model_to_dict(model) -> dict:
    """Works with both Pydantic v1 and v2, because requirements are not pinned."""
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)


def _require_database_member(authorization: Optional[str], organisation_id: str) -> dict:
    """Require a signed-in member of the organization for database access."""
    user = _require_session(authorization)
    _require_org_membership(user["id"], organisation_id)
    return user


@router.get("/sources")
async def get_sources(
    organisation_id: str,
    authorization: Optional[str] = Header(default=None),
):
    _require_database_member(authorization, organisation_id)
    return {"sources": list_database_sources(organisation_id)}


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def add_source(
    req: DatabaseSourceCreate,
    authorization: Optional[str] = Header(default=None),
):
    user = _require_database_member(authorization, req.organisation_id)
    try:
        source = create_database_source(
            organisation_id=req.organisation_id,
            user_id=user["id"],
            payload=_model_to_dict(req),
        )
        return {"source": source}
    except DatabaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/sources/configured-supabase", status_code=status.HTTP_201_CREATED)
async def add_configured_supabase_source(
    organisation_id: str,
    authorization: Optional[str] = Header(default=None),
):
    user = _require_database_member(authorization, organisation_id)

    try:
        source = create_configured_supabase_source(
            organisation_id=organisation_id,
            user_id=user["id"],
        )
        return {"source": source}

    except DatabaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/sources/{source_id}/scan")
async def scan_source(
    source_id: str,
    organisation_id: str,
    scan_auth: bool = Query(default=False),
    authorization: Optional[str] = Header(default=None),
):
    user = _require_database_member(authorization, organisation_id)
    try:
        return scan_database_source(
            organisation_id=organisation_id,
            source_id=source_id,
            user_id=user["id"],
            scan_auth=scan_auth,
        )
    except DatabaseSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabaseServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sources/{source_id}/findings")
async def get_findings(
    source_id: str,
    organisation_id: str,
    limit: int = Query(default=500, ge=1, le=1000),
    authorization: Optional[str] = Header(default=None),
):
    _require_database_member(authorization, organisation_id)
    try:
        return list_database_findings(
            organisation_id=organisation_id,
            source_id=source_id,
            limit=limit,
        )
    except DatabaseSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sources/{source_id}/runs")
async def get_scan_runs(
    source_id: str,
    organisation_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
):
    _require_database_member(authorization, organisation_id)
    try:
        return {
            "runs": list_database_scan_runs(
                organisation_id=organisation_id,
                source_id=source_id,
                limit=limit,
            )
        }
    except DatabaseSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sources/{source_id}/delete-update")
async def delete_update_source(
    source_id: str,
    organisation_id: str,
    req: DatabaseDataManageRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _require_database_member(authorization, organisation_id)
    try:
        return delete_update_database_source(
            organisation_id=organisation_id,
            source_id=source_id,
            user_id=user["id"],
            identifier=req.identifier,
            action=req.action,
            new_value=req.new_value,
        )
    except DatabaseSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sources/{source_id}/mask")
async def mask_source(
    source_id: str,
    organisation_id: str,
    req: DatabaseMaskRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Mask (not delete) rows matching `identifier`, using the same deterministic
    masking token algorithm as the local agent's delete-mask logic."""
    user = _require_database_member(authorization, organisation_id)
    try:
        return delete_update_database_source(
            organisation_id=organisation_id,
            source_id=source_id,
            user_id=user["id"],
            identifier=req.identifier,
            action="MASK",
            new_value=None,
        )
    except DatabaseSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabaseServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

