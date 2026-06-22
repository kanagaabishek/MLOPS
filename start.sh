#!/usr/bin/env bash
#
# start.sh — bring up the full FrameLock stack locally.
#   Infra (Qdrant + Redis) runs in Docker; the app processes (API, Celery worker,
#   Celery Beat) run from the local .venv. Logs go to ./logs/. Ctrl-C stops the
#   app processes; the containers keep running (stop them with the line printed
#   at the end).
#
# Usage:  ./start.sh           # default API port 8077
#         PORT=9000 ./start.sh
#
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
PY="$VENV/bin/python"
PORT="${PORT:-8077}"

export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
export CELERY_BROKER="${CELERY_BROKER:-redis://localhost:6379/0}"
export CELERY_BACKEND="${CELERY_BACKEND:-redis://localhost:6379/1}"
export PYTHONWARNINGS=ignore
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES   # macOS fork-safety for torch/Celery

# ── prerequisites ────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || { echo "✗ Docker is required (start Docker Desktop)"; exit 1; }
docker info  >/dev/null 2>&1      || { echo "✗ Docker daemon not running — start Docker Desktop"; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || echo "⚠ ffmpeg not found — install it: brew install ffmpeg"
[ -x "$PY" ] || { echo "✗ No .venv found. Create it first:"; echo "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }

# ── infra: Qdrant + Redis (create if missing, start if stopped) ───────────────
ensure_container() {
  local name="$1" image="$2"; shift 2
  if [ -n "$(docker ps -q -f name="^${name}$")" ]; then
    echo "✓ $name already running"
  elif [ -n "$(docker ps -aq -f name="^${name}$")" ]; then
    echo "▸ starting existing $name…"; docker start "$name" >/dev/null
  else
    echo "▸ creating $name…"; docker run -d --name "$name" "$@" "$image" >/dev/null
  fi
}
ensure_container framelock-qdrant qdrant/qdrant -p 6333:6333 -p 6334:6334
ensure_container framelock-redis  redis         -p 6379:6379

printf "▸ waiting for Qdrant"
until curl -sf http://localhost:6333/healthz >/dev/null 2>&1; do printf "."; sleep 1; done
echo " ✓"

# ── app processes ─────────────────────────────────────────────────────────────
mkdir -p logs
echo "▸ starting API, worker, and Beat…"
"$VENV/bin/uvicorn" framelock.app:app --host 127.0.0.1 --port "$PORT" --log-level warning > logs/api.log 2>&1 &
API_PID=$!
"$VENV/bin/celery" -A framelock.tasks worker --pool=solo --loglevel=info > logs/worker.log 2>&1 &
WORKER_PID=$!
"$VENV/bin/celery" -A framelock.tasks beat --loglevel=info > logs/beat.log 2>&1 &
BEAT_PID=$!

cleanup() { echo; echo "▸ stopping app processes…"; kill "$API_PID" "$WORKER_PID" "$BEAT_PID" 2>/dev/null || true; }
trap cleanup INT TERM

cat <<EOF

  ┌─────────────────────────────────────────────┐
  │  FrameLock is up                            │
  │  UI / API : http://127.0.0.1:$PORT
  │  API docs : http://127.0.0.1:$PORT/docs
  │  logs     : ./logs/{api,worker,beat}.log     │
  └─────────────────────────────────────────────┘

  Ctrl-C stops the app processes. The containers keep running; stop them with:
    docker stop framelock-qdrant framelock-redis

EOF

wait
