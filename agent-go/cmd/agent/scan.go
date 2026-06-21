package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"dpdp-toolkit/agent-go/internal/client"
	"dpdp-toolkit/agent-go/internal/scanner"
	"dpdp-toolkit/agent-go/internal/types"
)

func runStandaloneScanLoop(ctx context.Context, apiClient *client.Client, scanEngine *scanner.Engine, deviceID string, interval time.Duration) {
	checkInterval := time.Minute
	if interval > 0 && interval < checkInterval {
		checkInterval = interval
	}

	ticker := time.NewTicker(checkInterval)
	defer ticker.Stop()

	lastISTScanDate := ""
	firstStandaloneRunDone := false

	maybeRunDailyScan := func() {
		todayIST := currentISTDate()

		if firstStandaloneRunDone && todayIST == lastISTScanDate {
			return
		}

		if !firstStandaloneRunDone {
			log.Printf("standalone baseline scan due (First Agent Run - Scanning everything): ist_date=%s", todayIST)
		} else {
			log.Printf("standalone incremental daily scan due: ist_date=%s", todayIST)
		}

		startTime := time.Now()
		cronType := "standalone_daily_pii"

		var trackingID string
		resp, cronErr := apiClient.SubmitCronRun(ctx, types.CronRunPayload{
			DeviceID:  deviceID,
			TaskType:  cronType,
			Status:    "started",
			StartedAt: startTime,
		})
		if cronErr != nil {
			log.Printf("failed reporting cron start upstream: %v", cronErr)
		} else if resp != nil && resp.RunID != "" {
			trackingID = resp.RunID
			log.Printf("Successfully registered run session. Tracking ID from DB: %s", trackingID)
		}

		err := runStandaloneScanCycle(ctx, apiClient, scanEngine, deviceID, trackingID, firstStandaloneRunDone)

		duration := time.Since(startTime).String()
		status := "completed"
		errStr := ""
		if err != nil {
			status = "failed"
			errStr = err.Error()
			log.Printf("standalone daily scan routine failed: %v", err)
		}

		if _, finalCronErr := apiClient.SubmitCronRun(ctx, types.CronRunPayload{
			RunID:     trackingID,
			DeviceID:  deviceID,
			TaskType:  cronType,
			Status:    status,
			StartedAt: startTime,
			Duration:  duration,
			Error:     errStr,
		}); finalCronErr != nil {
			log.Printf("failed reporting cron status upstream: %v", finalCronErr)
		} else {
			log.Printf("Successfully updated run session %s to status: %s", trackingID, status)
		}

		firstStandaloneRunDone = true
		lastISTScanDate = todayIST
	}

	maybeRunDailyScan()

	for range ticker.C {
		maybeRunDailyScan()
	}
}

func runStandaloneScanCycle(ctx context.Context, apiClient *client.Client, scanEngine *scanner.Engine, deviceID string, trackingID string, apply24HourFilter bool) error {
	log.Printf("starting standalone pii scan: device_id=%s", deviceID)

	modifiedSince := time.Time{}
	if apply24HourFilter {
		modifiedSince = time.Now().Add(-24 * time.Hour)
	}

	matches, scannedFiles := scanEngine.ScanPII(modifiedSince)

	type groupKey struct {
		path  string
		dType string
	}
	grouped := make(map[groupKey]int)
	for _, m := range matches {
		grouped[groupKey{path: m.File, dType: m.Type}]++
	}

	vulns := make([]types.VulnerabilityItem, 0)
	now := time.Now()
	for key, count := range grouped {
		priority := 0.5 + (float64(count) * 0.01)
		if priority > 1.0 {
			priority = 1.0
		}
		vulns = append(vulns, types.VulnerabilityItem{
			Title:         fmt.Sprintf("Unencrypted %s Leak Found", key.dType),
			DataType:      key.dType,
			ExposureType:  "local_file",
			PriorityScore: priority,
			MatchCount:    count,
			PathOrPort:    key.path,
			Status:        "unresolved",
			DetectedAt:    now,
		})
	}

	if err := apiClient.SubmitVulnerabilities(ctx, types.VulnerabilityReportPayload{
		DeviceID:        deviceID,
		CronRunID:       trackingID,
		Vulnerabilities: vulns,
	}); err != nil {
		log.Printf("failed to report vulnerabilities upstream: %v", err)
	}

	return apiClient.SubmitLatestResult(ctx, types.TaskResultPayload{
		DeviceID:     deviceID,
		Status:       "completed",
		ScannedFiles: scannedFiles,
		Matches:      matches,
	})
}