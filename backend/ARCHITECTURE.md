# Backend architecture

The backend is a FastAPI application organised by responsibility rather than by deployment target. API modules own HTTP validation and response shapes; services own reusable work; persistence owns MongoDB setup and collection definitions.

```
backend/
  api/
    agents/       # device enrollment, scans, tasks, and agent installer
    cloud/        # cloud object discovery, PII scans, and requests
    identity/     # signup, sessions, organisations, membership, installers
  services/
    persistence/  # the one Mongo client, database, indexes, and collections
    cloud_storage/# S3 and mock-cloud adapters
    pii_detection.py
    pii.py
    remediation.py
  scripts/        # explicit, idempotent operational migrations
  main.py         # application composition and middleware
```

## Persistence rules

`services/persistence/mongo.py` is the only module that creates a MongoDB
client or exposes collections. Internal code must import collection names from
that module directly. `org_id` is the canonical tenant key; `organisation_id`
is retained only in records and API payloads that still require compatibility.

## Collection schema

All application records have a generated `id` where they are externally
addressable and should include `org_id` for tenant-scoped data.

| Collection | Purpose | Important fields / key |
| --- | --- | --- |
| `organizations` | Tenant configuration and connection secrets | `id` (unique), `name`, owner and enrollment/invite fields |
| `users` | User identity and password verifier | `id`, `email` (unique), password salt/hash |
| `org_memberships` | User access to an organization | `user_id`, `organisation_id`, `role`; unique pair |
| `sessions` | Revocable login sessions | `id`, `user_id`, `token` (unique), `revoked` |
| `data_sources` | Registered local devices and cloud connections | `id`, `org_id`, `source_type`, `source_key`; unique triple |
| `data_source_approval_requests` | Pending source enrollment approval | `org_id`, `data_source_id`, `status` |
| `scan_jobs` | Scan execution history | `id`, `org_id`, `data_source_id`, start/status fields |
| `pii_classifications` | PII findings for a source location/file | `id`, `org_id`, `data_source_id`, `location`, findings |
| `data_subject_requests` | Master correction, erasure, or access request | `id` (unique), `org_id`, principal, status, SLA timestamps |
| `request_tasks` | Per-source work created from a subject request | `request_id`, `data_source_id` (unique pair), status |
| `data_source_vulnerabilities` | Latest security findings per source | `org_id`, `data_source_id` (unique pair) |
| `redaction_records` | Evidence of a redaction/remediation operation | `id`, `org_id`, source/request links |
| `audit_logs` | Immutable-style activity trail | `org_id`, event/action fields, `created_at` |

`scripts/migrate_to_canonical_storage.py` is the one-way bridge for historical
Mongo collections. It is dry-run by default and never deletes legacy data.
