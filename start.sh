#!/bin/sh
# Intelligent Lighting System - starts everything. All options go to start.py:
#   ./start.sh --check      ./start.sh --dry-run      ./start.sh --no-ui
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/backend/venv/bin/python"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3 || command -v python)"
fi
if [ -z "$PY" ]; then
    echo "No Python found. Install Python 3.11 or 3.12, then see README: Start everything." >&2
    exit 1
fi
exec "$PY" "$ROOT/start.py" "$@"
