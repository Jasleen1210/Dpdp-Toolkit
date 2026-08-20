"""Backfill canonical local-agent cron runs from historical collections.
 
Run from the repository root:
    python -m backend.scripts.backfill_agent_cron_runs          # dry run
    python -m backend.scripts.backfill_agent_cron_runs --apply  # write/upsert
 
The migration reads only the canonical ``dpdp_platform`` database. It never
mutates or deletes source documents and is safe to rerun.
"""
 
from __future__ import annotations
 
import argparse
from datetime import datetime, timezone
from uuid import uuid4
 
from backend.services.persistence.mongo import (
    agent_cron_runs,
    data_source_vulnerabilities,
    db,
)
 
 
SOURCE_COLLECTIONS = ("scan_jobs", "agent_scan_logs")
DAILY_CRON_TASK_TYPE = "standalone_daily_pii"
 
 
def _as_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return _as_datetime(parsed)
    return None
 
 
def _first(doc: dict, *keys):
    for key in keys:
        value = doc.get(key)
        if value is not None:
            return value
    return None
 
 
def _normalise(doc: dict):
    org_id = _first(doc, "org_id", "organisation_id", "organization_id")
    device_id = _first(doc, "device_id", "device", "data_source_id")
    task_type = _first(doc, "task_type", "cron_type", "type")
    started_at = _as_datetime(_first(doc, "started_at", "startedAt", "timestamp"))
    if not org_id or not device_id or task_type != DAILY_CRON_TASK_TYPE or not started_at:
        return None
 
    status = _first(doc, "status", "run_status") or "unknown"
    reported_at = _as_datetime(
        _first(doc, "reported_at", "completed_at", "updated_at", "created_at")
    )
    completed_at = _as_datetime(_first(doc, "completed_at", "finished_at"))
    if completed_at is None and status in {"completed", "failed"}:
        completed_at = reported_at
    created_at = _as_datetime(_first(doc, "created_at")) or started_at
    updated_at = _as_datetime(_first(doc, "updated_at")) or reported_at or created_at
    source_id = next(
        (
            doc.get(key)
            for key in ("id", "run_id", "_id")
            if doc.get(key) not in (None, "")
        ),
        None,
    )
    stable_id = source_id is not None
    return {
        "id": str(source_id) if stable_id else str(uuid4()),
        "_stable_id": stable_id,
        "org_id": org_id,
        "organisation_id": org_id,
        "device_id": device_id,
        "data_source_id": _first(doc, "data_source_id") or device_id,
        "task_type": task_type,
        "status": status,
        "started_at": started_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "duration_elapsed": _first(doc, "duration_elapsed", "duration"),
        "error_message": _first(doc, "error_message", "error"),
        "completed_at": completed_at,
        "reported_at": reported_at,
        "vulnerability_count": None,
    }
 
 
def _linked_vulnerability_count(doc: dict):
    org_id = doc["org_id"]
    device_id = doc["device_id"]
    data_source_id = doc["data_source_id"]
    run_id = doc["id"]
    vulnerability = data_source_vulnerabilities.find_one(
        {
            "cron_run_id": run_id,
            "$and": [
                {"$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
                {
                    "$or": [
                        {"device_id": device_id},
                        {"data_source_id": device_id},
                        {"data_source_id": data_source_id},
                    ]
                },
            ],
        },
        {"_id": 0, "summary.total_vulnerabilities": 1},
    )
    if vulnerability is None:
        return None
    return (vulnerability.get("summary") or {}).get("total_vulnerabilities")
 
 
def _upsert(doc: dict, apply: bool):
    key = {
        "org_id": doc["org_id"],
        "device_id": doc["device_id"],
        "started_at": doc["started_at"],
    }
    if not apply:
        return
 
    set_doc = dict(doc)
    run_id = set_doc.pop("id")
    stable_id = set_doc.pop("_stable_id")
    created_at = set_doc.pop("created_at")
    set_doc["vulnerability_count"] = _linked_vulnerability_count({
        **set_doc,
        "id": run_id,
    })
    update = {"$set": set_doc}
    if stable_id:
        update["$set"]["id"] = run_id
    else:
        update["$setOnInsert"] = {"id": run_id}
    update["$setOnInsert"] = {
        **update.get("$setOnInsert", {}),
        "created_at": created_at,
    }
    agent_cron_runs.update_one(
        key,
        update,
        upsert=True,
    )
 
 
def migrate_cron_runs(apply: bool, counts: dict[str, int]):
    for collection_name in SOURCE_COLLECTIONS:
        for source_doc in db[collection_name].find({}):
            doc = _normalise(source_doc)
            if doc is None:
                continue
            counts["agent_cron_runs"] = counts.get("agent_cron_runs", 0) + 1
            _upsert(doc, apply)
 
 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write records; without this flag only report the work")
    args = parser.parse_args()
    counts: dict[str, int] = {}
    migrate_cron_runs(args.apply, counts)
    print(("Applied" if args.apply else "Dry-run:") + " canonical cron-run upserts")
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")
 
 
if __name__ == "__main__":
    main()