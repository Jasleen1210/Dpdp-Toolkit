package main

import (
	"context"
	"log"
	"runtime"
	"strings"
	"time"

	"dpdp-toolkit/agent-go/internal/client"
	"dpdp-toolkit/agent-go/internal/config"
	"dpdp-toolkit/agent-go/internal/device"
	"dpdp-toolkit/agent-go/internal/gui"
	"dpdp-toolkit/agent-go/internal/scanner"
	"dpdp-toolkit/agent-go/internal/types"
)

const agentVersion = "0.1.0"

func main() {
	cfg := config.Load()
	deviceID := device.ResolveDeviceID(cfg.DeviceID)
	hostname := device.ResolveHostname()

	log.Printf("agent starting: device_id=%s host=%s server=%s", deviceID, hostname, cfg.ServerURL)

	// On Windows with default scan paths, prompt user for folder selection via GUI
	if runtime.GOOS == "windows" && len(cfg.ScanPaths) > 0 && isUsingDefaultPaths(cfg.ScanPaths) {
		log.Printf("No custom scan paths configured. Prompting for folder selection...")
		selectedPath := gui.PromptFolderSelectionWindows(cfg.ScanPaths, true)
		if selectedPath != "" {
			log.Printf("User selected path: %s", selectedPath)
			cfg.ScanPaths = strings.Split(selectedPath, ",")
			for i, p := range cfg.ScanPaths {
				cfg.ScanPaths[i] = strings.TrimSpace(p)
			}
		}
	}

	apiClient := client.New(cfg)
	scanEngine := scanner.New(cfg)

	ctx := context.Background()
	if err := apiClient.Register(ctx, types.DeviceRegistrationRequest{
		DeviceID:     deviceID,
		Hostname:     hostname,
		AgentVersion: agentVersion,
	}); err != nil {
		log.Printf("register warning: %v", err)
	}

	lastTaskUpdateCursor := ""

	ticker := time.NewTicker(cfg.PollInterval)
	defer ticker.Stop()

	for {
		lastTaskUpdateCursor = runCycle(ctx, apiClient, scanEngine, deviceID, lastTaskUpdateCursor)
		<-ticker.C
	}
}

func runCycle(ctx context.Context, apiClient *client.Client, scanEngine *scanner.Engine, deviceID, since string) string {
	pollRes, err := apiClient.FetchTaskPoll(ctx, deviceID, since)
	if err != nil {
		log.Printf("fetch tasks error: %v", err)
		return since
	}

	if pollRes.HasUpdates {
		log.Printf("task updates available: count=%d", len(pollRes.Updates))
	}

	nextCursor := since
	if pollRes.NextCursor != "" {
		nextCursor = pollRes.NextCursor
	}

	tasks := pollRes.Tasks

	if len(tasks) == 0 {
		log.Printf("no pending tasks")
		return nextCursor
	}

	for _, task := range tasks {
		if task.IsExpired(time.Now()) {
			log.Printf("skip expired task: %s", task.ID)
			continue
		}

		log.Printf("processing task: id=%s query=%q", task.ID, task.Query)
		matches, scannedFiles := scanEngine.ScanTask(task)

		payload := types.TaskResultPayload{
			TaskID:      task.ID,
			DeviceID:    deviceID,
			Status:      "completed",
			ScannedFiles: scannedFiles,
			Matches:     matches,
		}

		if err := apiClient.SubmitResult(ctx, payload); err != nil {
			log.Printf("submit result error for task=%s: %v", task.ID, err)
			continue
		}

		log.Printf("task completed: id=%s matches=%d scanned_files=%d", task.ID, len(matches), scannedFiles)
	}

	return nextCursor
}

// isUsingDefaultPaths checks if the scan paths are system defaults (not user-configured)
func isUsingDefaultPaths(paths []string) bool {
	if len(paths) == 0 {
		return true
	}
	// Check if all paths are drive roots (C:\, D:\, etc.) or Unix root
	for _, p := range paths {
		if len(p) == 3 && p[1] == ':' && p[2] == '\\' {
			// Windows drive root like C:\
			continue
		}
		if p == "/" {
			// Unix root
			continue
		}
		// If any custom path exists, consider it user-configured
		return false
	}
	return true
}
