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
client. It exposes a single database (`db`, name from `DPDP_DB_NAME`, default
`dpdp_platform`) that holds **every** collection used by the app — there is no
second Mongo database. `services/db/db.py` (database-engine discovery) reuses
that same `db` instead of opening its own; it only defines a few extra
collections because their document shape differs from the generic ones.
Internal code must import collection names from `services/persistence/mongo.py`
(or `services/db/db.py` for the database-discovery collections) directly.
`org_id` is the canonical tenant key; `organisation_id` is retained only in
records and API payloads that still require compatibility.

## Collection schema

All application records have a generated `id` where they are externally
addressable and should include `org_id` for tenant-scoped data. Collections
are grouped by responsibility rather than by which feature added them:

**Identity**

| Collection        | Purpose                                     | Important fields / key                                    |
| ----------------- | ------------------------------------------- | --------------------------------------------------------- |
| `organizations`   | Tenant configuration and connection secrets | `id` (unique), `name`, owner and enrollment/invite fields |
| `users`           | User identity and password verifier         | `id`, `email` (unique), password salt/hash                |
| `org_memberships` | User access to an organization              | `user_id`, `organisation_id`, `role`; unique pair         |
| `sessions`        | Revocable login sessions                    | `id`, `user_id`, `token` (unique), `revoked`              |

**Sources** (one registry per source category — the connection shape differs enough to keep them separate)

| Collection                               | Purpose                                                        | Important fields / key                                                                      |
| ---------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `data_sources`                           | Registered local devices and cloud connections                 | `id`, `org_id`, `source_type` (`local_device`/`cloud_storage`), `source_key`; unique triple |
| `data_source_approval_requests`          | Pending source enrollment approval                             | `org_id`, `data_source_id`, `status`                                                        |
| `data_source_vulnerabilities`            | Latest security findings per source                            | `org_id`, `data_source_id` (unique pair)                                                    |
| `database_sources` (`services/db/db.py`) | Registered database-engine connections (Postgres, SQLite, ...) | `id`, `organisation_id`, `config` (engine + connection details, no raw password)            |

**Scan runs** (segregated per source category since local agent cron logs, cloud scans, and database scans each have different fields)

| Collection                                 | Purpose                                          | Important fields / key                                    |
| ------------------------------------------ | ------------------------------------------------ | --------------------------------------------------------- |
| `agent_scan_logs`                          | Local agent/device cron & scan execution history | `id`, `org_id`, `data_source_id`, start/status fields     |
| `cloud_scan_logs`                          | Cloud storage scan execution history             | `id`, `org_id`, `started_at`, `result_summary`            |
| `database_scan_runs` (`services/db/db.py`) | Database-engine scan execution history           | `id`, `organisation_id`, `source_id`, `status`, `summary` |

**Findings**

| Collection                                | Purpose                                                | Important fields / key                                                             |
| ----------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `pii_classifications`                     | PII findings for a local/cloud source location or file | `id`, `org_id`, `data_source_id`, `location`, findings                             |
| `database_findings` (`services/db/db.py`) | Column-level PII findings from a database scan         | `id`, `organisation_id`, `source_id`, `scan_run_id`, `table`, `column`, `pii_type` |

**Requests** (one shared table across every source type)

| Collection              | Purpose                                        | Important fields / key                                     |
| ----------------------- | ---------------------------------------------- | ---------------------------------------------------------- |
| `data_subject_requests` | Master correction, erasure, or access request  | `id` (unique), `org_id`, principal, status, SLA timestamps |
| `request_tasks`         | Per-source work created from a subject request | `request_id`, `data_source_id` (unique pair), status       |
| `redaction_records`     | Evidence of a redaction/remediation operation  | `id`, `org_id`, source/request links                       |

**Audit** (one shared table across every source type, including database scans)

| Collection   | Purpose                                              | Important fields / key                                                                 |
| ------------ | ---------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `audit_logs` | Immutable-style activity trail for every source type | `org_id`, `actor_type`/`actor_id`, `entity_type`, `source_type`, `action`, `timestamp` |

`scripts/migrate_to_canonical_storage.py` is the one-way bridge for historical
Mongo collections. It is dry-run by default and never deletes legacy data.
