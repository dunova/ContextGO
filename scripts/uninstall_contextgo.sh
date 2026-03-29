#!/usr/bin/env bash
set -euo pipefail

PURGE_DATA=0
if [ "${1:-}" = "--purge-data" ]; then
  PURGE_DATA=1
fi

HOME_DIR="${HOME:-$(cd ~ && pwd)}"
INSTALL_ROOT="${CONTEXTGO_INSTALL_ROOT:-$HOME_DIR/.local/share/contextgo}"
BIN_PATH="${CONTEXTGO_BIN_DIR:-$HOME_DIR/.local/bin}/contextgo"
STORAGE_ROOT="${CONTEXTGO_STORAGE_ROOT:-$HOME_DIR/.contextgo}"
LAUNCH_AGENTS_DIR="$HOME_DIR/Library/LaunchAgents"

log() { printf '[uninstall] %s\n' "$*"; }

if command -v launchctl >/dev/null 2>&1; then
  for label in com.contextgo.daemon com.contextgo.healthcheck; do
    launchctl bootout "gui/$(id -u)" "$LAUNCH_AGENTS_DIR/$label.plist" >/dev/null 2>&1 || true
  done
fi

for plist in com.contextgo.daemon.plist com.contextgo.healthcheck.plist; do
  if [ -f "$LAUNCH_AGENTS_DIR/$plist" ]; then
    rm -f "$LAUNCH_AGENTS_DIR/$plist"
    log "removed $LAUNCH_AGENTS_DIR/$plist"
  fi
done

if command -v pipx >/dev/null 2>&1; then
  pipx uninstall contextgo >/dev/null 2>&1 || true
fi

if [ -e "$BIN_PATH" ]; then
  rm -f "$BIN_PATH"
  log "removed $BIN_PATH"
fi

if [ -d "$INSTALL_ROOT" ]; then
  rm -rf "$INSTALL_ROOT"
  log "removed $INSTALL_ROOT"
fi

if [ "$PURGE_DATA" = "1" ] && [ -d "$STORAGE_ROOT" ]; then
  rm -rf "$STORAGE_ROOT"
  log "removed $STORAGE_ROOT"
elif [ -d "$STORAGE_ROOT" ]; then
  log "kept data at $STORAGE_ROOT"
  log "rerun with --purge-data to remove all indexed history and memories"
fi

log "ContextGO uninstall complete"
