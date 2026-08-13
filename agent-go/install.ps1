$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
 
function Find-AgentBinary {
  foreach ($candidate in @('dpdp-agent-windows-amd64.exe', 'dpdp-agent.exe')) {
    $path = Join-Path $scriptRoot $candidate
    if (Test-Path $path) { return $path }
  }
  return $null
}
 
$sourceBinary = Find-AgentBinary
if (-not $sourceBinary) {
  Write-Error 'dpdp-agent-windows-amd64.exe (or dpdp-agent.exe) not found in this folder. Download it next to this script and re-run.'
  exit 1
}

# Installed binary lives next to its .env in a stable per-user location.
$installDir = if ($env:DPDP_INSTALL_DIR) { $env:DPDP_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'DPDPAgent' }
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
$agentExe = Join-Path $installDir 'dpdp-agent.exe'
Copy-Item -Path $sourceBinary -Destination $agentExe -Force
Unblock-File -Path $agentExe -ErrorAction SilentlyContinue
 
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
  "SCAN_INTERVAL=24h"
  "SCAN_PATHS=$scanPathsValue"
  "INCLUDE_EXTENSIONS=*"
  "MAX_FILE_SIZE_MB=5"
  "REGISTER_PATH=/devices/register"
  "TASKS_PATH=/devices/tasks"
  "RESULTS_PATH=/results"
)
Set-Content -Path (Join-Path $installDir '.env') -Value ($envLines -join "`n") -Encoding ASCII
Write-Host "Installed to: $installDir"
Write-Host "Saved scan paths: $scanPathsValue"
function Test-IsAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  return (New-Object Security.Principal.WindowsPrincipal $identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
}
 
function Register-ScheduledTaskFallback {
  # No admin rights: run at logon via Task Scheduler and restart on failure.
  Write-Host 'Registering the agent as a scheduled task (runs at logon)...'
  $taskName = 'DPDPAgent'
  schtasks /Delete /TN $taskName /F 2>$null | Out-Null
 
  $action = New-ScheduledTaskAction -Execute $agentExe -Argument 'run' -WorkingDirectory $installDir
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName $taskName
  Write-Host 'Scheduled task "DPDPAgent" registered and started.'
}
 
# Registers a real Windows Service (auto-start, restart on failure) when we have
# admin rights; otherwise falls back to a per-user scheduled task at logon.
& $agentExe uninstall 2>$null | Out-Null
$serviceInstalled = $false
if (Test-IsAdministrator) {
  Write-Host 'Registering the agent as a Windows Service...'
  & $agentExe install
  if ($LASTEXITCODE -eq 0) {
    $serviceInstalled = $true
    sc.exe failure dpdp-agent reset= 86400 actions= restart/10000/restart/30000/restart/60000 | Out-Null
    Write-Host 'Windows Service "dpdp-agent" installed and started.'
  } else {
    Write-Warning 'Service installation failed; falling back to a scheduled task.'
  }
} else {
  Write-Host 'Not running as Administrator.'
}
 
if (-not $serviceInstalled) {
  Register-ScheduledTaskFallback
}
 
Write-Host ''
Write-Host 'The DPDP agent now runs in the background and starts automatically after reboot.'
Write-Host "Manage it with: `"$agentExe`" status | stop | start | uninstall"
Write-Host 'If SmartScreen blocked the download, right-click the .exe > Properties > Unblock, then re-run this script.'