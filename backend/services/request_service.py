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
        local_tasks = list(
            request_tasks.find(
                {"request_id": request_id, "org_id": org_id},
                {"_id": 0}
            )
        )
        
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
        }
    
    @staticmethod
    def normalize_status(
        req_status: str,
        local_tasks: List[dict],
        cloud_results: List[dict],
        requires_approval: bool = False
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
        
        # DELETE requests show approval state explicitly
        if requires_approval:
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
        
        return list(data_sources.find(query, {"_id": 0, "device_id": 1, "id": 1}))
    
    @staticmethod
    def create_local_device_tasks(
        request_id: str,
        org_id: str,
        request_type: str,
        identifier: str,
        new_value: Optional[str],
        device_ids: Optional[List[str]],
        expires_at: datetime,
    ) -> List[dict]:
        """
        Creates request_tasks for all org's approved devices.
        
        Returns list of created task IDs for tracking.
        """
        target_devices = RequestStateManager.filter_org_devices(org_id, device_ids)
        
        if not target_devices:
            return []
        
        action_type = request_type.lower()
        if action_type == "update" or action_type == "correction":
            packed_query = f"{identifier}::{new_value or ''}"
        else:
            packed_query = identifier
        
        task_group_id = str(uuid4())
        created_tasks = []
        now = utc_now()
        
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
                "status": "pending",
                "created_at": now,
                "expires_at": expires_at,
                "updated_at": now,
                "completed_at": None,
            }
            
            request_tasks.insert_one(task_doc)
            created_tasks.append({
                "task_id": task_id,
                "device_id": device_id,
                "status": "pending",
                "expires_at": expires_at.isoformat(),
            })
        
        return created_tasks
