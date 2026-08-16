from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _use_mock_db() -> bool:
    return os.getenv("USE_MOCK_DB", "").strip() == "1"


def _configure_dns_resolvers():
    """Configures public DNS resolvers (8.8.8.8, 1.1.1.1) to avoid local SRV DNS timeouts on Windows."""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ["8.8.8.8", "1.1.1.1", "8.8.4.4"]
        resolver.timeout = 5.0
        resolver.lifetime = 10.0
        dns.resolver.default_resolver = resolver
    except Exception:
        pass


def _make_client():
    if _use_mock_db():
        import mongomock

        return mongomock.MongoClient()

    _configure_dns_resolvers()

    from pymongo import MongoClient, ReadPreference

    atlas_url = os.getenv("ATLAS_URL", "").strip()
    if not atlas_url:
        print("[MongoDB] No ATLAS_URL configured, falling back to local mongomock.")
        import mongomock
        return mongomock.MongoClient()

    try:
        return MongoClient(
            atlas_url,
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=8000,
            socketTimeoutMS=10000,
            retryWrites=True,
            read_preference=ReadPreference.PRIMARY_PREFERRED,
        )
    except Exception as exc:
        print(f"[MongoDB] Failed to connect to Atlas ({exc}). Falling back to local mongomock.")
        import mongomock
        return mongomock.MongoClient()


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
    indexes = [
        (organizations, ("id",), {"unique": True}),
        (users, ("email",), {"unique": True}),
        (org_memberships, ([("user_id", 1), ("organisation_id", 1)],), {"unique": True}),
        (sessions, ("token",), {"unique": True}),
        (data_sources, ([("org_id", 1), ("source_type", 1), ("source_key", 1)],), {"unique": True}),
        (data_source_approval_requests, ([("org_id", 1), ("data_source_id", 1), ("status", 1)],), {}),
        (scan_jobs, ([("org_id", 1), ("data_source_id", 1), ("started_at", -1)],), {}),
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
        (audit_logs, ([("org_id", 1), ("created_at", -1)],), {}),
    ]
    for coll, args, kwargs in indexes:
        try:
            coll.create_index(*args, **kwargs)
        except Exception:
            pass


ensure_indexes()
