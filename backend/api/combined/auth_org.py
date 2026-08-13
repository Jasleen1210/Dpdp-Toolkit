import asyncio
import hashlib
import hmac
import io
import logging
import os
import secrets
import shutil
import subprocess
import tempfile
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



def _agent_source_root() -> Path:
    configured = os.getenv("AGENT_SOURCE_PATH", "").strip()
    return Path(configured) if configured else _project_root() / "agent-go"
 
 
def _installer_script_path(name: str) -> Path:
    return _agent_source_root() / name
 
 
# Prebuilt binaries shipped in the installer package, per target. The first
# existing candidate wins, so a single-platform deployment still works.
_AGENT_BINARY_CANDIDATES = {
    ("windows", "amd64"): ("AGENT_BINARY_PATH", ["dpdp-agent-windows-amd64.exe", "dpdp-agent.exe"]),
    ("darwin", "amd64"): ("AGENT_BINARY_PATH_DARWIN_AMD64", ["dpdp-agent-darwin-amd64", "dpdp-agent"]),
    ("darwin", "arm64"): ("AGENT_BINARY_PATH_DARWIN_ARM64", ["dpdp-agent-darwin-arm64"]),
}
 
 
def _agent_binary_path(platform: str = "windows", arch: str = "amd64") -> Path:
    candidates = _AGENT_BINARY_CANDIDATES.get((platform, arch))
    if not candidates:
        raise HTTPException(status_code=400, detail=f"Unsupported target {platform}/{arch}")
 
    env_var, names = candidates
    configured = os.getenv(env_var, "").strip()
    if configured:
        return Path(configured)
 
    root = _agent_source_root()
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return root / names[0]

def _go_toolchain() -> Optional[str]:
    return shutil.which(os.getenv("GO_BINARY", "go"))

def _build_org_agent_binary(
    platform: str,
    arch: str,
    server_url: str,
    org_id: str,
    agent_token: str,
) -> Optional[bytes]:
    """Compile an agent with the org connection settings baked in via ldflags.
 
    Returns None when no Go toolchain is available, so the caller can fall back
    to the prebuilt binary plus a generated .env.
    """
    if os.getenv("AGENT_BUILD_ON_DOWNLOAD", "1") != "1":
        return None
 
    go_bin = _go_toolchain()
    source_root = _agent_source_root()
    if not go_bin or not (source_root / "go.mod").is_file():
        return None
 
    ldflags = " ".join(
        [
            f"-X dpdp-toolkit/agent-go/internal/config.BuiltServerURL={server_url}",
            f"-X dpdp-toolkit/agent-go/internal/config.BuiltOrgID={org_id}",
            f"-X dpdp-toolkit/agent-go/internal/config.BuiltAPIKey={agent_token}",
            "-s",
            "-w",
        ]
    )
    # Small instances (Render free tier: 0.1 CPU / 512 MB) get OOM-killed by a
    # parallel build, so keep the compiler single-threaded.
    env = {
        **os.environ,
        "GOOS": platform,
        "GOARCH": arch,
        "CGO_ENABLED": "0",
        "GOMAXPROCS": os.getenv("AGENT_BUILD_GOMAXPROCS", "1"),
    }
 
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "dpdp-agent"
        result = subprocess.run(
            [
                go_bin,
                "build",
                "-p",
                env["GOMAXPROCS"],
                "-trimpath",
                "-ldflags",
                ldflags,
                "-o",
                str(output),
                "./cmd/agent",
            ],
            cwd=str(source_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("AGENT_BUILD_TIMEOUT", "300")),
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Agent build failed for {platform}/{arch}: {result.stderr.strip()[-500:]}",
            )
        return output.read_bytes()

async def _build_org_agent_binary_async(*args) -> Optional[bytes]:
    """Run the build off the event loop; a blocking build starves health checks.
 
    A failed or too-slow build degrades to the prebuilt binary rather than the
    whole download failing.
    """
    try:
        return await asyncio.to_thread(_build_org_agent_binary, *args)
    except (subprocess.SubprocessError, OSError, HTTPException) as exc:
        logging.warning("per-org agent build failed, using prebuilt binary: %s", exc)
        return None
 
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


def _zip_write_executable(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname)
    info.external_attr = 0o755 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)

def _add_windows_installer(
    zf: zipfile.ZipFile,
    api_base: str,
    org_id: str,
    agent_token: str,
    agent_binary: bytes,
) -> None:
    script_path = _installer_script_path("install.ps1")
    if not script_path.is_file():
        raise HTTPException(
            status_code=500,
            detail="install.ps1 not found. Set AGENT_SOURCE_PATH to the agent-go folder.",
        )
    
    # install.ps1 reads the org connection settings from the environment, so the
    # launcher injects them before handing over to the shared installer.
    bat_text = "\n".join(
        [
            "@echo off",
            f'set "SERVER_URL={api_base}"',
            f'set "API_KEY={agent_token}"',
            f'set "ORG_ID={org_id}"',
            'PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"',
            "pause",
            "",
        ]
    )

    readme_text = "\n".join(
        [
            "DPDP Agent Installer Package (Windows)",
            "",
            "This package is organisation scoped.",
            "",
            "Files:",
            "- install.bat: launcher that injects org settings and runs install.ps1",
            "- install.ps1: installer that writes .env and registers the background service",
            "- dpdp-agent.exe: the agent executable",
            "",
            "Install:",
            "1. Unzip this package on the endpoint.",
            "2. Run install.bat (right-click > Run as administrator to register a Windows Service;",
            "   without admin rights it registers a per-user scheduled task instead).",
            "3. Select one folder when prompted.",
            "",
            "The agent then runs in the background and restarts after reboot. Manage it with:",
            "  %LOCALAPPDATA%\\DPDPAgent\\dpdp-agent.exe status | stop | start | uninstall",
            "",
            "Security:",
            "- Keep this package internal to your organisation.",
            "- Rotate the org agent token if the package is exposed.",
            "",
        ]
    )
 
    zf.writestr("install.ps1", script_path.read_text(encoding="utf-8"))
    zf.writestr("install.bat", bat_text)
    zf.writestr("README.txt", readme_text)
    zf.writestr("dpdp-agent.exe", agent_binary)
 
 
