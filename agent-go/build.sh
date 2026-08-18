#!/usr/bin/env bash
# Cross-compiles the DPDP agent for every distributable platform.
#
# Optional build-time configuration (baked into the binary via ldflags, so the
# shipped agent works even without a .env file):
#   SERVER_URL=https://api.example.com API_KEY=token ORG_ID=org123 ./build.sh
#
# Output: dist/dpdp-agent-<os>-<arch>[.exe]
set -euo pipefail
 
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"
 
DIST_DIR="${DIST_DIR:-dist}"
VERSION="${VERSION:-dev}"
CONFIG_PKG="dpdp-toolkit/agent-go/internal/config"
 
LDFLAGS="-s -w"
LDFLAGS="$LDFLAGS -X ${CONFIG_PKG}.BuiltServerURL=${SERVER_URL:-}"
LDFLAGS="$LDFLAGS -X ${CONFIG_PKG}.BuiltAPIKey=${API_KEY:-}"
LDFLAGS="$LDFLAGS -X ${CONFIG_PKG}.BuiltOrgID=${ORG_ID:-}"
 
PLATFORMS=(
  "windows/amd64"
  "darwin/amd64"
  "darwin/arm64"
)
if [ "$#" -gt 0 ]; then
  PLATFORMS=("$@")
fi
 
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"
 
for platform in "${PLATFORMS[@]}"; do
  goos="${platform%%/*}"
  goarch="${platform##*/}"
 
  outdir="$DIST_DIR/${goos}-${goarch}"
  mkdir -p "$outdir"
  output="$outdir/dpdp-agent"
  if [ "$goos" = "windows" ]; then
    output="${output}.exe"
  fi
 
  echo "building $goos/$goarch -> $output"
  GOOS="$goos" GOARCH="$goarch" CGO_ENABLED=0 \
    go build -trimpath -ldflags "$LDFLAGS" -o "$output" ./cmd/agent
done
 
cp install.ps1 install.command "$DIST_DIR/"
chmod +x "$DIST_DIR/install.command"
 
echo "version: $VERSION"
ls -1 "$DIST_DIR"