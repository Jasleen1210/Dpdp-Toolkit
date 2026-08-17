from __future__ import annotations

try:
    from backend.services.persistence.mongo import client
except ImportError:
    from services.persistence.mongo import client


db = client["dpdp_database_scanner_db"]

database_sources_collection = db["database_sources"]
database_scan_runs_collection = db["database_scan_runs"]
database_findings_collection = db["database_findings"]
database_audit_logs_collection = db["database_audit_logs"]