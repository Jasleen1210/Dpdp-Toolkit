package main

import (
	"context"
	"log"
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

var istLocation = time.FixedZone("Asia/Kolkata", 5*60*60+30*60)

func main() {
	cfg := config.Load()

	log.Printf("debug: org_id=%q server=%q", cfg.OrgID, cfg.ServerURL)

	deviceID := device.ResolveDeviceID(cfg.DeviceID)
	hostname := device.ResolveHostname()

	log.Printf("agent starting: device_id=%s host=%s server=%s", deviceID, hostname, cfg.ServerURL)

	if len(cfg.ScanPaths) > 0 && isUsingDefaultPaths(cfg.ScanPaths) {
		log.Printf("No custom scan paths configured. Prompting for folder selection...")
		selectedPath := gui.PromptFolderSelection(cfg.ScanPaths, true)
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

	if err := apiClient.Health(ctx); err != nil {
		log.Printf("health check warning: %v", err)
	}

	if err := apiClient.Register(ctx, types.DeviceRegistrationRequest{
		DeviceID:     deviceID,
		Hostname:     hostname,
		AgentVersion: agentVersion,
	}); err != nil {
		log.Printf("register warning: %v", err)
	}

	if err := apiClient.Heartbeat(ctx, deviceID); err != nil {
		log.Printf("heartbeat warning: %v", err)
	}

	sinceCursor := ""
	go func() {
		ticker := time.NewTicker(cfg.PollInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				runTaskPollingCycle(ctx, apiClient, scanEngine, deviceID, &sinceCursor)
			}
		}
	}()

	go runStandaloneScanLoop(ctx, apiClient, scanEngine, deviceID, cfg.ScanInterval)

	select {}
}