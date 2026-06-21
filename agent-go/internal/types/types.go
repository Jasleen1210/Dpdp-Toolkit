package types

import "time"

type DeviceRegistrationRequest struct {
	DeviceID     string `json:"device_id"`
	Hostname     string `json:"hostname"`
	AgentVersion string `json:"agent_version"`
}

type Task struct {
	ID             string    `json:"id"`
	TaskGroupID    string    `json:"task_group_id"`
	OrganisationID string    `json:"organisation_id"`
	DeviceID       string    `json:"device_id"`
	Query          string    `json:"query"`       // Format: "FILE_PATH::TARGET_VALUE" or "FILE_PATH::TARGET_VALUE::NEW_VALUE"
	Status         string    `json:"status"`
	Type           string    `json:"type"`         // "update" or "delete"
	CreatedAt      time.Time `json:"created_at"`
	ExpiresAt      time.Time `json:"expires_at"`
}

type TaskListResponse struct {
	Tasks []Task `json:"tasks"`
}

type TaskUpdate struct {
	ID          string `json:"id"`
	TaskGroupID string `json:"task_group_id,omitempty"`
	DeviceID    string `json:"device_id,omitempty"`
	Status      string `json:"status,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
	CompletedAt string `json:"completed_at,omitempty"`
	ExpiresAt   string `json:"expires_at,omitempty"`
}

type TaskPollResponse struct {
	Tasks      []Task       `json:"tasks"`
	Updates    []TaskUpdate `json:"updates"`
	HasUpdates bool         `json:"has_updates"`
	NextCursor string       `json:"next_cursor"`
}

func (t Task) IsExpired(now time.Time) bool {
	if t.ExpiresAt.IsZero() {
		return false
	}
	// No parsing needed! Just compare the two time.Time objects directly
	return now.After(t.ExpiresAt)
}

type Match struct {
	Type  string `json:"type"`
	Value string `json:"value"`
	File  string `json:"file"`
}

type TaskResultPayload struct {
	TaskID       string  `json:"task_id"`
	DeviceID     string  `json:"device_id"`
	Status       string  `json:"status"`
	ScannedFiles int     `json:"scanned_files"`
	Matches      []Match `json:"matches"`
}

type FindingEntry struct {
	FileName        string `json:"file_name"`
	Path            string `json:"path"`
	DataType        string `json:"data_type"`
	Status          string `json:"status"` // "unprotected" or "protected"
	FirstDetectedAt string `json:"first_detected_at"`
	LastSeenAt      string `json:"last_seen_at"`
	ResolvedAt      string `json:"resolved_at,omitempty"`
}

type CronRunSummary struct {
	TotalFindings int `json:"total_findings"`
	Unprotected   int `json:"unprotected"`
	Protected     int `json:"protected"`
}

type CronRunPayload struct {
	RunID     string    `json:"run_id,omitempty"`
	DeviceID  string    `json:"device_id"`
	TaskType  string    `json:"task_type"`  // e.g., "standalone_daily_pii"
	Status    string    `json:"status"`     // "started", "completed", "failed"
	StartedAt time.Time `json:"started_at"`
	Duration  string    `json:"duration,omitempty"`
	Error     string    `json:"error,omitempty"`
}

type CronRunResponse struct {
	Status    string `json:"status"`
	RunID     string `json:"run_id"`
	RunStatus string `json:"run_status"`
}

type VulnerabilityItem struct {
	Title         string    `json:"title"`
	DataType      string    `json:"data_type"`
	ExposureType  string    `json:"exposure_type"`
	PriorityScore float64   `json:"priority_score"`
	MatchCount    int       `json:"match_count"`
	PathOrPort    string    `json:"path_or_port"`
	Status        string    `json:"status"`
	DetectedAt    time.Time `json:"detected_at"`
	ResolvedAt    *time.Time`json:"resolved_at"`
}

type VulnerabilityReportPayload struct {
	DeviceID       string              `json:"device_id"`
	OrganisationID string              `json:"organisation_id"`
	CronRunID      string              `json:"cron_run_id"`
	Vulnerabilities []VulnerabilityItem `json:"vulnerabilities"`
}

type TaskPayload struct {
	ActionType  string `json:"action_type"`
	FilePath    string `json:"file_path"`
	TargetValue string `json:"target_value"`
	NewValue    string `json:"new_value"`
}