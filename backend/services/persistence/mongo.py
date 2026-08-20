from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# adding three retries to prevent dns issues when connecting to Atlas

def _use_mock_db() -> bool:
    return os.getenv("USE_MOCK_DB", "").strip() == "1"


def _make_client():
    if _use_mock_db():
        import mongomock
        print("[MongoDB] Using mock database (USE_MOCK_DB=1)")
        return mongomock.MongoClient()

    from pymongo import MongoClient, ReadPreference
    import time

    atlas_url = os.getenv("ATLAS_URL", "").strip()
    if not atlas_url:
        print("[MongoDB] No ATLAS_URL configured, falling back to local mongomock.")
        import mongomock
        return mongomock.MongoClient()

    # Retry logic for DNS/network timeouts
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"[MongoDB] Attempting connection (attempt {attempt + 1}/{max_retries})...")
            
            # Use certifi to provide the CA bundle for macOS and environments where SSL verification fails
            import certifi
            
            client = MongoClient(
                atlas_url,
                serverSelectionTimeoutMS=25000,  # 25 seconds
                connectTimeoutMS=25000,
                socketTimeoutMS=30000,
                retryWrites=True,
                read_preference=ReadPreference.PRIMARY_PREFERRED,
                directConnection=False,
                appName="dpdp-app",
                tlsCAFile=certifi.where(),
                maxPoolSize=50,
                minPoolSize=10,
            )
            # Test connection
            client.server_info()
            print("[MongoDB] Connected to Atlas successfully")
            return client
        except Exception as exc:
            error_msg = str(exc)
            print(f"[MongoDB] Attempt {attempt + 1} failed: {error_msg}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"[MongoDB] Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"[MongoDB] All {max_retries} attempts failed. Falling back to local mongomock.")
                import mongomock
                return mongomock.MongoClient()


client = _make_client()
db = client[os.getenv("DPDP_DB_NAME", "dpdp_platform").strip() or "dpdp_platform"]

# Canonical collections. Everything lives in one Mongo database (`db` above);
# scan-run logs are split per source category (agent/cloud/database) because
# their payload shapes differ, while requests, sources, and audit trail stay unified.
organizations = db["organizations"]
users = db["users"]
org_memberships = db["org_memberships"]
sessions = db["sessions"]
data_sources = db["data_sources"]
data_source_approval_requests = db["data_source_approval_requests"]
agent_scan_logs = db["agent_scan_logs"]
agent_cron_runs = db["agent_cron_runs"]
cloud_scan_logs = db["cloud_scan_logs"]
pii_classifications = db["pii_classifications"]
data_subject_requests = db["data_subject_requests"]
request_tasks = db["request_tasks"]
data_source_vulnerabilities = db["data_source_vulnerabilities"]
agent_cron_run_vulnerabilities = db["agent_cron_run_vulnerabilities"]
audit_logs = db["audit_logs"]
redaction_records = db["redaction_records"]

# Database-engine discovery collections (backend/services/db/db.py) also live
# in this same `db`, kept in their own tables because connection configs and
# column-level findings have a different shape than the generic collections above.


def ensure_indexes() -> None:
    """Create idempotent indexes used by the production query paths."""
    indexes = [
        (organizations, ("id",), {"unique": True}),
        (users, ("email",), {"unique": True}),
        (org_memberships, ([("user_id", 1), ("organisation_id", 1)],), {"unique": True}),
        (sessions, ("token",), {"unique": True}),
        (data_sources, ([("org_id", 1), ("source_type", 1), ("source_key", 1)],), {"unique": True}),
        (data_source_approval_requests, ([("org_id", 1), ("data_source_id", 1), ("status", 1)],), {}),
        (agent_scan_logs, ([("org_id", 1), ("data_source_id", 1), ("started_at", -1)],), {}),
        (agent_cron_runs, ([("org_id", 1), ("device_id", 1), ("started_at", -1)],), {}),
        (agent_cron_runs, ("id",), {"unique": True}),
        (cloud_scan_logs, ([("org_id", 1), ("started_at", -1)],), {}),
        (pii_classifications, ([("org_id", 1), ("data_source_id", 1), ("location", 1)],), {}),
        (pii_classifications, ([("org_id", 1), ("request_task_id", 1)],), {}),
        (pii_classifications, ([("org_id", 1), ("task_id", 1)],), {}),
        (pii_classifications, ([("org_id", 1), ("request_id", 1)],), {}),
        (data_subject_requests, ([("org_id", 1), ("created_at", -1)],), {}),
        (data_subject_requests, ("id",), {"unique": True}),
        (request_tasks, ("id",), {}),
        (request_tasks, ([("request_id", 1), ("data_source_id", 1)],), {"unique": True}),
        (request_tasks, ([("org_id", 1), ("status", 1), ("created_at", -1)],), {}),
        (data_source_vulnerabilities, ([("org_id", 1), ("data_source_id", 1)],), {"unique": True}),
        (agent_cron_run_vulnerabilities, ([("org_id", 1), ("cron_run_id", 1)],), {"unique": True}),
        (audit_logs, ([("org_id", 1), ("created_at", -1)],), {}),
    ]
    for coll, args, kwargs in indexes:
        try:
            coll.create_index(*args, **kwargs)
        except Exception:
            pass


ensure_indexes()
