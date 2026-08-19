from __future__ import annotations

# Database-engine discovery shares the single platform Mongo database instead
# of a second, disconnected one. Sources/scan-runs/findings keep their own
# collections here because connection configs and column-level findings have
# a different shape than the generic data_sources/pii_classifications tables.
# Audit events go into the platform-wide `audit_logs` collection (see mongo.py).
try:
    from backend.services.persistence.mongo import db
except ImportError:
    from services.persistence.mongo import db

database_sources_collection = db["database_sources"]
database_scan_runs_collection = db["database_scan_runs"]
database_findings_collection = db["database_findings"]


def _ensure_database_indexes() -> None:
    indexes = [
        (database_sources_collection, ([("organisation_id", 1), ("id", 1)],), {"unique": True}),
        (database_scan_runs_collection, ([("organisation_id", 1), ("source_id", 1), ("started_at", -1)],), {}),
        (database_findings_collection, ([("organisation_id", 1), ("source_id", 1)],), {}),
    ]
    for coll, args, kwargs in indexes:
        try:
            coll.create_index(*args, **kwargs)
        except Exception:
            pass


_ensure_database_indexes()