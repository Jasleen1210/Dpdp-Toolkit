package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
 
	"github.com/kardianos/service"
 
	"dpdp-toolkit/agent-go/internal/client"
	"dpdp-toolkit/agent-go/internal/config"
	"dpdp-toolkit/agent-go/internal/device"
	"dpdp-toolkit/agent-go/internal/gui"
	"dpdp-toolkit/agent-go/internal/scanner"
	"dpdp-toolkit/agent-go/internal/types"
)

const agentVersion = "0.1.0"

var istLocation = time.FixedZone("Asia/Kolkata", 5*60*60+30*60)

type program struct {
	cfg    config.Config
	cancel context.CancelFunc
	wg     sync.WaitGroup
}

func (p *program) Start(s service.Service) error {
	ctx, cancel := context.WithCancel(context.Background())
	p.cancel = cancel
 
	p.wg.Add(1)
	go func() {
		defer p.wg.Done()
		p.run(ctx)
	}()
	return nil
}
 
func (p *program) Stop(s service.Service) error {
	if p.cancel != nil {
		p.cancel()
	}
	done := make(chan struct{})
	go func() {
		p.wg.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(10 * time.Second):
		log.Printf("stop timeout: forcing shutdown")
	}
	return nil
}
 
func (p *program) run(ctx context.Context) {
	cfg := p.cfg
 
	deviceID := device.ResolveDeviceID(cfg.DeviceID)
	hostname := device.ResolveHostname()
 
	log.Printf("agent starting: device_id=%s host=%s server=%s", deviceID, hostname, cfg.ServerURL)

	apiClient := client.New(cfg)
	scanEngine := scanner.New(cfg)

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

	var wg sync.WaitGroup
	wg.Add(2)
 
	sinceCursor := ""
	go func() {
		defer wg.Done()
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

	go func() {
		defer wg.Done()
		runStandaloneScanLoop(ctx, apiClient, scanEngine, deviceID, cfg.ScanInterval)
	}()

	wg.Wait()
	log.Printf("agent stopped")
}
 
func serviceConfig() *service.Config {
	workingDir := ""
	if exe, err := os.Executable(); err == nil {
		if resolved, err := filepath.EvalSymlinks(exe); err == nil {
			exe = resolved
		}
		workingDir = filepath.Dir(exe)
	}
 
	return &service.Config{
		Name:             "dpdp-agent",
		DisplayName:      "DPDP Local Agent",
		Description:      "Scans local files for personal data and executes DPDP remediation tasks.",
		Arguments:        []string{"run"},
		WorkingDirectory: workingDir,
		Option: service.KeyValue{
			// launchd (macOS): start at login and keep the agent alive.
			"RunAtLoad":   true,
			"KeepAlive":   true,
			"UserService": true,
			// Windows service / systemd: restart automatically after a crash.
			"OnFailure":                    "restart",
			"OnFailureDelayDuration":       "10s",
			"OnFailureResetPeriod":         10,
			"Restart":                      "always",
			"DelayedAutoStart":             true,
			"LogDirectory":                 workingDir,
		},
	}
}
 
func main() {
	cfg := config.Load()
	log.Printf("debug: org_id=%q server=%q", cfg.OrgID, cfg.ServerURL)
 
	prg := &program{cfg: cfg}
	svc, err := service.New(prg, serviceConfig())
	if err != nil {
		log.Fatalf("service init failed: %v", err)
	}
 
	command := "run"
	if len(os.Args) > 1 {
		command = strings.ToLower(strings.TrimSpace(os.Args[1]))
	}
 
	switch command {
	case "install", "uninstall", "start", "stop", "restart":
		if err := service.Control(svc, command); err != nil {
			log.Fatalf("%s failed: %v", command, err)
		}
		if command == "install" {
			if err := service.Control(svc, "start"); err != nil {
				log.Printf("service installed but start failed: %v", err)
			}
		}
		log.Printf("service %s: ok", command)
	case "status":
		status, err := svc.Status()
		if err != nil {
			log.Fatalf("status failed: %v", err)
		}
		fmt.Println(statusLabel(status))
	case "run":
		if service.Interactive() {
			prg.cfg = promptForScanPathsIfNeeded(cfg)
		}
		if err := svc.Run(); err != nil {
			log.Fatalf("run failed: %v", err)
		}
	default:
		fmt.Printf("usage: %s [run|install|uninstall|start|stop|restart|status]\n", filepath.Base(os.Args[0]))
		os.Exit(2)
	}
}
 
func statusLabel(status service.Status) string {
	switch status {
	case service.StatusRunning:
		return "running"
	case service.StatusStopped:
		return "stopped"
	default:
		return "unknown"
	}
}
 
func promptForScanPathsIfNeeded(cfg config.Config) config.Config {
	if len(cfg.ScanPaths) == 0 || !isUsingDefaultPaths(cfg.ScanPaths) {
		return cfg
	}
 
	log.Printf("No custom scan paths configured. Prompting for folder selection...")
	selectedPath := gui.PromptFolderSelection(cfg.ScanPaths, true)
	if selectedPath == "" {
		return cfg
	}
 
	log.Printf("User selected path: %s", selectedPath)
	paths := strings.Split(selectedPath, ",")
	for i, p := range paths {
		paths[i] = strings.TrimSpace(p)
	}
	cfg.ScanPaths = paths
	return cfg
}