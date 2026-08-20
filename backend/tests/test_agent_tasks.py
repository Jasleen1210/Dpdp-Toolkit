import asyncio
import os
from datetime import datetime, timezone
 
os.environ["USE_MOCK_DB"] = "1"
 
from backend.api.agents.models import CronRunRequest, VulnerabilityReportPayload
from backend.api.agents.tasks import (
    device_cron_runs_collection,
    cron_run_vulnerabilities_collection,
    device_vulnerabilities_collection,
    devices_collection,
    get_cron_run_vulnerabilities,
    get_device_vulnerabilities,
    list_cron_runs,
    register_cron_run,
    report_vulnerabilities,
)
from backend.services.persistence.mongo import organizations
 
 
ORG_ID = "cron-test-org"
OTHER_ORG_ID = "cron-other-org"
AGENT_TOKEN = "agent-token"
ADMIN_KEY = "admin-key"
DEVICE_ID = "device-1"
 
 
def setup_function():
    for collection in (
        organizations,
        devices_collection,
        device_cron_runs_collection,
        cron_run_vulnerabilities_collection,
        device_vulnerabilities_collection,
    ):
        collection.delete_many({})
    organizations.insert_many([
        {"id": ORG_ID, "agent_token": AGENT_TOKEN, "admin_api_key": ADMIN_KEY},
        {"id": OTHER_ORG_ID, "agent_token": "other-token", "admin_api_key": "other-key"},
    ])
    devices_collection.insert_many([
        {
            "id": "source-1",
            "device_id": DEVICE_ID,
            "source_key": DEVICE_ID,
            "source_type": "local_device",
            "approved": True,
            "organisation_id": ORG_ID,
            "org_id": ORG_ID,
        },
        {
            "id": "source-2",
            "device_id": "device-2",
            "source_key": "device-2",
            "source_type": "local_device",
            "approved": True,
            "organisation_id": ORG_ID,
            "org_id": ORG_ID,
        },
    ])
 
 
