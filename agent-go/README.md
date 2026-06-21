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

## Run

From this folder:

```bash
go run ./cmd/agent
```

## Build

```bash
go build -o dpdp-agent.exe ./cmd/agent
```

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
