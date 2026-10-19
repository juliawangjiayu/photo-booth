#!/bin/bash
# Double-click in macOS Finder, or run: ./start.command
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it from python.org or Homebrew."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js and npm are required: https://nodejs.org"
  exit 1
fi
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install -r apps/studio/backend/requirements.txt
if [ ! -d "apps/studio/frontend/node_modules" ]; then
  (cd apps/studio/frontend && npm install)
fi
python -m uvicorn backend.main:app --app-dir apps/studio --host 127.0.0.1 --port 8000 &
BACK_PID=$!
cleanup() { kill "$BACK_PID" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
(cd apps/studio/frontend && npm run dev)
