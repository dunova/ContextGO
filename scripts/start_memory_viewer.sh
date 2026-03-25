#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${CONTEXT_VIEWER_HOST:-127.0.0.1}"
PORT="${CONTEXT_VIEWER_PORT:-37677}"
TOKEN="${CONTEXT_VIEWER_TOKEN:-}"

echo "Launching Context Mesh Viewer via context_cli serve on ${HOST}:${PORT}"
CMD=(python3 "$SCRIPT_DIR/context_cli.py" serve --host "$HOST" --port "$PORT")
if [ -n "$TOKEN" ]; then
  CMD+=("--token" "$TOKEN")
fi
exec "${CMD[@]}"
