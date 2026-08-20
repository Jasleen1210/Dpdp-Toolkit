# Data Subject Request (DSR) Workflow Architecture

## Overview

DPDP processes Data Subject Requests across three infrastructure layers:

1. **Cloud Storage** (AWS S3, Azure Blob, GCP)
2. **Local Devices** (Agent-managed endpoints)
3. **Database** (PostgreSQL, MySQL, MongoDB)

All requests are **org-scoped** with strict data isolation.

---

## Request Lifecycle State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER SUBMITS REQUEST                         │
│                POST /requests (JSON payload)                    │
│                   Org-ID via header validation                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────────┐
                    │ Create Master   │
                    │ Doc in MongoDB  │
                    └──────┬──────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼─────┐   ┌───────▼────────┐  ┌──────▼──────┐
   │ DELETE?  │   │ Queue Local    │  │  Async Bg   │
   └────┬─────┘   │ Device Tasks   │  │  Processing │
        │         └─────────────────┘  │ (Cloud/DB)  │
   ┌────▼───────────────────┐          └──────┬──────┘
   │ Status:                │                 │
   │ AWAITING_APPROVAL      │          ┌──────▼─────────┐
   │ (User must confirm)    │          │ Background Job │
   └────┬───────────────────┘          │ Fetches request│
        │                              │ Scans sources  │
        │ User calls                   │ Stores results │
        │ POST /requests/{id}/approve  │ Updates master │
        │                              └──────┬─────────┘
   ┌────▼────────────────────┐               │
   │ Start cloud scanning    │◄──────────────┘
   │ (move to IN_PROGRESS)   │
   └────┬───────────────────┘
        │
     ┌──┴────────────────────────────────┐
     │                                   │
  ┌──▼──────────────────┐  ┌────────────▼──────┐
  │ Local Device Tasks  │  │ Cloud Results     │
  │ (request_tasks)     │  │ (pii_classif)     │
  │ status: pending     │  │ stored per file   │
  │ ↓ device polls      │  │ ↓ api stores      │
  │ status: in_progress │  │ status: completed │
  │ ↓ device finishes   │  │                   │
  │ status: completed   │  │                   │
  └──────────┬──────────┘  └────────┬──────────┘
             │                     │
             └──────────┬──────────┘
                        │
            ┌───────────▼──────────┐
            │ All tasks completed? │
            └───────────┬──────────┘
                        │
                   ┌────▼─────────┐
                   │ Status:      │
                   │ COMPLETED    │
                   │ closed_at ✓  │
                   └──────────────┘
