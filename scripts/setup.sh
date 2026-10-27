#!/usr/bin/env sh
# One-time setup: Python venv with pinned backend deps, and pinned frontend deps.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for c in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then PYTHON="$c"; break; fi
  done
  if [ -z "$PYTHON" ] && command -v py >/dev/null 2>&1; then PYTHON="py -3.13"; fi
fi
[ -n "$PYTHON" ] || { echo "Python 3.11+ is required (set PYTHON=...)."; exit 1; }
echo "Using $PYTHON"
$PYTHON -m venv .venv
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=.venv/Scripts/python; fi
"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
[ -f .env ] || cp .env.example .env
echo "Done. Start with: scripts/dev.sh   (or one port: cd backend && ../$PY -m uvicorn qcanvas.api.app:app)"
