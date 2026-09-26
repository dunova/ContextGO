#!/usr/bin/env bash
# sync_linux_node.sh -- Export ContextGO memory pack and deploy/sync to remote Linux host.
#
# Usage:
#   sync_linux_node.sh user@host [--port 22] [--full-deploy]
#
# Exit codes:
#   0  Sync / deploy succeeded.
#   1  Invalid arguments or remote execution failed.

set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") <user@remote-host> [options]

Synchronize ContextGO memories and optionally deploy runtime to a remote Linux host.

Arguments:
  user@remote-host     SSH destination (e.g. ubuntu@192.168.1.100 or deploy@vps)

Options:
  --port <port>        SSH port (default: 22)
  --full-deploy        Sync runtime code and invoke unified_context_deploy.sh remotely
  --pack-only          Only export and import memory pack (default)
  -h, --help           Show this help message

Examples:
  $(basename "$0") ubuntu@node-1.internal
  $(basename "$0") root@vps.example.com --port 2222 --full-deploy
EOF
    exit 0
}

TARGET=""
SSH_PORT="22"
FULL_DEPLOY=0

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            ;;
        --port)
            SSH_PORT="$2"
            shift 2
            ;;
        --full-deploy)
            FULL_DEPLOY=1
            shift
            ;;
        --pack-only)
            FULL_DEPLOY=0
            shift
            ;;
        -*)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
        *)
            if [ -z "$TARGET" ]; then
                TARGET="$1"
                shift
            else
                echo "Unexpected argument: $1" >&2
                exit 1
            fi
            ;;
    esac
done

if [ -z "$TARGET" ]; then
    echo "ERROR: Destination user@remote-host is required." >&2
    usage
fi

log() { printf '[sync-node] %s\n' "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 1. Ensure local CLI is available
CLI_BIN="$(command -v contextgo 2>/dev/null || echo "$HOME/.local/bin/contextgo")"
if [ ! -x "$CLI_BIN" ]; then
    if [ -f "$REPO_ROOT/src/contextgo/context_cli.py" ]; then
        CLI_BIN="python3 $REPO_ROOT/src/contextgo/context_cli.py"
    else
        log "ERROR: contextgo CLI not found locally." >&2
        exit 1
    fi
fi

# 2. Export local memory package
TMP_PACK="$(mktemp -t contextgo_pack_XXXXXX.json)"
trap 'rm -f "$TMP_PACK"' EXIT

log "exporting local memory package..."
$CLI_BIN memory-pack export --out "$TMP_PACK"

# 3. Full deployment if requested
if [ "$FULL_DEPLOY" = "1" ]; then
    log "deploying ContextGO runtime to $TARGET via rsync..."
    rsync -avz -e "ssh -p $SSH_PORT" \
        --exclude '.git' \
        --exclude '.venv' \
        --exclude '__pycache__' \
        --exclude '.pytest_cache' \
        --exclude '.ruff_cache' \
        --exclude '.mypy_cache' \
        "$REPO_ROOT/" "$TARGET:~/.local/share/contextgo-src/"

    log "running remote unified_context_deploy.sh on $TARGET..."
    ssh -p "$SSH_PORT" "$TARGET" "bash ~/.local/share/contextgo-src/scripts/unified_context_deploy.sh"
fi

# 4. Transfer and import memory pack on remote node
REMOTE_PACK="/tmp/contextgo_sync_pack_$$.json"
log "transferring memory package to remote node..."
scp -P "$SSH_PORT" "$TMP_PACK" "$TARGET:$REMOTE_PACK"

log "importing memory package into remote node ContextGO..."
ssh -p "$SSH_PORT" "$TARGET" "bash -l -c 'contextgo memory-pack import $REMOTE_PACK && rm -f $REMOTE_PACK && contextgo health'"

log "remote node $TARGET synchronization completed successfully!"
