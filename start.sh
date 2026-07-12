#!/bin/bash
# RHEINGOLD Space entrypoint: FastAPI (internal :8000) + Next standalone (:7860).
set -euo pipefail

export RHEINGOLD_MART="${RHEINGOLD_MART:-/app/data/mart/rheingold.duckdb}"
# The Space sets ALLOWED_ORIGIN (e.g. https://sidnov6-rheingold.hf.space).
# Same-origin proxying via Next rewrites means CORS rarely triggers, but the
# API restricts cross-origin callers to this origin either way.
export ALLOWED_ORIGIN="${ALLOWED_ORIGIN:-http://localhost:7860}"

/app/.venv/bin/python -m uvicorn main:app \
  --app-dir /app/apps/api --host 127.0.0.1 --port 8000 &
API_PID=$!

PORT="${PORT:-7860}" HOSTNAME=0.0.0.0 node /app/apps/web/server.js &
WEB_PID=$!

cleanup() {
  trap - INT TERM EXIT
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  wait "$API_PID" "$WEB_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Exit (→ container restart) as soon as either process dies.
wait -n "$API_PID" "$WEB_PID"
