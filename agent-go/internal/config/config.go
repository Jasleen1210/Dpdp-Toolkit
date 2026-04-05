package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	ServerURL      string
	APIKey         string
	OrgID          string
	PollInterval   time.Duration
	DeviceID       string
	ScanPaths      []string
	IncludeExts    map[string]struct{}
	MaxFileSizeMB  int64
	RegisterPath   string
	TasksPath      string
	ResultsPath    string
}

func Load() Config {
	poll := parseDuration(getEnv("POLL_INTERVAL", "5m"), 5*time.Minute)
	scanPaths := splitCSV(getEnv("SCAN_PATHS", "C:/Users"))
	exts := splitCSV(getEnv("INCLUDE_EXTENSIONS", "*"))
	maxSize := parseInt64(getEnv("MAX_FILE_SIZE_MB", "5"), 5)

	return Config{
		ServerURL:     strings.TrimRight(getEnv("SERVER_URL", "http://localhost:8000"), "/"),
		APIKey:        getEnv("API_KEY", ""),
		OrgID:         getEnv("ORG_ID", "dpdp-org"),
		PollInterval:  poll,
		DeviceID:      getEnv("DEVICE_ID", ""),
		ScanPaths:     scanPaths,
		IncludeExts:   normalizeExtMap(exts),
		MaxFileSizeMB: maxSize,
		RegisterPath:  normalizePath(getEnv("REGISTER_PATH", "/devices/register")),
		TasksPath:     normalizePath(getEnv("TASKS_PATH", "/devices/tasks")),
		ResultsPath:   normalizePath(getEnv("RESULTS_PATH", "/results")),
	}
}

func getEnv(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
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

func parseDuration(v string, fallback time.Duration) time.Duration {
	d, err := time.ParseDuration(v)
	if err != nil {
		return fallback
	}
	return d
}

func parseInt64(v string, fallback int64) int64 {
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		return fallback
	}
	return n
}

func normalizePath(v string) string {
	if strings.HasPrefix(v, "/") {
		return v
	}
	return "/" + v
}
