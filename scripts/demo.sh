#!/usr/bin/env sh
# Run the agent on the Bell sketch with a fault injected into attempt 1,
# so the live log shows a failure, a diagnosis, a repair and a pass.
set -e
cd "$(dirname "$0")/../backend"
if [ -x ../.venv/bin/python ]; then PY=../.venv/bin/python; else PY=../.venv/Scripts/python; fi
SPEC="${1:-../examples/specs/bell.json}"
FAULT="${QCANVAS_DEMO_FAULT:-auto}"
exec "$PY" -m qcanvas.cli "$SPEC" --fault "$FAULT" --noise "${QCANVAS_NOISE:-realistic}" --pace "${QCANVAS_PACE:-0.4}"
