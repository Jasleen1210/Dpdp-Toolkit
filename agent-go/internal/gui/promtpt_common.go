package gui

import (
    "fmt"
    "os"
    "strings"
)

func isDefaultPath(p string) bool {
    if strings.HasSuffix(p, "\\") && len(p) == 3 {
        return true
    }
    return p == "/" || p == os.Getenv("HOME")
}

func writePathToEnv(path string) {
    envPath := ".env"
    if _, err := os.Stat(envPath); err == nil {
        content, _ := os.ReadFile(envPath)
        lines := strings.Split(string(content), "\n")
        updated := false
        for i, line := range lines {
            if strings.HasPrefix(strings.TrimSpace(line), "SCAN_PATHS=") {
                lines[i] = fmt.Sprintf("SCAN_PATHS=%s", path)
                updated = true
                break
            }
        }
        if !updated {
            lines = append(lines, fmt.Sprintf("SCAN_PATHS=%s", path))
        }
        os.WriteFile(envPath, []byte(strings.Join(lines, "\n")), 0644)
    } else {
        os.WriteFile(envPath, []byte(fmt.Sprintf("SCAN_PATHS=%s\n", path)), 0644)
    }
}