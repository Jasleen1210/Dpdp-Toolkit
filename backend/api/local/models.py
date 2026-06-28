from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    device_id: str
    hostname: str
    agent_version: str
    organisation_id: Optional[str] = None

class DeviceApprovalRequest(BaseModel):
    device_id: str
    approved: bool = True

class DeviceHeartbeatRequest(BaseModel):
    device_id: str

class CreateTaskRequest(BaseModel):
    query: str
    device_ids: List[str] = Field(default_factory=list)
    expires_in_hours: int = 24

class MatchItem(BaseModel):
    type: str
    value: str
    file: str

class SubmitResultRequest(BaseModel):
    task_id: str
    device_id: str
    status: str
    scanned_files: int = 0
    matches: List[MatchItem] = Field(default_factory=list)

class StandaloneScanResultRequest(BaseModel):
    device_id: str
    status: str = "completed"
    scanned_files: int = 0
    matches: List[MatchItem] = Field(default_factory=list)

class CronRunRequest(BaseModel):
    run_id: Optional[str] = Field(default=None)
    device_id: str
    task_type: str = Field(..., description="e.g., 'standalone_daily_pii'")
    status: str = Field(..., description="'started', 'completed', or 'failed'")
    started_at: datetime
    duration: Optional[str] = None
    error: Optional[str] = None

class VulnerabilityItemRequest(BaseModel):
    title: str
    data_type: str
    exposure_type: str
    priority_score: float = Field(..., ge=0.0, le=1.0)
    match_count: int
    path_or_port: str
    status: str = "unresolved"

class VulnerabilityReportPayload(BaseModel):
    device_id: str
    cron_run_id: str
    vulnerabilities: List[VulnerabilityItemRequest]

class UserRemediationRequest(BaseModel):
    device_id: str
    action_type: str = Field(..., description="'update' or 'delete'")
    target_file_path: str
    target_data_type: str
    target_value: str
    new_value: Optional[str] = None

class TaskCreateRequest(BaseModel):
    type: Literal["access", "update", "delete"]
    device_id: str
    query: str
    task_group_id: Optional[str] = None

class RemediationTaskRequest(BaseModel):
    device_id: str
    action_type: Literal["access", "update", "delete"]
    target_value: str
    new_value: Optional[str] = None