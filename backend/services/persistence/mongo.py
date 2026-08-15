from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _use_mock_db() -> bool:
    return os.getenv("USE_MOCK_DB", "").strip() == "1"


def _make_client():
    if _use_mock_db():
        import mongomock

        return mongomock.MongoClient()

    from pymongo import MongoClient

    atlas_url = os.getenv("ATLAS_URL", "").strip()
    if not atlas_url:
        raise RuntimeError("ATLAS_URL is required when USE_MOCK_DB != 1")
    return MongoClient(atlas_url)


client = _make_client()
db = client[os.getenv("DPDP_DB_NAME", "dpdp_platform").strip() or "dpdp_platform"]

# Canonical collections
organizations = db["organizations"]
users = db["users"]
org_memberships = db["org_memberships"]
sessions = db["sessions"]
data_sources = db["data_sources"]
data_source_approval_requests = db["data_source_approval_requests"]
scan_jobs = db["scan_jobs"]
pii_classifications = db["pii_classifications"]
data_subject_requests = db["data_subject_requests"]
request_tasks = db["request_tasks"]
data_source_vulnerabilities = db["data_source_vulnerabilities"]
audit_logs = db["audit_logs"]
redaction_records = db["redaction_records"]


def ensure_indexes() -> None:
    """Create idempotent indexes used by the production query paths."""
    organizations.create_index("id", unique=True)
    users.create_index("email", unique=True)
    org_memberships.create_index([("user_id", 1), ("organisation_id", 1)], unique=True)
    sessions.create_index("token", unique=True)
    data_sources.create_index([("org_id", 1), ("source_type", 1), ("source_key", 1)], unique=True)
    data_source_approval_requests.create_index([("org_id", 1), ("data_source_id", 1), ("status", 1)])
    scan_jobs.create_index([("org_id", 1), ("data_source_id", 1), ("started_at", -1)])
    pii_classifications.create_index([("org_id", 1), ("data_source_id", 1), ("location", 1)])
    data_subject_requests.create_index([("org_id", 1), ("created_at", -1)])
    data_subject_requests.create_index("id", unique=True)
    request_tasks.create_index([("request_id", 1), ("data_source_id", 1)], unique=True)
    request_tasks.create_index([("org_id", 1), ("status", 1), ("created_at", -1)])
    data_source_vulnerabilities.create_index([("org_id", 1), ("data_source_id", 1)], unique=True)
    audit_logs.create_index([("org_id", 1), ("created_at", -1)])


ensure_indexes()
