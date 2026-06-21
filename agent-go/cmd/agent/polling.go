package main

import (
	"context"
	"log"
	"strings"

	"dpdp-toolkit/agent-go/internal/client"
	"dpdp-toolkit/agent-go/internal/scanner"
	"dpdp-toolkit/agent-go/internal/types"
)

func runTaskPollingCycle(ctx context.Context, apiClient *client.Client, scanEngine *scanner.Engine, deviceID string, since *string) {
	if err := apiClient.Heartbeat(ctx, deviceID); err != nil {
		log.Printf("heartbeat warning: %v", err)
	}

	pollRes, err := apiClient.FetchTaskPoll(ctx, deviceID, *since)
	if err != nil {
		log.Printf("fetch tasks error: %v", err)
		return
	}

	if pollRes.HasUpdates {
		log.Printf("task updates available: count=%d", len(pollRes.Updates))
	}

	if pollRes.NextCursor != "" {
		*since = pollRes.NextCursor
	}

	tasks := pollRes.Tasks
	if len(tasks) == 0 {
		log.Printf("no pending tasks")
		return
	}

	for _, task := range tasks {
		if (task.Type == "update" || task.Type == "delete") && task.Status == "pending" {
			processRemediationTask(ctx, apiClient, scanEngine, deviceID, task)
		}
	}
}

func processRemediationTask(ctx context.Context, apiClient *client.Client, scanEngine *scanner.Engine, deviceID string, task types.Task) {
	log.Printf("[REMEDIATION] Starting search-before-change for target: %s", task.Query)

	targetValue := task.Query
	newValue := ""
	if task.Type == "update" {
		parts := strings.Split(task.Query, "::")
		if len(parts) < 2 {
			log.Printf("Error: invalid update query format")
			return
		}
		targetValue = parts[0]
		newValue = parts[1]
	}

	scanTask := task
	scanTask.Type = "access"
	scanTask.Query = targetValue
	matches, _ := scanEngine.ScanTask(scanTask)

	if len(matches) == 0 {
		log.Printf("[REMEDIATION] Target value '%s' not found anywhere on device. Task skipped.", targetValue)
		apiClient.SubmitResult(ctx, types.TaskResultPayload{TaskID: task.ID, DeviceID: deviceID, Status: "completed"})
		return
	}

	status := "completed"
	for _, match := range matches {
		log.Printf("[REMEDIATION] Modifying file: %s", match.File)
		if err := modifyLocalFile(match.File, task.Type, targetValue, newValue); err != nil {
			log.Printf("Failed to modify %s: %v", match.File, err)
			status = "failed"
		}
	}

	apiClient.SubmitResult(ctx, types.TaskResultPayload{
		TaskID:   task.ID,
		DeviceID: deviceID,
		Status:   status,
	})
}