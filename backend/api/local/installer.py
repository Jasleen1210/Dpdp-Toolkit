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


@router.get("/installer/download")
async def download_installer(
    organisation_id: Optional[str] = None,
    platform: str = "windows",  # "windows" or "darwin"
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

    # Determine output binary name and GOOS
    if platform == "windows":
        binary_name = f"dpdp-agent-{org_id[:8]}.exe"
        goos = "windows"
        goarch = "amd64"
    elif platform == "darwin":
        binary_name = f"dpdp-agent-{org_id[:8]}"
        goos = "darwin"
        goarch = "amd64"  # or "arm64" for M1/M2
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