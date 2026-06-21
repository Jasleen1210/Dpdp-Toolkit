package main

import (
	"fmt"
	"os"
	"strings"
	"time"

	"dpdp-toolkit/agent-go/internal/types"
)

func currentISTDate() string {
	return time.Now().In(istLocation).Format("2006-01-02")
}

func isUsingDefaultPaths(paths []string) bool {
	if len(paths) == 0 {
		return true
	}
	for _, p := range paths {
		if len(p) == 3 && p[1] == ':' && p[2] == '\\' {
			continue
		}
		if p == "/" {
			continue
		}
		return false
	}
	return true
}

func uniqueMatchFileCount(matches []types.Match) int {
	files := make(map[string]struct{}, len(matches))
	for _, match := range matches {
		if match.File == "" {
			continue
		}
		files[match.File] = struct{}{}
	}
	return len(files)
}

func modifyLocalFile(filePath, actionType, targetValue, newValue string) error {
	content, err := os.ReadFile(filePath)
	if err != nil {
		return err
	}
	fileStr := string(content)

	var modifiedStr string
	if actionType == "delete" {
		modifiedStr = strings.ReplaceAll(fileStr, targetValue, "[REDACTED]")
	} else {
		modifiedStr = strings.ReplaceAll(fileStr, targetValue, newValue)
	}

	if fileStr == modifiedStr {
		return nil
	}
	return os.WriteFile(filePath, []byte(modifiedStr), 0644)
}

func handleDiskModificationTask(task types.Task) error {
	parts := strings.Split(task.Query, "::")
	if len(parts) < 2 {
		return fmt.Errorf("invalid query string payload layout")
	}

	filePath := parts[0]
	targetValue := parts[1]

	content, err := os.ReadFile(filePath)
	if err != nil {
		return fmt.Errorf("failed to open local target file: %w", err)
	}
	fileStr := string(content)

	var modifiedStr string
	if task.Type == "delete" {
		modifiedStr = strings.ReplaceAll(fileStr, targetValue, "[REDACTED]")
	} else if task.Type == "update" {
		if len(parts) < 3 {
			return fmt.Errorf("update task missing the new replacement value parameter string")
		}
		modifiedStr = strings.ReplaceAll(fileStr, targetValue, parts[2])
	} else {
		return fmt.Errorf("unsupported task action type: %s", task.Type)
	}

	if fileStr == modifiedStr {
		return fmt.Errorf("target value to update/delete was not found inside the specified file contents")
	}
	return os.WriteFile(filePath, []byte(modifiedStr), 0644)
}