```

---

## Data Storage Layout (MongoDB Collections)

```
┌─────────────────────────────────────────────────────────────────┐
│                   data_subject_requests                         │
│  Master orchestration doc per request                          │
│                                                                 │
│  {                                                              │
│    id: "req-uuid",                                              │
│    org_id: "org-123",  ◄─── CRITICAL: All queries filtered      │
│    identifier: "user@example.com",                              │
│    type: "delete" | "access" | "update",                        │
│    status: "pending" | "awaiting_approval" | "in_progress"      │
│    target_sources: ["cloud", "local", "db"],                    │
│    requires_approval: true,   ◄─── DELETE=true always           │
│    created_at: datetime,                                        │
│    updated_at: datetime,                                        │
│    cloud_results: [...],  ◄─── Summary of cloud findings        │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
                        │
             ┌──────────┴──────────┐
             │                    │
    ┌────────▼─────────┐ ┌───────▼──────────┐
    │ request_tasks    │ │ pii_classif      │
    │ One per local    │ │ One per cloud    │
    │ device per req   │ │ file per req     │
    │                  │ │                  │
    │ {                │ │ {                │
    │  id: "task-uuid" │ │  id: "class-id" │
    │  request_id: "x" │ │  request_id: "x"│
    │  org_id: "org-x" │ │  org_id: "org-x"│
    │  device_id: "d1" │ │  provider: "S3" │
    │  status: "pend"  │ │  file: "/path"  │
    │  created_at: ts  │ │  status: "done" │
    │  expires_at: ts  │ │  matches: [...]  │
    │ }                │ │ }                │
    │                  │ │                  │
    └──────────────────┘ └──────────────────┘
```

### Why This Layout?

1. **Single Source of Truth**: Master doc in `data_subject_requests` is always queried first
2. **Org Isolation**: Every doc has `org_id` field for filtering
3. **Task Tracking**: `request_tasks` (local) and `pii_classifications` (cloud) append results without modifying master
4. **Async Safety**: Background jobs can update cloud results independently of local progress

---

## Request Processing Flow: Cloud vs. Local vs. Database

### Cloud Storage Flow (Async, Background)

```
POST /requests (user submits)
    │
    ├─ Create master doc with status: PENDING
    │
    ├─ Schedule background task (if "cloud" in target_sources)
    │
    └─ Return immediately (< 50ms)

    ↓ [Background Job - Runs in parallel]

    └─ _run_async_processing()
       │
       ├─ List all connected cloud sources (AWS/Azure/GCP)
       │  From data_sources where source_type="cloud_storage"
       │
       ├─ For each cloud provider:
       │  ├─ Read files from cloud
       │  ├─ Detect PII using detect_pii_full()
       │  ├─ Store results in pii_classifications (per file)
       │  ├─ If DELETE: redact matching data
       │  └─ Update master_doc["cloud_results"]
       │
       └─ Update master_doc status: IN_PROGRESS → COMPLETED

    Result stored in: pii_classifications collection
    Keyed by: (request_id, org_id, file, provider)
```

### Local Device Flow (Sync + Async Polling)

```
POST /requests (user submits)
    │
    ├─ Create master doc with status: PENDING
    │
    ├─ Call _dispatch_local_device_tasks(org_id, device_ids)
    │  ├─ Query data_sources: {org_id, approved=true, type="local_device"}
    │  ├─ For each device: create request_task
    │  │  ├─ id: unique task ID
    │  │  ├─ device_id: which device to scan
    │  │  ├─ query: packed identifier+new_value
    │  │  ├─ status: "pending"
    │  │  └─ expires_at: task deadline
    │  └─ Insert into request_tasks
    │
    └─ Return immediately with task IDs

    ↓ [Device Agent - Polls independently]

    Device Agent:
    ├─ Polls GET /tasks?device_id=X
    ├─ Receives pending tasks
    ├─ Scans local filesystem for matches
    ├─ PUTs back task status: IN_PROGRESS
    ├─ (DELETE requests) redacts matching PII
    ├─ PUTs back task status: COMPLETED
    └─ Includes matches in response

    Result stored in: request_tasks collection
    Keyed by: (request_id, org_id, device_id)

    Master doc status derived from:
    ├─ All tasks == "completed" → Master = "COMPLETED"
    └─ Any task == "pending" or "in_progress" → Master = "IN_PROGRESS"
```

### Database Flow (Placeholder)

```
POST /requests (user submits)
    │
    ├─ Create master doc
    │
    ├─ If "db" in target_sources:
    │  └─ Call _dispatch_database_sources()
    │     └─ Currently: returns stub response
    │        (extensible for PostgreSQL, MySQL, MongoDB)
    │
    └─ Returns immediately

    Future Implementation:
    └─ Create database_queries collection
       ├─ One doc per database per request
       ├─ Query template: e.g. "DELETE FROM users WHERE email=?"
       ├─ Execute via database connection pooler
       └─ Store execution log (rows affected, errors)
```

---

## Endpoint Reference (Org-Scoped)

### 1. Create Request

```
POST /requests
Header: X-Org-Id: org-123
Header: Authorization: Bearer session-token

Body: {
  "type": "delete" | "access" | "update",
  "identifier": "user@example.com",
  "new_value": "masked@example.com",  // for type=update
  "target_sources": ["cloud", "local", "db"],
  "device_ids": ["device-1"],  // optional; if null, scan ALL org devices
  "expires_in_hours": 24
}

Response: {
  "status": "accepted",
  "request_id": "req-uuid",
  "overall_status": "pending" | "awaiting_approval",
  "local_tasks": [
    { "task_id": "...", "device_id": "device-1", "status": "pending" }
  ]
}
```

### 2. List Requests (Org-Scoped)

```
GET /requests
Header: X-Org-Id: org-123
Header: Authorization: Bearer session-token

Response: [
  {
    "id": "req-uuid",
    "type": "delete" | "access" | "update",
    "subject": "user@example.com",
    "status": "pending" | "in_progress" | "completed" | "awaiting_approval",
    "handler": "Cloud (AWS/Azure/GCP) | Local (device-1, device-2)",
    "created": "2026-08-17 14:30",
    "target_sources": ["cloud", "local"],
    "devices": ["device-1", "device-2"],
    "tasks_completed": 1,  // of total devices
  }
]
```

### 3. Get Request Details

```
GET /requests/{request-id}
Header: X-Org-Id: org-123
Header: Authorization: Bearer session-token

Response: {
  "request": { ...master doc... },
  "local_tasks": [
    {
      "task_id": "...",
      "device_id": "device-1",
      "status": "completed",
      "matches_count": 3,
      "pii_types": ["email", "phone"]
    }
  ],
  "cloud_results": [
    {
      "provider": "AWS S3",
      "bucket": "customers",
      "file": "customer_records.csv",
      "status": "completed",
      "pii_found": 5
    }
  ]
}
```

### 4. Approve Delete Request

```
POST /requests/{request-id}/approve
Header: X-Org-Id: org-123
Header: Authorization: Bearer session-token

Response: {
  "message": "Approved and executed.",
  "result": { ...deletion summary... }
}
```

### 5. List Cloud Sources (Org-Scoped)

```
GET /cloud/sources
Header: X-Org-Id: org-123
Header: Authorization: Bearer session-token

Response: {
  "sources": [
    {
      "id": "source-uuid",
      "provider": "AWS S3",
      "bucket": "customer-data",
      "region": "us-east-1",
      "auth_method": "role_arn",
      "status": "connected"
    }
  ]
}
```

---

## Security & Data Isolation Checklist

✅ **Authentication Layer**

- All endpoints require: `Authorization: Bearer {token}` header
- Token validated against `sessions` collection
- Revoked tokens rejected

✅ **Org-Level Isolation**

- All endpoints require: `X-Org-Id: {org-id}` header
- User membership verified: `org_memberships.find_one({user_id, org_id})`
- All MongoDB queries filtered by `org_id` or `organisation_id`

✅ **Request Scoping**

- Device scanning: Only approved devices of the org scanned
- Cloud sources: Only connected sources of the org accessed
- Results: Stored with request org_id for future filtering

✅ **Local Device Scanning (Safe by Default)**

- Devices are "approved" only after agent enrollment
- Device tasks only created for org's devices
- Device agent receives only its assigned tasks
- Tasks expire after `expires_at` timestamp

✅ **Cloud Source Isolation**

- IAM credentials stored but **never exposed** in API responses
- Only masked access keys returned (`AKIA...****`)
- Cloud scanning limited to org's connected sources

---

## Example: Delete Request End-to-End

```
1. Admin logs in → token obtained → belongs to org-123

2. Admin submits DSR:
   POST /requests
   X-Org-Id: org-123
   Body: {type: "delete", identifier: "user@acme.com", target_sources: ["all"]}

3. Backend:
   ├─ Validates user token & org membership
   ├─ Creates master doc: {id: req-1, org_id: "org-123", status: "awaiting_approval"}
   ├─ Creates tasks for org's 3 approved devices
   ├─ Schedules async cloud scanning
   └─ Returns: request_id=req-1, status=awaiting_approval

4. Admin reviews findings via GET /requests/req-1 (cloud pre-scanned)

5. Admin approves: POST /requests/req-1/approve

6. Backend:
   ├─ Updates: status: "in_progress"
   ├─ Signals cloud remediation (delete matching files)
   ├─ Waits for all device agents to complete tasks

7. Results accumulate:
   ├─ Device 1: 5 files redacted, task=completed
   ├─ Device 2: 2 files redacted, task=completed
   ├─ Device 3: 0 files found, task=completed
   ├─ Cloud: 3 files deleted from S3, 1 from GCP

8. Master doc: status=completed, closed_at=now, summary includes all results

9. Admin views final report: GET /requests/req-1
```

---

## Migration Checklist (Current → Secure)

- [ ] Add middleware.py with `resolve_org_context()` dependency
- [ ] Update all endpoint signatures: `ctx: OrgAuthContext = Depends(resolve_org_context)`
- [ ] Update all MongoDB queries: Add `org_id` filter
- [ ] Update `/requests` endpoint to use `RequestStateManager`
- [ ] Remove `/cloud/requests` endpoint (migrate to `/requests`)
- [ ] Update frontend to include `X-Org-Id` header on all requests
- [ ] Test: Verify users cannot access other org's data
- [ ] Test: Verify devices only scan for their org
- [ ] Test: Verify cloud sources only listed for their org
