#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${CONTEXT_VIEWER_HOST:-127.0.0.1}"
PORT="${CONTEXT_VIEWER_PORT:-37677}"

echo "Starting Context Mesh Viewer on ${HOST}:${PORT}"
exec python3 "$SCRIPT_DIR/memory_viewer.py"
