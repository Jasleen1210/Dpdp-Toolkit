"""Backfill legacy Mongo collections into the canonical DPDP schema.

Run from the repository root:
    python -m backend.scripts.migrate_to_canonical_storage          # dry run
    python -m backend.scripts.migrate_to_canonical_storage --apply  # write/upsert

The migration never drops, renames, or mutates legacy collections. It is safe
to rerun: every record is upserted using a stable natural key.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.services.persistence.mongo import (
    client, data_source_approval_requests, data_source_vulnerabilities,
    data_sources, data_subject_requests, pii_classifications, request_tasks,
    agent_scan_logs, cloud_scan_logs, users, organizations, org_memberships, sessions,
)

DEFAULT_ORG_ID = os.getenv("ORG_ID", "dpdp-org").strip() or "dpdp-org"


def now():
    return datetime.now(timezone.utc)


def legacy_db(name: str):
    return client[name]


def upsert(collection, key: dict, doc: dict, apply: bool, counts: dict, name: str):
    counts[name] = counts.get(name, 0) + 1
    if apply:
        # MongoDB cannot update a field through both $set and $setOnInsert in
        # the same operation. Preserve the historical creation timestamp only
        # for a newly inserted canonical document; later reruns never rewrite it.
        set_doc = dict(doc)
        created_at = set_doc.pop("created_at", now())
        collection.update_one(
            key,
            {"$set": set_doc, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
        )


def migrate_identity(apply: bool, counts: dict):
    source = legacy_db("dpdp_combined_db")
    for name, target, key in (("users", users, "email"), ("organizations", organizations, "id"), ("org_memberships", org_memberships, None), ("sessions", sessions, "token")):
        for doc in source[name].find({}, {"_id": 0}):
            if name == "org_memberships":
                org_id = doc.get("organisation_id") or doc.get("organization_id")
                doc["organisation_id"] = org_id
                lookup = {"user_id": doc.get("user_id"), "organisation_id": org_id}
            else:
                lookup = {key: doc.get(key)}
            upsert(target, lookup, doc, apply, counts, name)


def migrate_local(apply: bool, counts: dict):
    source = legacy_db(os.getenv("LOCAL_DB_NAME", "dpdp_local_db"))
    source_ids: dict[tuple[str, str], str] = {}
    for device in source["devices"].find({}, {"_id": 0}):
        org_id, device_id = device.get("organisation_id", DEFAULT_ORG_ID), device.get("device_id")
        if not device_id:
            continue
        canonical_id = device.get("id") or str(uuid4())
        source_ids[(org_id, device_id)] = canonical_id
        device.update({"id": canonical_id, "org_id": org_id, "organisation_id": org_id, "source_type": "local_device", "source_key": device_id})
        upsert(data_sources, {"org_id": org_id, "source_type": "local_device", "source_key": device_id}, device, apply, counts, "data_sources")
    for approval in source["device_approval_requests"].find({}, {"_id": 0}):
        org_id, device_id = approval.get("organisation_id", DEFAULT_ORG_ID), approval.get("device_id")
        approval.update({"org_id": org_id, "organisation_id": org_id, "data_source_id": source_ids.get((org_id, device_id), device_id)})
        upsert(data_source_approval_requests, {"org_id": org_id, "data_source_id": approval["data_source_id"], "status": approval.get("status", "pending")}, approval, apply, counts, "data_source_approval_requests")
    task_request_ids: dict[str, str] = {}
    for task in source["device_tasks"].find({}, {"_id": 0}):
        org_id, task_id = task.get("organisation_id", DEFAULT_ORG_ID), task.get("id")
        if not task_id:
            continue
        request_id = task.get("request_id") or task_request_ids.setdefault(task.get("task_group_id") or task_id, str(uuid4()))
        task_request_ids[task.get("task_group_id") or task_id] = request_id
        request_type = task.get("type", "access").lower()
        request_doc = {"id": request_id, "org_id": org_id, "request_type": request_type, "data_principal": {"identifier_hash": (task.get("query") or "").split("::", 1)[0].lower()}, "verification_status": "verified", "status": "completed" if task.get("status") == "completed" else "in_progress", "sla_due_at": task.get("expires_at"), "submitted_via": "api", "created_at": task.get("created_at", now()), "updated_at": task.get("updated_at", task.get("created_at", now()))}
        upsert(data_subject_requests, {"id": request_id}, request_doc, apply, counts, "data_subject_requests")
        task.update({"request_id": request_id, "org_id": org_id, "organisation_id": org_id, "data_source_id": source_ids.get((org_id, task.get("device_id")), task.get("device_id")), "source_type": "local_device"})
        upsert(request_tasks, {"request_id": request_id, "data_source_id": task["data_source_id"]}, task, apply, counts, "request_tasks")
    for result in source["device_results"].find({}, {"_id": 0}):
        org_id, device_id = result.get("organisation_id", DEFAULT_ORG_ID), result.get("device_id")
        task_id = result.get("task_id")
        task = None
        if task_id:
            task = request_tasks.find_one({"id": task_id, "org_id": org_id}, {"_id": 0, "request_id": 1, "data_source_id": 1})
        request_id = task.get("request_id") if task else result.get("request_id")
        data_source_id = (task.get("data_source_id") if task else None) or source_ids.get((org_id, device_id), device_id)
        result.update({
            "id": result.get("id") or str(uuid4()),
            "org_id": org_id,
            "organisation_id": org_id,
            "data_source_id": data_source_id,
            "request_task_id": task_id,
            "task_id": task_id,
            "request_id": request_id,
            "source_type": "local_device",
            "device_id": device_id,
            "location": task_id or result.get("result_scope", "standalone"),
            "classified_at": result.get("updated_at", result.get("received_at", now())),
        })
        upsert(pii_classifications, {"org_id": org_id, "data_source_id": result["data_source_id"], "location": result["location"]}, result, apply, counts, "pii_classifications")
    for log in source["device_cron_logs"].find({}, {"_id": 0}):
        org_id, device_id = log.get("organisation_id", DEFAULT_ORG_ID), log.get("device_id")
        log.update({"id": log.get("id") or str(uuid4()), "org_id": org_id, "data_source_id": source_ids.get((org_id, device_id), device_id), "source_type": "local_device"})
        upsert(agent_scan_logs, {"org_id": org_id, "data_source_id": log["data_source_id"], "started_at": log.get("started_at")}, log, apply, counts, "agent_scan_logs")
    for vuln in source["device_vulnerabilities"].find({}, {"_id": 0}):
        org_id, device_id = vuln.get("organisation_id", DEFAULT_ORG_ID), vuln.get("device_id")
        vuln.update({"org_id": org_id, "data_source_id": source_ids.get((org_id, device_id), device_id), "source_type": "local_device"})
        upsert(data_source_vulnerabilities, {"org_id": org_id, "data_source_id": vuln["data_source_id"]}, vuln, apply, counts, "data_source_vulnerabilities")


def migrate_cloud(apply: bool, counts: dict):
    source, org_id = legacy_db("cloud_db"), DEFAULT_ORG_ID
    for item in source["cloud_classification"].find({}, {"_id": 0}):
        source_key = "::".join(str(item.get(key, "")) for key in ("provider", "bucket", "region")); data_source_id = str(uuid4())
        existing = data_sources.find_one({"org_id": org_id, "source_type": "cloud_storage", "source_key": source_key}, {"_id": 0, "id": 1})
        if existing: data_source_id = existing["id"]
        source_doc = {"id": data_source_id, "org_id": org_id, "organisation_id": org_id, "source_type": "cloud_storage", "source_key": source_key, "provider": item.get("provider"), "bucket": item.get("bucket"), "region": item.get("region"), "approved": True, "created_at": now(), "updated_at": now()}
        upsert(data_sources, {"org_id": org_id, "source_type": "cloud_storage", "source_key": source_key}, source_doc, apply, counts, "data_sources")
        item.update({"id": item.get("id") or str(uuid4()), "org_id": org_id, "data_source_id": data_source_id, "source_type": "cloud_storage", "location": item.get("location", item.get("file")), "classified_at": item.get("updated_at", now())})
        upsert(pii_classifications, {"org_id": org_id, "data_source_id": data_source_id, "location": item["location"]}, item, apply, counts, "pii_classifications")
    for req in source["user_requests"].find({}, {"_id": 0}):
        request_id = req.get("id") or str(uuid4()); request_type = req.get("type", "ACCESS").lower()
        req.update({"id": request_id, "org_id": org_id, "request_type": request_type, "data_principal": {"identifier_hash": (req.get("identifier") or "").lower()}, "verification_status": "verified", "submitted_via": "api", "sla_due_at": req.get("sla_due_at", now() + timedelta(days=30)), "updated_at": req.get("updated_at", req.get("created_at", now()))})
        upsert(data_subject_requests, {"id": request_id}, req, apply, counts, "data_subject_requests")
    for log in source["cloud_logs"].find({}, {"_id": 0}):
        log.update({"id": log.get("id") or str(uuid4()), "org_id": org_id, "source_type": "cloud_storage", "started_at": log.get("timestamp", now())})
        upsert(cloud_scan_logs, {"org_id": org_id, "source_type": "cloud_storage", "started_at": log["started_at"], "task_type": log.get("action")}, log, apply, counts, "cloud_scan_logs")


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apply", action="store_true", help="write records; without this flag only report the work")
    args = parser.parse_args(); counts: dict[str, int] = {}
    migrate_identity(args.apply, counts); migrate_local(args.apply, counts); migrate_cloud(args.apply, counts)
    print(("Applied" if args.apply else "Dry-run:") + " canonical upserts")
    for name, count in sorted(counts.items()): print(f"  {name}: {count}")


if __name__ == "__main__": main()
