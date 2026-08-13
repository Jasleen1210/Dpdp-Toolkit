#!/usr/bin/env bash
# macOS installer for the DPDP agent.
# Double-click this file in Finder (or run it from Terminal) after downloading
# the dpdp-agent binary for your Mac into the same folder.
set -euo pipefail
 
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"
 
find_binary() {
  if [ -n "${DPDP_AGENT_BINARY:-}" ] && [ -f "$DPDP_AGENT_BINARY" ]; then
    echo "$DPDP_AGENT_BINARY"
    return 0
  fi
 
  local arch
  arch="$(uname -m)"
  local preferred="dpdp-agent-darwin-amd64"
  if [ "$arch" = "arm64" ]; then
    preferred="dpdp-agent-darwin-arm64"
  fi
 
  for candidate in "$preferred" "dpdp-agent-darwin-arm64" "dpdp-agent-darwin-amd64" "dpdp-agent"; do
    if [ -f "$script_dir/$candidate" ]; then
      echo "$script_dir/$candidate"
      return 0
    fi
  done
  return 1
}
 
if ! binary="$(find_binary)"; then
  echo "Error: no dpdp-agent binary found in $script_dir."
  echo "Download dpdp-agent-darwin-arm64 (Apple Silicon) or dpdp-agent-darwin-amd64 (Intel) into this folder and re-run."
  exit 1
fi
 
# Installed binary lives next to its .env in a stable location.
install_dir="${DPDP_INSTALL_DIR:-$HOME/Library/Application Support/DPDPAgent}"
mkdir -p "$install_dir"
cp -f "$binary" "$install_dir/dpdp-agent"
chmod +x "$install_dir/dpdp-agent"
 
# macOS Gatekeeper flags downloaded, unsigned binaries; clear the quarantine bit.
xattr -d com.apple.quarantine "$install_dir/dpdp-agent" 2>/dev/null || true
 
# Apple Silicon refuses to exec a binary without a signature (SIGKILL at launch),
# and cross-compiled binaries ship unsigned, so ad-hoc sign it locally.
codesign --force --sign - "$install_dir/dpdp-agent" 2>/dev/null || true
 
default_scan_path="$HOME/Documents"
selected_path="$(osascript <<'APPLESCRIPT' 2>/dev/null || true
try
  set chosenFolder to choose folder with prompt "Select the folder to scan for sensitive data"
  POSIX path of chosenFolder
on error
  return ""
end try
APPLESCRIPT
)"
selected_path="${selected_path%/}"
 
if [ -z "$selected_path" ]; then
  read -r -p "Folder to scan [$default_scan_path]: " selected_path || true
  selected_path="${selected_path:-$default_scan_path}"
fi
 
env_file="$install_dir/.env"
cat > "$env_file" <<EOF
SERVER_URL=${SERVER_URL:-}
API_KEY=${API_KEY:-}
ORG_ID=${ORG_ID:-}
POLL_INTERVAL=30s
SCAN_INTERVAL=24h
SCAN_PATHS=$selected_path
INCLUDE_EXTENSIONS=*
MAX_FILE_SIZE_MB=5
REGISTER_PATH=/devices/register
TASKS_PATH=/devices/tasks
RESULTS_PATH=/results
EOF
chmod 600 "$env_file"
 
echo "Installed to: $install_dir"
echo "Saved scan path: $selected_path"
 
# Registers a LaunchAgent (~/Library/LaunchAgents/dpdp-agent.plist) with
# RunAtLoad + KeepAlive, so the agent survives logout and reboot.
"$install_dir/dpdp-agent" uninstall >/dev/null 2>&1 || true
"$install_dir/dpdp-agent" install
 
echo
echo "DPDP agent is now running in the background and will start automatically at login."
echo "Manage it with:"
echo "  \"$install_dir/dpdp-agent\" status"
echo "  \"$install_dir/dpdp-agent\" stop"
echo "  \"$install_dir/dpdp-agent\" uninstall"
echo
echo "If macOS blocked the app ('cannot be opened because the developer cannot be verified'),"
echo "open System Settings > Privacy & Security and click 'Open Anyway', then re-run this installer."