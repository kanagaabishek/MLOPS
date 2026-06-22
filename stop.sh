#!/usr/bin/env bash
#
# stop.sh — stop FrameLock.
#   By default stops the app processes (API, Celery worker, Celery Beat) and
#   leaves the Qdrant + Redis containers running (their data persists).
#   Pass --all to also stop the containers.
#
# Usage:  ./stop.sh          # stop app processes only
#         ./stop.sh --all    # also stop Qdrant + Redis containers
#
set -uo pipefail
cd "$(dirname "$0")"

echo "▸ stopping app processes…"
pkill -f "uvicorn framelock.app"     2>/dev/null && echo "  ✓ API stopped"          || echo "  · API not running"
pkill -f "celery -A framelock.tasks" 2>/dev/null && echo "  ✓ worker/Beat stopped"  || echo "  · worker/Beat not running"

if [ "${1:-}" = "--all" ]; then
  echo "▸ stopping containers…"
  if docker stop framelock-qdrant framelock-redis >/dev/null 2>&1; then
    echo "  ✓ containers stopped (data persists; 'docker rm framelock-qdrant framelock-redis' to remove)"
  else
    echo "  · containers were not running"
  fi
else
  echo "▸ containers left running — use './stop.sh --all' to stop them too"
fi
