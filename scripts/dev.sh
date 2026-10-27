#!/usr/bin/env sh
# Start the backend (http://127.0.0.1:8000) and the Vite dev server (http://127.0.0.1:5173) together.
# Ctrl+C stops both.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY="$ROOT/.venv/Scripts/python"; fi
[ -x "$PY" ] || { echo "No .venv found. Run scripts/setup.sh first."; exit 1; }
[ -d "$ROOT/frontend/node_modules" ] || { echo "No frontend/node_modules. Run scripts/setup.sh first."; exit 1; }

cd "$ROOT/backend"
"$PY" -m uvicorn qcanvas.api.app:app --host 127.0.0.1 --port 8000 &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null || true' EXIT INT TERM

echo "Backend on http://127.0.0.1:8000 (provider: ${QCANVAS_MODEL_PROVIDER:-from .env or mock})"
cd "$ROOT/frontend"
npm run dev -- --host 127.0.0.1
