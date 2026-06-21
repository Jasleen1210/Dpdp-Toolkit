//go:build windows

package gui

import (
    "os"
    "os/exec"
    "path/filepath"
    "strings"
)

func promptFolderSelection(currentPaths []string, writeEnv bool) string {
    if len(currentPaths) > 1 || (len(currentPaths) == 1 && !isDefaultPath(currentPaths[0])) {
        return ""
    }
    if os.Getenv("OS") == "Windows_NT" || os.Getenv("SYSTEMROOT") != "" {
        return showFolderPickerGUI(writeEnv)
    }
    return ""
}

func showFolderPickerGUI(writeEnv bool) string {
    scriptPath := filepath.Join(os.TempDir(), "dpdp-folder-picker.ps1")
    defer os.Remove(scriptPath)

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

    cmd := exec.Command("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath)
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