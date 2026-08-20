# Backend image for Render. It ships the Go toolchain and the agent-go sources so
# the installer endpoint can compile a per-organisation agent on each download,
# with SERVER_URL/API_KEY/ORG_ID baked in via ldflags.
FROM python:3.10-slim
 
COPY --from=golang:1.24-bookworm /usr/local/go /usr/local/go
 
ENV PATH="/usr/local/go/bin:${PATH}" \
    GOCACHE=/tmp/gocache \
    GOMODCACHE=/go/pkg/mod \
    PYTHONUNBUFFERED=1 \
    AGENT_SOURCE_PATH=/app/agent-go \
    AGENT_BUILD_ON_DOWNLOAD=1
 
WORKDIR /app
 
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && python -m spacy download en_core_web_sm
 
COPY agent-go agent-go
# Warm the module cache and produce fallback binaries, so the first download
# does not pay for dependency fetching and works even if builds are disabled.
RUN cd agent-go \
    && go mod download \
    && mkdir -p dist/windows-amd64 dist/darwin-amd64 dist/darwin-arm64 \
    && CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o dist/windows-amd64/dpdp-agent.exe ./cmd/agent \
    && CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o dist/darwin-amd64/dpdp-agent ./cmd/agent \
    && CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -ldflags "-s -w" -o dist/darwin-arm64/dpdp-agent ./cmd/agent \
    && chmod -R a+rwX "$GOMODCACHE"
 
COPY backend backend
 
# main.py imports absolute `backend.*` packages, so run from the repo root.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]