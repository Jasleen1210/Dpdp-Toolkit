package config

import (
	"os"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

var (
	BuiltServerURL string
	BuiltAPIKey    string
	BuiltOrgID     string
)

type Config struct {
	ServerURL      string
	APIKey         string
	OrgID          string
	PollInterval   time.Duration
	ScanInterval   time.Duration
	DeviceID       string
	ScanPaths      []string
	IncludeExts    map[string]struct{}
	MaxFileSizeMB  int64
	RegisterPath   string
	TasksPath      string
	ResultsPath    string
	CronRunsPath          string
FindingsCheckInterval time.Duration
}

func Load() Config {
	_ = godotenv.Load()

	pollInterval := mustParseDuration(firstNonEmpty(os.Getenv("POLL_INTERVAL"), "30s"))
	scanInterval := mustParseDuration(firstNonEmpty(os.Getenv("SCAN_INTERVAL"), "24h"))
	scanPaths := splitCSV(firstNonEmpty(os.Getenv("SCAN_PATHS"), strings.Join(defaultScanPaths(), ",")))
	if len(scanPaths) == 0 {
		scanPaths = defaultScanPaths()
	}
	exts := splitCSV(firstNonEmpty(os.Getenv("INCLUDE_EXTENSIONS"), "*"))
	if len(exts) == 0 {
		exts = []string{"*"}
	}
	maxSize := mustParseInt64(firstNonEmpty(os.Getenv("MAX_FILE_SIZE_MB"), "5"))

	return Config{
		ServerURL:     strings.TrimRight(firstNonEmpty(BuiltServerURL, os.Getenv("SERVER_URL"), "http://127.0.0.1:8000"), "/"),
		APIKey:        firstNonEmpty(BuiltAPIKey, os.Getenv("API_KEY")),
		OrgID:         firstNonEmpty(BuiltOrgID, os.Getenv("ORG_ID")),
		PollInterval:  pollInterval,
		ScanInterval:  scanInterval,
		DeviceID:      firstNonEmpty(os.Getenv("DEVICE_ID"), ""),
		ScanPaths:     scanPaths,
		IncludeExts:   normalizeExtMap(exts),
		MaxFileSizeMB: maxSize,
		RegisterPath:  normalizePath(firstNonEmpty(os.Getenv("REGISTER_PATH"), "/devices/register")),
		TasksPath:     normalizePath(firstNonEmpty(os.Getenv("TASKS_PATH"), "/devices/tasks")),
		ResultsPath:   normalizePath(firstNonEmpty(os.Getenv("RESULTS_PATH"), "/results")),
		CronRunsPath:          normalizePath(firstNonEmpty(os.Getenv("CRON_RUNS_PATH"), "/devices/cron-runs")),
FindingsCheckInterval: mustParseDuration(firstNonEmpty(os.Getenv("FINDINGS_CHECK_INTERVAL"), "1h")),
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func splitCSV(v string) []string {
	parts := strings.Split(v, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		t := strings.TrimSpace(p)
		if t != "" {
			out = append(out, t)
		}
	}
	return out
}

func normalizeExtMap(exts []string) map[string]struct{} {
	m := make(map[string]struct{}, len(exts))
	for _, ext := range exts {
		e := strings.ToLower(strings.TrimSpace(ext))
		if e == "" {
			continue
		}
		if e == "*" {
			m["*"] = struct{}{}
			continue
		}
		if !strings.HasPrefix(e, ".") {
			e = "." + e
		}
		m[e] = struct{}{}
	}
	return m
}

func defaultScanPaths() []string {
	switch runtime.GOOS {
	case "windows":
		paths := make([]string, 0, 4)
		for drive := 'C'; drive <= 'Z'; drive++ {
			root := string(drive) + ":\\"
			if _, err := os.Stat(root); err == nil {
				paths = append(paths, root)
			}
		}
		if len(paths) > 0 {
			return paths
		}
		return []string{"C:\\"}

	case "darwin":
		// Default to the current user's home directory on macOS
		if home, err := os.UserHomeDir(); err == nil && home != "" {
			return []string{home}
		}
		return []string{"/Users"}

	default: // linux
		if home, err := os.UserHomeDir(); err == nil && home != "" {
			return []string{home}
		}
		return []string{"/home"}
	}
}

func mustParseDuration(v string) time.Duration {
	d, err := time.ParseDuration(v)
	if err != nil {
		panic("invalid duration value: " + err.Error())
	}
	return d
}

func mustParseInt64(v string) int64 {
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		panic("invalid MAX_FILE_SIZE_MB: " + err.Error())
	}
	return n
}

func normalizePath(v string) string {
	if strings.HasPrefix(v, "/") {
		return v
	}
	return "/" + v
}
