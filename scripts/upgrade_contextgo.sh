#!/usr/bin/env bash
set -euo pipefail

log() { printf '[upgrade] %s\n' "$*"; }

if ! command -v pipx >/dev/null 2>&1; then
  log "pipx is required. Install it first: brew install pipx"
  exit 1
fi

pipx ensurepath >/dev/null 2>&1 || true

if [ -f "pyproject.toml" ] && grep -q 'name = "contextgo"' pyproject.toml 2>/dev/null; then
  log "upgrading ContextGO from the current repository checkout"
  pipx install --force '.[vector]'
else
  log "upgrading installed ContextGO from pipx"
  pipx upgrade contextgo || pipx install "contextgo[vector]"
fi

if command -v contextgo >/dev/null 2>&1; then
  log "verifying upgraded runtime"
  contextgo health
  contextgo sources
else
  log 'ContextGO upgraded, but your current shell may need PATH refresh.'
  log 'Run: eval "$(contextgo shell-init)"'
fi
