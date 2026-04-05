# DPDP Desktop Agent (Go)

A lightweight desktop agent for organization-managed laptops/desktops.

It supports:

- device registration with backend
- polling for search tasks
- local file scanning within allowed directories
- regex-based PII detection
- result upload back to backend

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

The agent expects these endpoints by default (all configurable):

1. `POST /devices/register`
2. `GET /devices/tasks?device_id=<id>`
3. `POST /results`

### Suggested contracts

`POST /devices/register`

```json
{
  "device_id": "HOST-123",
  "hostname": "HOST-123",
  "agent_version": "0.1.0"
}
```

`GET /devices/tasks?device_id=HOST-123`

Supported response formats:

```json
[
  {
    "id": "task-1",
    "query": "invoice_2024",
    "expires_at": "2026-04-07T12:00:00Z",
    "paths": ["C:/Users/Public/Documents"]
  }
]
```

or

```json
{
  "tasks": [
    {
      "id": "task-1",
      "query": "invoice_2024",
      "expires_at": "2026-04-07T12:00:00Z",
      "paths": ["C:/Users/Public/Documents"]
    }
  ]
}
```

`POST /results`

```json
{
  "task_id": "task-1",
  "device_id": "HOST-123",
  "status": "completed",
  "scanned_files": 120,
  "matches": [
    {
      "type": "EMAIL",
      "value": "ra***@example.com",
      "file": "C:/Users/Public/Documents/customers.txt"
    }
  ]
}
```

## Configuration

Set environment variables (see `.env.example`):

- `SERVER_URL` default: `http://localhost:8000`
- `API_KEY` default: empty (optional)
- `POLL_INTERVAL` default: `5m`
- `ORG_ID` default: `dpdp-org`
- `DEVICE_ID` default: machine hostname
- `SCAN_PATHS` default:
  - `C:/Users`
- `INCLUDE_EXTENSIONS` default:
  - `*` (scan all file extensions)
- `MAX_FILE_SIZE_MB` default: `5`
- `REGISTER_PATH` default: `/devices/register`
- `TASKS_PATH` default: `/devices/tasks`
- `RESULTS_PATH` default: `/results`

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

1. Add the 3 backend endpoints above in your Python service.
2. Start with polling mode (already implemented here).
3. Keep task `expires_at` within 24 hours and reject stale results server-side.
4. When scale grows, migrate distribution from polling to MQTT/WebSockets.
