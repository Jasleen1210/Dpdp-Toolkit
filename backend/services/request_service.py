"""
Unified Data Subject Request Service.
Single source of truth for request creation, retrieval, and state management.
Enforces org-level isolation and manages workflows across cloud, local, and database sources.

REQUEST LIFECYCLE:
1. User submits request via POST /requests
2. Master doc stored in data_subject_requests collection
3. Local device tasks queued in request_tasks collection  
4. Cloud & database processing spawned asynchronously
5. Status synchronized across all task types via request id
6. User retrieves unified view via GET /requests
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Literal
from uuid import uuid4

from backend.services.persistence.mongo import (
    audit_logs,
    data_sources,
    data_subject_requests,
    pii_classifications,
    request_tasks,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RequestStateManager:
    """
    Unified manager for request state across all source types.
    
    State Machine:
    - DELETE requests: pending → awaiting_approval → in_progress → completed
    - All others:      pending → in_progress → completed
    
    Task Tracking:
    - request_tasks: local device execution tasks
    - pii_classifications: cloud scan results (stored per file/location)
    - Master doc: orchestration point for all activities
    """
    
    @staticmethod
    def build_request_list_query(org_id: str, filters: dict = None) -> dict:
        """
        Builds MongoDB query for fetching org-scoped requests.
        Ensures data isolation by org_id.
        """
        query = {"$or": [{"org_id": org_id}, {"organisation_id": org_id}]}
        if filters:
            query.update(filters)
        return query
    
    @staticmethod
    def get_request_with_tasks(request_id: str, org_id: str) -> dict:
        """
        Retrieves single request with all associated tasks.
        Single roundtrip to database with proper org isolation.
        """
        # Fetch master request
        req = data_subject_requests.find_one(
            RequestStateManager.build_request_list_query(org_id, {"id": request_id}),
            {"_id": 0}
        )
        if not req:
            return None
        
        # Fetch all tasks for this request
        task_docs = list(
            request_tasks.find(
                {"request_id": request_id, "org_id": org_id},
                {"_id": 0}
            )
        )

        local_tasks = RequestStateManager.attach_local_task_results(task_docs, org_id)
        
        # Fetch cloud results from pii_classifications
        cloud_results = list(
            pii_classifications.find(
                {
                    "request_id": request_id,
                    "org_id": org_id,
                    "source_type": "cloud_storage",
                },
                {"_id": 0}
            )
        )
        
        return {
            "request": req,
            "local_tasks": local_tasks,
            "cloud_results": cloud_results,
            "db_results": req.get("db_results", []),
            "db_errors": req.get("db_errors", []),
        }
    
    @staticmethod
    def attach_local_task_results(task_docs: List[dict], org_id: str) -> List[dict]:
        """
        Merges each local device task with the scan result submitted by the agent
        (stored in pii_classifications), so callers receive the full finding
        details: scanned file counts, detected PII types and per-match rows.
        """
        if not task_docs:
            return []
 
        task_ids = [task["id"] for task in task_docs if task.get("id")]
        results = list(
            pii_classifications.find(
                {
                    "$and": [
                        {
                            "$or": [
                                {"request_task_id": {"$in": task_ids}},
                                {"task_id": {"$in": task_ids}},
                            ]
                        },
                        {"$or": [{"org_id": org_id}, {"organisation_id": org_id}]},
                    ]
                },
                {"_id": 0},
            )
        )
 
        result_by_task = {}
        for result in results:
            key = result.get("request_task_id") or result.get("task_id")
            if key:
                result_by_task[key] = result
 
        enriched = []
        for task in task_docs:
            task_id = task.get("id")
            result = result_by_task.get(task_id) or {}
            matches = result.get("matches", [])
            enriched.append({
                **task,
                "task_id": task_id,
                "scanned_files": result.get("scanned_files", 0),
                "matches_count": len(matches),
                "pii_types": sorted({m.get("type", "") for m in matches if m.get("type")}),
                "matches": matches,
                "delete_replacements": result.get("delete_replacements", []),
            })
 
        return enriched
 
    @staticmethod
    def normalize_status(
        req_status: str,
        local_tasks: List[dict],
        cloud_results: List[dict],
        requires_approval: bool = False,
        approved: bool = False,
    ) -> str:
        """
        Derives canonical status from master request and all task states.
        
        Returns:
            "awaiting_approval" - delete request pending user confirmation
            "in_progress" - any tasks pending or in_progress
            "completed" - all tasks and cloud results completed
            "rejected" - explicitly rejected by user
        """
        normalized = (req_status or "pending").lower()
        
        if normalized in {"rejected", "cancelled"}:
            return "rejected"
        if normalized in {"error", "failed"}:
            return "error"
        
        # DELETE requests show approval state explicitly until approved
        if requires_approval and not approved:
            if normalized in {"awaiting_approval", "pending"}:
                return "awaiting_approval"
            elif normalized == "rejected":
                return "rejected"
        
        # Check local tasks
        if local_tasks:
            task_statuses = [t.get("status", "pending").lower() for t in local_tasks]
            if all(s == "completed" for s in task_statuses):
                local_done = True
            elif any(s in {"pending", "in_progress"} for s in task_statuses):
                return "in_progress"
            else:
                local_done = True
        else:
            local_done = True
        
        # Check cloud results
        if cloud_results:
            cloud_statuses = [c.get("status", "pending").lower() for c in cloud_results]
            if all(s in {"completed", "failed"} for s in cloud_statuses):
                cloud_done = True
            elif any(s == "in_progress" for s in cloud_statuses):
                return "in_progress"
            else:
                cloud_done = True
        else:
            cloud_done = True
        
        if local_done and cloud_done:
            return "completed"
        
        return normalized if normalized in {"pending", "in_progress"} else "in_progress"

    @staticmethod
    def build_status_message(source_status: dict) -> str:
        """Return a user-facing explanation of the current source work."""
        if not source_status:
            return "No scan sources were selected."
        errors = [source for source, state in source_status.items() if state == "error"]
        awaiting = [source for source, state in source_status.items() if state == "awaiting_approval"]
        queued = [source for source, state in source_status.items() if state in {"queued", "in_progress"}]
        skipped = [source for source, state in source_status.items() if state == "skipped"]
        if errors:
            return f"Scan error on {', '.join(errors)}. Review the source details."
        if awaiting:
            return f"Waiting for approval before processing {', '.join(awaiting)}."
        if queued:
            return f"Waiting for scan results from {', '.join(queued)}."
        if skipped:
            return f"Completed with {', '.join(skipped)} source(s) skipped."
        return "All selected sources finished scanning."
    
    @staticmethod
    def filter_org_devices(org_id: str, device_ids: Optional[List[str]] = None) -> List[dict]:
        """
        Gets all approved local devices for org, optionally filtered by device_ids.
        
        Args:
            org_id: Organization ID
            device_ids: Optional list of specific device IDs. If None, returns all org devices.
        
        Returns:
            List of device documents (minimal fields for task creation)
        """
        query = {
            "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
            "source_type": "local_device",
            "approved": True,
        }
        
        if device_ids:
            query["device_id"] = {"$in": device_ids}
        
        return list(data_sources.find(query, {"_id": 0, "device_id": 1, "id": 1, "last_seen": 1}))
    
    @staticmethod
    def create_local_device_tasks(
        request_id: str,
        org_id: str,
        request_type: str,
        identifier: str,
        new_value: Optional[str],
        device_ids: Optional[List[str]],
        expires_at: datetime,
        requires_approval: bool = False,
    ) -> List[dict]:
        """
        Creates request_tasks for all org's approved devices.

        Tasks for requests that require approval are created as "awaiting_approval"
        so the agent (which only executes "pending" tasks) does not act until
        `release_local_device_tasks` flips them to "pending" on approval.

        Returns list of created task IDs for tracking.
        """
        target_devices = RequestStateManager.filter_org_devices(org_id, device_ids)
        
        if not target_devices:
            return []
        
        action_type = request_type.lower()
        if action_type == "update":
            packed_query = f"{identifier}::{new_value or ''}"
        else:
            packed_query = identifier
        
        task_group_id = str(uuid4())
        created_tasks = []
        now = utc_now()
        initial_status = "awaiting_approval" if requires_approval else "pending"
        
        for device in target_devices:
            device_id = device.get("device_id")
            if not device_id:
                continue
            
            task_id = str(uuid4())
            data_source_id = device.get("id") or device_id
            
            task_doc = {
                "id": task_id,
                "request_id": request_id,
                "task_group_id": task_group_id,
                "data_source_id": data_source_id,
                "org_id": org_id,
                "organisation_id": org_id,
                "device_id": device_id,
                "source_type": "local_device",
                "query": packed_query,
                "type": action_type,
                "status": initial_status,
                "created_at": now,
                "expires_at": expires_at,
                "updated_at": now,
                "completed_at": None,
            }
            
            request_tasks.insert_one(task_doc)
            created_tasks.append({
                "task_id": task_id,
                "device_id": device_id,
                "status": initial_status,
                "expires_at": expires_at.isoformat(),
            })
        
        return created_tasks

    @staticmethod
    def release_local_device_tasks(request_id: str, org_id: str) -> int:
        """Flips awaiting-approval local tasks to pending so the agent can execute them."""
        result = request_tasks.update_many(
            {
                "request_id": request_id,
                "$or": [{"org_id": org_id}, {"organisation_id": org_id}],
                "status": "awaiting_approval",
            },
            {"$set": {"status": "pending", "updated_at": utc_now()}},
        )
        return result.modified_count
