import hashlib
import hmac
import io
import os
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi import Request
from pydantic import BaseModel, EmailStr, Field

try:
    from services.combined.db import (
        org_memberships_collection,
        organizations_collection,
        sessions_collection,
        users_collection,
    )
except ImportError:
    from backend.services.combined.db import (
        org_memberships_collection,
        organizations_collection,
        sessions_collection,
        users_collection,
    )

router = APIRouter(prefix="/auth", tags=["auth-org"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    salt = secrets.token_bytes(16) if salt_hex is None else bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return salt.hex(), digest.hex()


def _verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, recalculated = _hash_password(password, salt_hex=salt_hex)
    return hmac.compare_digest(recalculated, digest_hex)


def _new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def _new_code(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"


def _new_admin_key() -> str:
    return _new_token("adm")


def _safe_user_doc(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "created_at": user.get("created_at"),
    }


def _list_user_organisations(user_id: str) -> list[dict]:
    memberships = list(
        org_memberships_collection.find(
            {"user_id": user_id},
            {
                "_id": 0,
                "organisation_id": 1,
                "organization_id": 1,
                "role": 1,
                "admin_api_key": 1,
                "admin_key": 1,
            },
        )
    )

    org_ids = [
        m.get("organisation_id") or m.get("organization_id")
        for m in memberships
        if (m.get("organisation_id") or m.get("organization_id"))
    ]
    orgs = list(organizations_collection.find({"id": {"$in": org_ids}}, {"_id": 0})) if org_ids else []
    org_map = {o["id"]: o for o in orgs}

    merged = []
    for m in memberships:
        membership_org_id = m.get("organisation_id") or m.get("organization_id")
        if not membership_org_id:
            continue

        org = org_map.get(membership_org_id)
        if not org:
            continue

        membership_admin_key = m.get("admin_api_key") or m.get("admin_key")
        if not membership_admin_key:
            membership_admin_key = _new_admin_key()
            org_memberships_collection.update_one(
                {
                    "user_id": user_id,
                    "$or": [
                        {"organisation_id": membership_org_id},
                        {"organization_id": membership_org_id},
                    ],
                },
                {"$set": {"admin_api_key": membership_admin_key}},
            )

        merged.append(
            {
                "id": org["id"],
                "name": org["name"],
                "role": m.get("role", "member"),
                "invite_code": org.get("invite_code"),
                "device_enrollment_code": org.get("device_enrollment_code"),
                "agent_token": org.get("agent_token"),
                "admin_api_key": membership_admin_key,
            }
        )

    return merged


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _agent_binary_path() -> Path:
    configured = os.getenv("AGENT_BINARY_PATH", "").strip()
    if configured:
        return Path(configured)
    return _project_root() / "agent-go" / "dpdp-agent.exe"


def _require_org_membership(user_id: str, organisation_id: str) -> dict:
    membership = org_memberships_collection.find_one(
        {"user_id": user_id, "organisation_id": organisation_id},
        {"_id": 0},
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this organisation")
    return membership


def _require_session(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.replace("Bearer ", "", 1).strip()
    session = sessions_collection.find_one({"token": token, "revoked": False}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    user = users_collection.find_one({"id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Session user not found")

    return user


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class JoinOrgRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=64)


class RotateDeviceCodeRequest(BaseModel):
    organisation_id: str


class RotateInviteCodeRequest(BaseModel):
    organisation_id: str


@router.post("/signup")
async def signup(req: SignupRequest):
    email = req.email.lower().strip()
    if users_collection.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="User already exists")

    salt_hex, password_hash = _hash_password(req.password)
    user_id = str(uuid4())

    users_collection.insert_one(
        {
            "id": user_id,
            "email": email,
            "name": req.name.strip(),
            "password_hash": password_hash,
            "password_salt": salt_hex,
            "created_at": utc_now(),
        }
    )

    user = users_collection.find_one({"id": user_id}, {"_id": 0})
    return {"user": _safe_user_doc(user)}


@router.post("/login")
async def login(req: LoginRequest):
    email = req.email.lower().strip()
    user = users_collection.find_one({"email": email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _verify_password(req.password, user["password_salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _new_token("sess")
    sessions_collection.insert_one(
        {
            "id": str(uuid4()),
            "user_id": user["id"],
            "token": token,
            "revoked": False,
            "created_at": utc_now(),
        }
    )

    memberships = list(
        org_memberships_collection.find({"user_id": user["id"]}, {"_id": 0, "organisation_id": 1, "role": 1})
    )
    organisations = _list_user_organisations(user["id"])

    return {
        "token": token,
        "user": _safe_user_doc(user),
        "memberships": memberships,
        "organisations": organisations,
    }


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.replace("Bearer ", "", 1).strip()
    sessions_collection.update_many({"token": token, "revoked": False}, {"$set": {"revoked": True}})
    return {"message": "logged out"}


@router.post("/organisations/create")
async def create_organisation(
    req: CreateOrgRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _require_session(authorization)

    org_id = str(uuid4())
    invite_code = _new_code("JOIN")
    device_enrollment_code = _new_code("DEVICE")
    agent_token = _new_token("agt")
    org_admin_api_key = _new_admin_key()
    owner_admin_api_key = _new_admin_key()

    organizations_collection.insert_one(
        {
            "id": org_id,
            "name": req.name.strip(),
            "owner_user_id": user["id"],
            "invite_code": invite_code,
            "device_enrollment_code": device_enrollment_code,
            "agent_token": agent_token,
            "admin_api_key": org_admin_api_key,
            "created_at": utc_now(),
        }
    )

    org_memberships_collection.update_one(
        {"user_id": user["id"], "organisation_id": org_id},
        {
            "$set": {
                "user_id": user["id"],
                "organisation_id": org_id,
                "role": "owner",
                "admin_api_key": owner_admin_api_key,
                "joined_at": utc_now(),
            }
        },
        upsert=True,
    )

    return {
        "organisation": {
            "id": org_id,
            "name": req.name.strip(),
            "invite_code": invite_code,
            "device_enrollment_code": device_enrollment_code,
            "admin_api_key": owner_admin_api_key,
            "agent_token": agent_token,
        }
    }


@router.post("/organisations/join")
async def join_organisation(
    req: JoinOrgRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _require_session(authorization)
    code = req.invite_code.strip().upper()

    org = organizations_collection.find_one({"invite_code": code}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    existing_membership = org_memberships_collection.find_one(
        {"user_id": user["id"], "organisation_id": org["id"]},
        {"_id": 0, "role": 1, "admin_api_key": 1},
    )
    role = (existing_membership or {}).get("role") or "member"
    admin_api_key = (existing_membership or {}).get("admin_api_key") or _new_admin_key()

    org_memberships_collection.update_one(
        {"user_id": user["id"], "organisation_id": org["id"]},
        {
            "$set": {
                "user_id": user["id"],
                "organisation_id": org["id"],
                "role": role,
                "admin_api_key": admin_api_key,
                "joined_at": utc_now(),
            }
        },
        upsert=True,
    )

    # Treat invite code as one-time-like by rotating immediately after successful join.
    next_invite_code = _new_code("JOIN")
    organizations_collection.update_one(
        {"id": org["id"]},
        {"$set": {"invite_code": next_invite_code}},
    )

    return {
        "organisation": {
            "id": org["id"],
            "name": org["name"],
            "device_enrollment_code": org.get("device_enrollment_code"),
            "next_invite_code": next_invite_code,
            "admin_api_key": admin_api_key,
            "agent_token": org.get("agent_token"),
        }
    }


@router.get("/organisations/mine")
async def my_organisations(authorization: Optional[str] = Header(default=None)):
    user = _require_session(authorization)
    return {"organisations": _list_user_organisations(user["id"])}


@router.post("/organisations/rotate-device-code")
async def rotate_device_code(
    req: RotateDeviceCodeRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _require_session(authorization)
    membership = _require_org_membership(user["id"], req.organisation_id)
    if not membership or membership.get("role") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only org owner/admin can rotate device code")

    new_code = _new_code("DEVICE")
    organizations_collection.update_one(
        {"id": req.organisation_id},
        {"$set": {"device_enrollment_code": new_code}},
    )

    return {"organisation_id": req.organisation_id, "device_enrollment_code": new_code}


@router.post("/organisations/rotate-invite-code")
async def rotate_invite_code(
    req: RotateInviteCodeRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _require_session(authorization)
    membership = _require_org_membership(user["id"], req.organisation_id)
    if not membership or membership.get("role") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only org owner/admin can rotate invite code")

    new_code = _new_code("JOIN")
    organizations_collection.update_one(
        {"id": req.organisation_id},
        {"$set": {"invite_code": new_code}},
    )

    return {"organisation_id": req.organisation_id, "invite_code": new_code}


@router.get("/organisations/{organisation_id}/installer")
async def download_org_installer(
    organisation_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    user = _require_session(authorization)
    membership = _require_org_membership(user["id"], organisation_id)
    if membership.get("role") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only org owner/admin can download installer package")

    org = organizations_collection.find_one({"id": organisation_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    api_base = str(request.base_url).rstrip("/")
    agent_binary = _agent_binary_path()
    if not agent_binary.exists() or not agent_binary.is_file():
        raise HTTPException(
            status_code=500,
            detail="Prebuilt agent binary not found. Set AGENT_BINARY_PATH or place dpdp-agent.exe in agent-go/.",
        )

    script_text = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path",
            "if (-not (Test-Path (Join-Path $scriptRoot 'dpdp-agent.exe'))) {",
            "  Write-Error 'dpdp-agent.exe not found in the installer folder.'",
            "  exit 1",
            "}",
            "Add-Type -AssemblyName System.Windows.Forms",
            "$defaultScanPath = Join-Path $env:USERPROFILE 'Documents'",
            "$folderBrowser = New-Object System.Windows.Forms.FolderBrowserDialog",
            "$folderBrowser.Description = 'Select folders to scan for sensitive data'",
            "$folderBrowser.SelectedPath = $defaultScanPath",
            "$folderBrowser.ShowNewFolderButton = $false",
            "$result = $folderBrowser.ShowDialog()",
            "if ($result -eq [System.Windows.Forms.DialogResult]::OK) {",
            "  $scanPaths = @($folderBrowser.SelectedPath)",
            "} else {",
            "  $scanPaths = @($defaultScanPath)",
            "}",
            "$scanPathsValue = [string]::Join(',', $scanPaths)",
            "$envLines = @(",
            f"  \"SERVER_URL={api_base}\"",
            f"  \"API_KEY={org.get('agent_token', '')}\"",
            f"  \"ORG_ID={org['id']}\"",
            "  \"POLL_INTERVAL=30s\"",
            "  \"SCAN_PATHS=$scanPathsValue\"",
            "  \"INCLUDE_EXTENSIONS=*\"",
            "  \"MAX_FILE_SIZE_MB=5\"",
            "  \"REGISTER_PATH=/devices/register\"",
            "  \"TASKS_PATH=/devices/tasks\"",
            "  \"RESULTS_PATH=/results\"",
            ")",
            "Set-Content -Path (Join-Path $scriptRoot '.env') -Value ($envLines -join \"`n\") -Encoding ASCII",
            "Write-Host \"Saved scan paths: $scanPathsValue\"",
            "Write-Host 'Launching DPDP agent for configured organisation...'",
            "& (Join-Path $scriptRoot 'dpdp-agent.exe')",
            "",
        ]
    )

    bat_text = "\n".join(
        [
            "@echo off",
            "PowerShell -NoProfile -ExecutionPolicy Bypass -File \"%~dp0install.ps1\"",
            "pause",
            "",
        ]
    )

    readme_text = "\n".join(
        [
            "DPDP Agent Installer Package",
            "",
            "This package is organisation scoped.",
            "",
            "Files:",
            "- install.bat: Windows launcher that runs install.ps1",
            "- install.ps1: bootstrap launcher script",
            "- dpdp-agent.exe: prebuilt executable with generic config support",
            "",
            "Install:",
            "1. Unzip this package on the company endpoint.",
            "2. Run install.bat or right-click install.ps1 and choose Run with PowerShell.",
            "3. Select one folder when prompted.",
            "",
            "Security:",
            "- Keep this package internal to your organisation.",
            "- Rotate org agent token if package is exposed.",
            "",
        ]
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("install.ps1", script_text)
        zf.writestr("install.bat", bat_text)
        zf.writestr("README.txt", readme_text)

        zf.write(agent_binary, arcname="dpdp-agent.exe")

    zip_buffer.seek(0)
    filename = f"dpdp-agent-{organisation_id}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)
