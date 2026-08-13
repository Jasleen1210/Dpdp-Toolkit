# DPDP Desktop Agent (Go)

A lightweight desktop agent for organization-managed laptops/desktops.

It supports:

- device registration with backend
- standalone 24-hour PII scans of selected directories
- local file scanning within allowed directories
- regex-based PII detection

## Why this stack now

Since your current platform already has React + Python backend, this agent extends it without changing your web stack:

- Dashboard: React (existing)
- Backend: FastAPI/Python (existing)
- Device agent: Go (this folder)

## Folder structure

- `cmd/agent/main.go`: app entrypoint
- `internal/config`: environment-based config
- `internal/client`: backend HTTP client
- `internal/scanner`: local file scanner
- `internal/pii`: regex-based PII detector
- `internal/types`: shared request/response models

## Expected backend APIs

The agent registers with the backend by default (all configurable):

1. `POST /devices/register`

### Suggested contracts

`POST /devices/register`

```json
{
  "device_id": "HOST-123",
  "hostname": "HOST-123",
  "agent_version": "0.1.0"
}
```

Optional registration payload stays the same. The agent now scans local files on its own schedule and logs any detected PII matches.

```json
{
  "device_id": "HOST-123",
  "hostname": "HOST-123",
  "agent_version": "0.1.0"
}
```

## Configuration

Set environment variables (see `.env.example`):

- `SERVER_URL` default: `http://localhost:8000`
- `API_KEY` default: empty (optional)
- `POLL_INTERVAL` default: `30s`
- `SCAN_INTERVAL` default: `24h`
- `ORG_ID` default: `dpdp-org`
- `DEVICE_ID` default: machine hostname
- `SCAN_PATHS` default:
  - `C:/Users`
- `INCLUDE_EXTENSIONS` default:
  - `*` (scan all file extensions)
- `MAX_FILE_SIZE_MB` default: `5`
- `REGISTER_PATH` default: `/devices/register`

## Install (end users)

Binaries and installers are published as **GitHub Release assets** — free, stable
download URLs, no premium distribution platform:
 
```
https://github.com/jasleen1210/dPDP-toolkit/releases/latest
```
 
### Windows
 
1. Download `dpdp-agent-windows-amd64.exe` and `install.ps1` into the same folder.
2. Right-click the `.exe` > Properties > **Unblock** (SmartScreen marks unsigned
   downloads). If SmartScreen shows "Windows protected your PC", click
   **More info > Run anyway**.
3. Run the installer (Administrator recommended, so it registers a real service):
 
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install.ps1
   ```
 
The installer copies the agent to `%LOCALAPPDATA%\DPDPAgent`, prompts for the
folder to scan, writes `.env`, and registers a **Windows Service** (`dpdp-agent`,
auto-start with restart-on-failure). Without Administrator rights it falls back
to a **Scheduled Task** (`DPDPAgent`) that runs at logon and restarts on failure.
 
### macOS
 
1. Download `dpdp-agent-darwin-arm64` (Apple Silicon) or `dpdp-agent-darwin-amd64`
   (Intel) and `install.command` into the same folder.
2. Make the installer executable and run it:
 
   ```bash
   chmod +x install.command && ./install.command
   ```
 
   (Or double-click `install.command` in Finder.)
 
The installer copies the agent to `~/Library/Application Support/DPDPAgent`,
clears the Gatekeeper quarantine flag (`xattr -d com.apple.quarantine`), ad-hoc
signs it (`codesign --force --sign -`, without which Apple Silicon kills the
cross-compiled binary at launch with `Killed: 9`), shows a native folder picker
(`osascript -e 'choose folder'`), writes `.env`, and installs
a **LaunchAgent** at `~/Library/LaunchAgents/dpdp-agent.plist` with `RunAtLoad`
and `KeepAlive` set, so the agent starts at login and is restarted if it exits.
 
If macOS still refuses to open the binary ("developer cannot be verified"), open
**System Settings > Privacy & Security > Open Anyway**, then re-run the installer.
 
## Service commands
 
The binary is both the agent and its own service manager:
 
```bash
dpdp-agent run        # foreground (default when no subcommand is given)
dpdp-agent install    # register + start the OS service (Windows Service / launchd / systemd)
dpdp-agent start
dpdp-agent stop
dpdp-agent status
dpdp-agent uninstall
```
 
`run` in an interactive terminal still prompts for a scan folder when only
default paths are configured; when running as a service it never prompts.
 
## How environment is configured
 
The org installer endpoint (`GET /auth/organisations/{id}/installer`) compiles a
fresh agent per download when a Go toolchain is present on the backend, baking
`SERVER_URL`/`API_KEY`/`ORG_ID` into the binary. Set `AGENT_BUILD_ON_DOWNLOAD=0`
to disable and ship the prebuilt binary instead; `AGENT_SERVER_URL` overrides the
URL that gets baked in when the request host is not reachable from endpoints.
 
Two supported flows:
 
1. **Install-time `.env`** — `install.ps1` / `install.command` prompt for the scan
   folder and write a `.env` next to the installed binary (`SERVER_URL`, `API_KEY`,
   `ORG_ID` are taken from the environment of the installer process if set). The
   agent loads `.env` from both the working directory and its own executable's
   directory, so the service picks it up without a shell.
2. **Download-time (build-time) ldflags** — values baked into the binary:
 
   ```bash
   SERVER_URL=https://api.example.com API_KEY=token ORG_ID=org123 ./build.sh
   ```
 
   which injects `-X dpdp-toolkit/agent-go/internal/config.BuiltServerURL=...`
   (and `BuiltAPIKey`, `BuiltOrgID`). This is what
   `backend/api/local/installer.py` does when an admin downloads a per-org agent
   from the dashboard — the resulting binary needs no `.env` for connectivity.
 
Built-in values take precedence over `.env`/environment variables.
 
## Run from source
 
```bash
go run ./cmd/agent
```
 
## Build
 
Single binary for the current platform:
 
```bash
go build -o dpdp-agent ./cmd/agent
```
 
All distributable binaries (`windows/amd64`, `darwin/amd64`, `darwin/arm64`) into `dist/`:
 
```bash
./build.sh
```
 
## Release
 
`.github/workflows/release.yml` cross-compiles every target and uploads the
binaries plus `install.ps1`, `install.command` and `SHA256SUMS.txt` to a GitHub
Release on any `v*` tag push (or manual `workflow_dispatch`):
 
```bash
git tag v0.1.0 && git push origin v0.1.0
```
 
Optional repository variables `AGENT_SERVER_URL` / `AGENT_ORG_ID` and secret
`AGENT_API_KEY` are baked into the released binaries when set.
 
## Security notes

- always use HTTPS in production
- set `DEVICE_SHARED_TOKEN` in backend and use it as agent `API_KEY`
- set matching `ORG_ID` in backend and agent
- approve devices via admin API before they can pull scan tasks
- avoid uploading raw PII where possible; this agent masks matches before upload
- restrict `SCAN_PATHS` to approved directories per policy

## Multi-format text extraction

The agent now extracts text from:

- plain text and structured text files (`.txt`, `.csv`, `.json`, etc.)
- PDF (`.pdf`) via native text extraction
- Office/OpenDocument zip-based formats (`.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`) via XML text extraction
- unknown/binary files via printable-strings fallback

Note: binary-heavy formats may produce noisy text; results should be treated as discovery leads and validated in context.

## Next step for your current system

1. Add the device registration endpoint in your Python service if you want inventory tracking.
2. Restrict `SCAN_PATHS` to approved folders before deploying on endpoints.
3. If you later want central tasking, you can layer that back on without changing the scanner itself.
