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
		log.Printf("DEBUG task: id=%s type=%q status=%q query=%q", task.ID, task.Type, task.Status, task.Query)

		if task.Status != "pending" {
			continue
		}

		// Case A: Handle remediation actions
		if task.Type == "update" || task.Type == "delete" {
			processRemediationTask(ctx, apiClient, scanEngine, deviceID, task)
			continue
		}

		// Case B: Handle data discovery actions
		if task.Type == "access" {
			log.Printf("[ACCESS] Running targeted search sequence for string: %q", task.Query)

			scanTask := task
			scanTask.Type = "access"
			scanTask.Query = task.Query

			matches, _ := scanEngine.ScanTask(scanTask)

			// ADD THIS TEMPORARY DEBUG LOOP HERE:
			log.Printf("--- START MATCH INSPECTION ---")
			for i, m := range matches {
				// This will print exactly what properties exist on the matches your engine returns
				log.Printf("Match [%d]: File=%s, Value=%s, Type=%s", i, m.File, m.Value, m.Type)
			}
			log.Printf("--- END MATCH INSPECTION ---")

			log.Printf("[ACCESS] Verification complete for %s. Found %d verified locations.", task.ID, len(matches))

			// Ensure matches is never nil — always send an empty list
			if matches == nil {
				matches = []types.Match{}
			}

			err := apiClient.SubmitResult(ctx, types.TaskResultPayload{
				TaskID:   task.ID,
				DeviceID: deviceID,
				Status:   "completed",
				Matches:  matches,
			})

			// 3. CRITICAL: Catch why the backend isn't saving the completed status!
			if err != nil {
				log.Printf("[ACCESS] ERROR: Failed to mark task %s as completed upstream: %v", task.ID, err)
			} else {
				log.Printf("[ACCESS] Success: Task %s status updated to completed in remote DB.", task.ID)
			}
			continue
		}

		log.Printf("Warning: unhandled task type %q", task.Type)
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