def _add_macos_installer(
    zf: zipfile.ZipFile,
    api_base: str,
    org_id: str,
    agent_token: str,
    agent_binary: bytes,
) -> None:
    script_path = _installer_script_path("install.command")
    if not script_path.is_file():
        raise HTTPException(
            status_code=500,
            detail="install.command not found. Set AGENT_SOURCE_PATH to the agent-go folder.",
        )
 
    # Same pattern as install.bat: export the org settings, then hand over to the
    # shared installer, which prompts for the scan folder and loads the LaunchAgent.
    launcher_text = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'cd "$(dirname "${BASH_SOURCE[0]}")"',
            f'export SERVER_URL="{api_base}"',
            f'export API_KEY="{agent_token}"',
            f'export ORG_ID="{org_id}"',
            'export DPDP_AGENT_BINARY="$PWD/dpdp-agent"',
            "chmod +x ./dpdp-agent ./dpdp-install.sh",
            "xattr -dr com.apple.quarantine . 2>/dev/null || true",
            "codesign --force --sign - ./dpdp-agent 2>/dev/null || true",
            'exec bash ./dpdp-install.sh',
            "",
        ]
    )

    readme_text = "\n".join(
        [
            "DPDP Agent Installer Package (macOS)",
            "",
            "This package is organisation scoped.",
            "",
            "Files:",
            "- install.command: launcher that injects org settings and runs the installer",
            "- dpdp-install.sh: installer that writes .env and loads the LaunchAgent",
            "- dpdp-agent: the agent executable",
            "",
            "Install:",
            "1. Unzip this package.",
            "2. In Terminal, run:",
            "     cd <unzipped folder>",
            "     chmod +x install.command dpdp-install.sh dpdp-agent",
            "     ./install.command",
            "   (Or right-click install.command in Finder > Open > Open.)",
            "3. Choose the folder to scan when the picker appears.",
            "",
            "The agent is installed to ~/Library/Application Support/DPDPAgent and registered as a",
            "LaunchAgent (~/Library/LaunchAgents/dpdp-agent.plist) with RunAtLoad and KeepAlive, so it",
            "keeps running and starts again at login. Manage it with:",
            '  "$HOME/Library/Application Support/DPDPAgent/dpdp-agent" status | stop | start | uninstall',
            "",
            "Gatekeeper: the binary is unsigned. The installer clears the quarantine flag and ad-hoc",
            "signs the binary (Apple Silicon kills unsigned binaries at launch). If macOS still blocks",
            "it, open System Settings > Privacy & Security and click 'Open Anyway', then re-run.",
            "",
            "Security:",
            "- Keep this package internal to your organisation.",
            "- Rotate the org agent token if the package is exposed.",
            "",
        ]
    )
 
    _zip_write_executable(zf, "install.command", launcher_text.encode("utf-8"))
    _zip_write_executable(zf, "dpdp-install.sh", script_path.read_bytes())
    zf.writestr("README.txt", readme_text)
    _zip_write_executable(zf, "dpdp-agent", agent_binary)
 
 
@router.get("/organisations/{organisation_id}/installer")
async def download_org_installer(
    organisation_id: str,
    request: Request,
    platform: str = "windows",  # "windows" or "darwin"
    arch: str = "amd64",  # "amd64" or "arm64" (Apple Silicon)
    authorization: Optional[str] = Header(default=None),
):
    user = _require_session(authorization)
    # Any member of the org may download the installer: every enrolled device has
    # to run the agent for the org to see it.
    _require_org_membership(user["id"], organisation_id)
 
    org = organizations_collection.find_one({"id": organisation_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
 
    if platform not in {"windows", "darwin"}:
        raise HTTPException(status_code=400, detail="Unsupported platform")
 
    api_base = os.getenv("AGENT_SERVER_URL", "").strip() or str(request.base_url).rstrip("/")
    agent_token = org.get("agent_token", "")
    
    # Preferred path: compile per organisation so SERVER_URL/API_KEY/ORG_ID are
    # baked into the binary; the prebuilt binary + .env is the fallback.
    agent_bytes = await _build_org_agent_binary_async(
        platform, arch, api_base, org["id"], agent_token
    )
    if agent_bytes is None:
        binary_path = _agent_binary_path(platform, arch)
        if not binary_path.is_file():
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Prebuilt {platform}/{arch} agent binary not found at {binary_path.name}, "
                    "and no Go toolchain is available to build one. Run agent-go/build.sh or "
                    "set the matching AGENT_BINARY_PATH* variable."
                ),
            )
        agent_bytes = binary_path.read_bytes()
 
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if platform == "windows":
            _add_windows_installer(zf, api_base, org["id"], agent_token, agent_bytes)
        else:
            _add_macos_installer(zf, api_base, org["id"], agent_token, agent_bytes)

    zip_buffer.seek(0)
    suffix = "windows" if platform == "windows" else f"macos-{arch}"
    filename = f"dpdp-agent-{organisation_id}-{suffix}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)
