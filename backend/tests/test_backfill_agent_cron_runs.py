from datetime import datetime, timezone
 
from backend.scripts import backfill_agent_cron_runs as migration
from backend.services.persistence.mongo import agent_cron_runs, db
 
 
def setup_function():
    agent_cron_runs.delete_many({})
    db["scan_jobs"].delete_many({})
    db["agent_scan_logs"].delete_many({})
 
 
def test_backfill_maps_both_sources_and_is_idempotent():
    started_at = datetime(2025, 2, 1, tzinfo=timezone.utc)
    db["scan_jobs"].insert_one({
        "org_id": "org-a",
        "device_id": "device-a",
        "task_type": "standalone_daily_pii",
        "status": "completed",
        "started_at": started_at,
        "duration": "3s",
        "vulnerability_count": 4,
    })
    db["agent_scan_logs"].insert_one({
        "organisation_id": "org-a",
        "device_id": "device-b",
        "task_type": "standalone_daily_pii",
        "status": "failed",
        "started_at": started_at,
        "error": "permission denied",
    })
    db["scan_jobs"].insert_one({
        "org_id": "org-a",
        "device_id": "device-a",
        "task_type": "other_scan",
        "status": "completed",
        "started_at": started_at,
    })
 
    counts = {}
    migration.migrate_cron_runs(False, counts)
    assert counts == {"agent_cron_runs": 2}
    assert agent_cron_runs.count_documents({}) == 0
 
    migration.migrate_cron_runs(True, {})
    migration.migrate_cron_runs(True, {})
    assert agent_cron_runs.count_documents({}) == 2
    run = agent_cron_runs.find_one({"device_id": "device-b"}, {"_id": 0})
    assert run["org_id"] == "org-a"
    assert run["error_message"] == "permission denied"
    assert run["id"]