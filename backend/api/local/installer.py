# installer.py
import os
import subprocess
import tempfile
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse

from .auth import _resolve_org_id, _validate_admin_key, _get_org_or_fail

router = APIRouter()

# Path to your agent-go source on the server
AGENT_SOURCE_PATH = os.getenv("AGENT_SOURCE_PATH", "/app/agent-go")
SERVER_URL = os.getenv("SERVER_URL", "https://your-backend.com")


SUPPORTED_ARCHS = {"amd64", "arm64"}
 
# Installer scripts shipped alongside the agent source; they prompt for the scan
# folder, write the .env and register the background service.
INSTALL_SCRIPTS = {
    "windows": "install.ps1",
    "darwin": "install.command",
}

@router.get("/installer/script")
async def download_install_script(
    organisation_id: Optional[str] = None,
    platform: str = "windows",  # "windows" or "darwin"
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)
 
    script_name = INSTALL_SCRIPTS.get(platform)
    if not script_name:
        raise HTTPException(status_code=400, detail="Unsupported platform")
 
    script_path = os.path.join(AGENT_SOURCE_PATH, script_name)
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=500, detail=f"{script_name} not found on server")
 
    return FileResponse(
        path=script_path,
        filename=script_name,
        media_type="text/plain",
    )
 
@router.get("/installer/download")
async def download_installer(
    organisation_id: Optional[str] = None,
    platform: str = "windows",  # "windows" or "darwin"
    arch: str = "amd64",  # "amd64" or "arm64" (Apple Silicon)
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    x_org_id: Optional[str] = Header(default=None, alias="X-Org-Id"),
):
    org_id = _resolve_org_id(x_org_id, organisation_id)
    _validate_admin_key(x_admin_key, org_id)

    # Fetch the org's agent token from DB
    org = _get_org_or_fail(org_id)
    agent_token = org.get("agent_token", "")
    if not agent_token:
        raise HTTPException(status_code=500, detail="Org has no agent token configured")
    
    if arch not in SUPPORTED_ARCHS:
        raise HTTPException(status_code=400, detail="Unsupported architecture")
 
    # Determine output binary name and GOOS
    if platform == "windows":
        binary_name = f"dpdp-agent-{org_id[:8]}.exe"
        goos = "windows"
        goarch = "amd64"
    elif platform == "darwin":
        binary_name = f"dpdp-agent-{org_id[:8]}"
        goos = "darwin"
        goarch = arch
    else:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    # Build into a temp file
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, binary_name)

        ldflags = (
            f"-X dpdp-toolkit/agent-go/internal/config.BuiltServerURL={SERVER_URL} "
            f"-X dpdp-toolkit/agent-go/internal/config.BuiltOrgID={org_id} "
            f"-X dpdp-toolkit/agent-go/internal/config.BuiltAPIKey={agent_token}"
        )

        env = os.environ.copy()
        env["GOOS"] = goos
        env["GOARCH"] = goarch
        env["CGO_ENABLED"] = "0"  # Required for cross-compilation

        result = subprocess.run(
            [
                "go", "build",
                "-trimpath",
                "-ldflags", ldflags,
                "-o", output_path,
                "./cmd/agent",
            ],
            cwd=AGENT_SOURCE_PATH,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,  # 2 min build timeout
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Build failed: {result.stderr}"
            )

        return FileResponse(
            path=output_path,
            filename=binary_name,
            media_type="application/octet-stream",
        )