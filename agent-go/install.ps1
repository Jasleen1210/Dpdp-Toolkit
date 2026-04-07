$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path (Join-Path $scriptRoot 'dpdp-agent.exe'))) {
  Write-Error 'dpdp-agent.exe not found in current folder.'
  exit 1
}

Add-Type -AssemblyName System.Windows.Forms

$defaultScanPath = Join-Path $env:USERPROFILE 'Documents'
$folderBrowser = New-Object System.Windows.Forms.FolderBrowserDialog
$folderBrowser.Description = "Select folders to scan for sensitive data"
$folderBrowser.SelectedPath = $defaultScanPath
$folderBrowser.ShowNewFolderButton = $false

$result = $folderBrowser.ShowDialog()

if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
  $scanPaths = @($folderBrowser.SelectedPath)
} else {
  $scanPaths = @($defaultScanPath)
}

$scanPathsValue = [string]::Join(',', $scanPaths)
$envLines = @(
  "SERVER_URL=$env:SERVER_URL"
  "API_KEY=$env:API_KEY"
  "ORG_ID=$env:ORG_ID"
  "POLL_INTERVAL=30s"
  "SCAN_PATHS=$scanPathsValue"
  "INCLUDE_EXTENSIONS=*"
  "MAX_FILE_SIZE_MB=5"
  "REGISTER_PATH=/devices/register"
  "TASKS_PATH=/devices/tasks"
  "RESULTS_PATH=/results"
)
Set-Content -Path (Join-Path $scriptRoot '.env') -Value ($envLines -join "`n") -Encoding ASCII
Write-Host "Saved scan paths: $scanPathsValue"
Write-Host 'Launching DPDP agent for configured organisation...'
& (Join-Path $scriptRoot 'dpdp-agent.exe')