def _request(**overrides):
    values = {
        "device_id": DEVICE_ID,
        "task_type": "standalone_daily_pii",
        "status": "started",
        "started_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return CronRunRequest(**values)
 
 
def _register(req, run_id=None):
    if run_id is not None:
        if hasattr(req, "model_copy"):
            req = req.model_copy(update={"run_id": run_id})
        else:
            req = req.copy(update={"run_id": run_id})
    return asyncio.run(register_cron_run(
        req,
        authorization=f"Bearer {AGENT_TOKEN}",
        x_org_id=ORG_ID,
    ))
 
 
def test_cron_run_lifecycle_writes_one_canonical_record():
    started = _register(_request())
    run_id = started["run_id"]
 
    completed = _register(
        _request(status="completed", duration="2.5s"),
        run_id=run_id,
    )
 
    assert completed["run_id"] == run_id
    assert device_cron_runs_collection.count_documents({}) == 1
    run = device_cron_runs_collection.find_one({"id": run_id}, {"_id": 0})
    assert run["data_source_id"] == "source-1"
    assert run["status"] == "completed"
    assert run["duration_elapsed"] == "2.5s"
    assert run["completed_at"] is not None
    assert run["vulnerability_count"] is None
 
 
def test_unknown_completion_is_persisted_as_a_complete_record():
    response = _register(
        _request(status="failed", duration="1s", error="scan failed"),
        run_id="lost-start-run",
    )
 
    assert response["run_id"] == "lost-start-run"
    run = device_cron_runs_collection.find_one({"id": "lost-start-run"}, {"_id": 0})
    assert run["status"] == "failed"
    assert run["error_message"] == "scan failed"
    assert run["completed_at"] is not None
 
 
def test_vulnerability_report_enriches_matching_cron_run():
    started = _register(_request())
    payload = VulnerabilityReportPayload(
        device_id=DEVICE_ID,
        cron_run_id=started["run_id"],
        vulnerabilities=[],
    )
 
    assert asyncio.run(report_vulnerabilities(
        payload,
        authorization=f"Bearer {AGENT_TOKEN}",
        x_org_id=ORG_ID,
    )) == {"status": "success"}
    run = device_cron_runs_collection.find_one({"id": started["run_id"]})
    assert run["vulnerability_count"] == 0
    vulnerability_doc = device_vulnerabilities_collection.find_one(
        {"device_id": DEVICE_ID, "organisation_id": ORG_ID},
        {"_id": 0},
    )
    assert vulnerability_doc["cron_run_id"] == started["run_id"]
 
 
def _vulnerability(path: str, data_type: str, match_count: int):
    return {
        "title": f"{data_type} finding",
        "data_type": data_type,
        "exposure_type": "file",
        "priority_score": 0.75,
        "match_count": match_count,
        "path_or_port": path,
        "status": "unresolved",
    }
 
 
def _report(run_id: str, vulnerabilities: list[dict]):
    return asyncio.run(report_vulnerabilities(
        VulnerabilityReportPayload(
            device_id=DEVICE_ID,
            cron_run_id=run_id,
            vulnerabilities=vulnerabilities,
        ),
        authorization=f"Bearer {AGENT_TOKEN}",
        x_org_id=ORG_ID,
    ))
 
 
def test_vulnerability_reports_are_retained_per_run_and_idempotent():
    first_run = _register(_request(started_at=datetime(2025, 1, 1, tzinfo=timezone.utc)))
    second_run = _register(_request(started_at=datetime(2025, 1, 2, tzinfo=timezone.utc)))
    first_finding = _vulnerability("/first.txt", "email", 2)
    second_finding = _vulnerability("/second.txt", "phone", 4)
 
    assert _report(first_run["run_id"], [first_finding]) == {"status": "success"}
    assert _report(second_run["run_id"], [second_finding]) == {"status": "success"}
    assert cron_run_vulnerabilities_collection.count_documents({}) == 2
 
    first_doc = cron_run_vulnerabilities_collection.find_one(
        {"cron_run_id": first_run["run_id"]},
        {"_id": 0},
    )
    second_doc = cron_run_vulnerabilities_collection.find_one(
        {"cron_run_id": second_run["run_id"]},
        {"_id": 0},
    )
    assert first_doc["vulnerabilities"] == [first_finding]
    assert second_doc["vulnerabilities"] == [second_finding]
 
    assert _report(second_run["run_id"], [second_finding]) == {"status": "success"}
    assert cron_run_vulnerabilities_collection.count_documents({}) == 2
    latest = device_vulnerabilities_collection.find_one(
        {"device_id": DEVICE_ID, "organisation_id": ORG_ID},
        {"_id": 0},
    )
    assert latest["cron_run_id"] == second_run["run_id"]
    assert latest["vulnerabilities"] == [second_finding]
    latest_response = asyncio.run(get_device_vulnerabilities(
        DEVICE_ID,
        x_admin_key=ADMIN_KEY,
        x_org_id=ORG_ID,
    ))
    assert latest_response["cron_run_id"] == second_run["run_id"]
    assert latest_response["vulnerabilities"] == [second_finding]
 
 
def test_cron_run_vulnerability_endpoint_scopes_and_falls_back_safely():
    first_run = _register(_request(started_at=datetime(2025, 1, 1, tzinfo=timezone.utc)))
    second_run = _register(_request(started_at=datetime(2025, 1, 2, tzinfo=timezone.utc)))
    first_finding = _vulnerability("/first.txt", "email", 2)
    second_finding = _vulnerability("/second.txt", "phone", 4)
    _report(first_run["run_id"], [first_finding])
    _report(second_run["run_id"], [second_finding])
 
    response = asyncio.run(get_cron_run_vulnerabilities(
        second_run["run_id"],
        x_admin_key=ADMIN_KEY,
        x_org_id=ORG_ID,
    ))
    assert response["detail_retained"] is True
    assert response["vulnerabilities"] == [second_finding]
    assert "_id" not in response
 
    cron_run_vulnerabilities_collection.delete_one({"cron_run_id": second_run["run_id"]})
    fallback = asyncio.run(get_cron_run_vulnerabilities(
        second_run["run_id"],
        x_admin_key=ADMIN_KEY,
        x_org_id=ORG_ID,
    ))
    assert fallback["detail_retained"] is True
    assert fallback["vulnerabilities"] == [second_finding]
    assert fallback["cron_run_id"] == second_run["run_id"]
 
    cron_run_vulnerabilities_collection.delete_one({"cron_run_id": first_run["run_id"]})
    device_vulnerabilities_collection.delete_one({
        "device_id": DEVICE_ID,
        "organisation_id": ORG_ID,
    })
    empty = asyncio.run(get_cron_run_vulnerabilities(
        first_run["run_id"],
        x_admin_key=ADMIN_KEY,
        x_org_id=ORG_ID,
    ))
    assert empty["detail_retained"] is False
    assert empty["vulnerabilities"] == []
 
    other_org = asyncio.run(get_cron_run_vulnerabilities(
        second_run["run_id"],
        x_admin_key="other-key",
        x_org_id=OTHER_ORG_ID,
    ))
    assert other_org["detail_retained"] is False
 
def test_read_endpoint_is_scoped_filtered_sorted_and_hides_mongo_id():
    _register(_request(started_at=datetime(2025, 1, 1, tzinfo=timezone.utc)))
    _register(_request(
        device_id="device-2",
        started_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
    ))
    device_cron_runs_collection.insert_one({
        "id": "other-run",
        "org_id": OTHER_ORG_ID,
        "organisation_id": OTHER_ORG_ID,
        "device_id": DEVICE_ID,
        "task_type": "standalone_daily_pii",
        "status": "completed",
        "started_at": datetime(2025, 1, 4, tzinfo=timezone.utc),
    })
 
    response = asyncio.run(list_cron_runs(
        device_id="device-2",
        organisation_id=ORG_ID,
        x_admin_key=ADMIN_KEY,
        x_org_id=ORG_ID,
    ))
 
    assert len(response["runs"]) == 1
    run = response["runs"][0]
    assert run["device_id"] == "device-2"
    assert run["started_at"].replace(tzinfo=timezone.utc) == datetime(
        2025, 1, 3, tzinfo=timezone.utc
    )
    assert "_id" not in run
    assert "id" not in run
 
    all_runs = asyncio.run(list_cron_runs(
        organisation_id=ORG_ID,
        x_admin_key=ADMIN_KEY,
        x_org_id=ORG_ID,
    ))["runs"]
    assert [item["device_id"] for item in all_runs] == ["device-2", DEVICE_ID]