package gui

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
)

// PromptFolderSelectionWindows shows a native Windows folder picker dialog if SCAN_PATHS is not configured.
// Returns the selected paths (comma-separated) or an empty string if cancelled/cancelled.
// On success, it also writes the selected paths to a .env file.
func PromptFolderSelectionWindows(currentPaths []string, writeEnv bool) string {
	// If already configured via .env or env var, skip prompt
	if len(currentPaths) > 1 || (len(currentPaths) == 1 && !isDefaultPath(currentPaths[0])) {
		return ""
	}

	// On Windows, show a GUI folder picker
	if os.Getenv("OS") == "Windows_NT" || os.Getenv("SYSTEMROOT") != "" {
		return showFolderPickerGUI(writeEnv)
	}

	return ""
}

func isDefaultPath(p string) bool {
	// Check if it's a default drive root (C:\, D:\, etc. on Windows) or / on Unix
	if strings.HasSuffix(p, "\\") && len(p) == 3 {
		return true // e.g., C:\
	}
	return p == "/"
}

func showFolderPickerGUI(writeEnv bool) string {
	// Use PowerShell to show a Windows Forms folder picker dialog
	scriptPath := filepath.Join(os.TempDir(), "dpdp-folder-picker.ps1")
	defer os.Remove(scriptPath)

	// PowerShell script that shows a folder picker and outputs the selected directory
	psScript := `
[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
$folderBrowser = New-Object System.Windows.Forms.FolderBrowserDialog
$folderBrowser.Description = "Select folder(s) to scan for data"
$folderBrowser.ShowNewFolderButton = $true
$folderBrowser.RootFolder = [System.Environment+SpecialFolder]::MyComputer

if ($folderBrowser.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Host "SELECTED:$($folderBrowser.SelectedPath)"
} else {
    Write-Host "CANCELLED"
}
`

	if err := os.WriteFile(scriptPath, []byte(psScript), 0644); err != nil {
		return ""
	}

	// Execute PowerShell script with hidden window
	cmd := exec.Command("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}

	output, err := cmd.Output()
	if err != nil {
		return ""
	}

	resultStr := strings.TrimSpace(string(output))
	if strings.HasPrefix(resultStr, "SELECTED:") {
		selectedPath := strings.TrimPrefix(resultStr, "SELECTED:")
		selectedPath = strings.TrimSpace(selectedPath)

		if writeEnv && selectedPath != "" {
			writePathToEnv(selectedPath)
		}

		return selectedPath
	}

	return ""
}

func writePathToEnv(path string) {
	envPath := ".env"
	if _, err := os.Stat(envPath); err == nil {
		// Read existing .env
		content, _ := os.ReadFile(envPath)
		contentStr := string(content)

		// Update or add SCAN_PATHS
		lines := strings.Split(contentStr, "\n")
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

		newContent := strings.Join(lines, "\n")
		os.WriteFile(envPath, []byte(newContent), 0644)
	} else {
		// Create new .env with SCAN_PATHS
		envContent := fmt.Sprintf("SCAN_PATHS=%s\n", path)
		os.WriteFile(envPath, []byte(envContent), 0644)
	}
}
