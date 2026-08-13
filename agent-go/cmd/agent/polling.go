package main

import (
	"context"
	"log"
	"sort"
	"strings"

	"dpdp-toolkit/agent-go/internal/client"
	"dpdp-toolkit/agent-go/internal/scanner"
	"dpdp-toolkit/agent-go/internal/types"
)

type remediationPlan struct {
	task               types.Task
	targetValue        string
	newValue           string
	matches            []types.Match
	scannedFiles       int
	deleteReplacements []types.DeleteReplacement
}

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

	sort.SliceStable(tasks, func(i, j int) bool {
		a, b := tasks[i], tasks[j]
		if a.CreatedAt.IsZero() && b.CreatedAt.IsZero() {
			return a.ID < b.ID
		}
		if a.CreatedAt.IsZero() {
			return false
		}
		if b.CreatedAt.IsZero() {
			return true
		}
		if a.CreatedAt.Equal(b.CreatedAt) {
			return a.ID < b.ID
		}
		return a.CreatedAt.Before(b.CreatedAt)
	})

	plans := make([]remediationPlan, 0, len(tasks))

	for _, task := range tasks {
		log.Printf("DEBUG task: id=%s type=%q status=%q query=%q", task.ID, task.Type, task.Status, task.Query)

		if task.Status != "pending" {
			continue
		}

		// Case A: Handle remediation actions
		if task.Type == "update" || task.Type == "delete" {
			plan, ok := prepareRemediationTask(ctx, apiClient, scanEngine, deviceID, task)
			if ok {
				plans = append(plans, plan)
			}
			continue
		}

		// Case B: Handle data discovery actions
		if task.Type == "access" {
			log.Printf("[ACCESS] Running targeted search sequence for string: %q", task.Query)

			scanTask := task
			scanTask.Type = "access"
			scanTask.Query = task.Query

			matches, scannedFiles := scanEngine.ScanTask(scanTask)

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
				TaskID:       task.ID,
				DeviceID:     deviceID,
				Status:       "completed",
				ScannedFiles: scannedFiles,
				Matches:      matches,
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

	for _, plan := range plans {
		applyRemediationPlan(ctx, apiClient, plan)
	}
}

func prepareRemediationTask(ctx context.Context, apiClient *client.Client, scanEngine *scanner.Engine, deviceID string, task types.Task) (remediationPlan, bool) {
	log.Printf("[REMEDIATION] Starting search-before-change for target: %s", task.Query)

	targetValue := task.Query
	newValue := ""
	if task.Type == "update" {
		parts := strings.Split(task.Query, "::")
		if len(parts) < 2 {
			log.Printf("Error: invalid update query format")
			return remediationPlan{}, false
		}
		targetValue = parts[0]
		newValue = parts[1]
	}

	scanTask := task
	scanTask.Type = "access"
	scanTask.Query = targetValue
	matches, scannedFiles := scanEngine.ScanTask(scanTask)
	if matches == nil {
		matches = []types.Match{}
	}

	plan := remediationPlan{
		task:         task,
		targetValue:  targetValue,
		newValue:     newValue,
		matches:      matches,
		scannedFiles: scannedFiles,
	}

	if task.Type == "delete" {
		for _, match := range matches {
			deleteResult, _, deleteErr := buildDeleteRedaction(match.File, targetValue)
			if deleteErr != nil {
				log.Printf("[DELETE] preview build failed file=%s err=%v", match.File, deleteErr)
				return remediationPlan{}, false
			}
			if len(deleteResult.entries) > 0 {
				plan.deleteReplacements = append(plan.deleteReplacements, deleteResult.entries...)
			}
		}
	}

	apiClient.SubmitResult(ctx, types.TaskResultPayload{
		TaskID:             task.ID,
		DeviceID:           deviceID,
		Status:             "completed",
		ScannedFiles:       scannedFiles,
		Matches:            matches,
		DeleteReplacements: plan.deleteReplacements,
	})

	if len(matches) == 0 {
		log.Printf("[REMEDIATION] Target value '%s' not found anywhere on device. Task skipped.", targetValue)
		return remediationPlan{}, false
	}

	return plan, true
}

func applyRemediationPlan(ctx context.Context, apiClient *client.Client, plan remediationPlan) {
	if plan.task.Type == "delete" {
		applyDeletePlan(ctx, apiClient, plan)
		return
	}

	status := "completed"
	for _, match := range plan.matches {
		log.Printf("[REMEDIATION] Modifying file: %s", match.File)
		if err := modifyLocalFile(match.File, plan.task.Type, plan.targetValue, plan.newValue); err != nil {
			log.Printf("Failed to modify %s: %v", match.File, err)
			status = "failed"
		}
	}

	if status != "completed" {
		apiClient.SubmitResult(ctx, types.TaskResultPayload{
			TaskID:       plan.task.ID,
			DeviceID:     plan.task.DeviceID,
			Status:       status,
			ScannedFiles: plan.scannedFiles,
			Matches:      plan.matches,
		})
	}
}
