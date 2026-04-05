package types

import "time"

type DeviceRegistrationRequest struct {
	DeviceID     string `json:"device_id"`
	Hostname     string `json:"hostname"`
	AgentVersion string `json:"agent_version"`
}

type Task struct {
	ID        string   `json:"id"`
	Query     string   `json:"query"`
	CreatedAt string   `json:"created_at,omitempty"`
	ExpiresAt string   `json:"expires_at,omitempty"`
	Paths     []string `json:"paths,omitempty"`
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
	if t.ExpiresAt == "" {
		return false
	}
	tm, err := time.Parse(time.RFC3339, t.ExpiresAt)
	if err != nil {
		return false
	}
	return now.After(tm)
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
