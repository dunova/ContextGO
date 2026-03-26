# CLAUDE.md — Project Instructions for Claude Code

## Project

ContextGO — local-first context and memory runtime for AI coding teams.
Entry point: `python3 scripts/context_cli.py` (or `contextgo` if pip-installed)

## Architecture

- `scripts/` — Python core: CLI, daemon, indexer, viewer, search, smoke, maintenance
  - `context_cli.py` — single operator entry point for all commands
  - `context_config.py` — env var resolution and storage root
  - `session_index.py` — SQLite FTS5-backed session index and retrieval
  - `memory_index.py` — memory and observation index, export/import
  - `context_daemon.py` — session capture and sanitization
  - `context_server.py` — local viewer API server
  - `context_core.py` — shared helpers: file scan, memory write, safe_mtime
  - `context_native.py` — Rust/Go backend orchestration
  - `context_smoke.py` — smoke test suite
  - `context_maintenance.py` — index cleanup and repair
- `native/session_scan/` — Rust hot-path binary for file scanning
- `native/session_scan_go/` — Go hot-path binary for parallel scanning
- `docs/` — full documentation suite (ARCHITECTURE, CONFIGURATION, TROUBLESHOOTING, API, CONTRIBUTING)
- `benchmarks/` — Python vs. native-wrapper performance harness
- `templates/` — systemd/launchd service templates
- `artifacts/` — autoresearch outputs (do not edit)
- `patches/` — compatibility notes (do not edit)

## Test Commands

```bash
# Syntax checks
bash -n scripts/*.sh
python3 -m py_compile scripts/*.py

# Unit and integration tests
python3 -m pytest scripts/test_context_cli.py scripts/test_context_core.py scripts/test_session_index.py scripts/test_context_native.py scripts/test_context_smoke.py scripts/test_autoresearch_contextgo.py

# End-to-end quality gate
python3 scripts/e2e_quality_gate.py

# Smoke tests (sandboxed — does not write to ~/.contextgo)
python3 scripts/context_cli.py smoke --sandbox
python3 scripts/smoke_installed_runtime.py

# Health check
bash scripts/context_healthcheck.sh
```

## Style Rules

- **Python:** ruff-compatible, type hints required on all new functions and public interfaces, English docstrings, target Python 3.10+
- **Rust:** `cargo clippy` clean before commit
- **Go:** `go vet` clean before commit
- **Shell:** `shellcheck` clean, always start with `#!/usr/bin/env bash` and `set -euo pipefail`

## Important

- All user-facing text: bilingual (English primary, Chinese secondary)
- Never commit to `artifacts/` or `patches/` without an explicit request
- Run the full test suite before any commit
- No hardcoded absolute paths in committed code — use `~` or environment variables
- No secrets, tokens, or API keys in any committed file
- Default storage root is `~/.contextgo`; override with `CONTEXTGO_STORAGE_ROOT`
- Remote sync is disabled by default; enabled only via `CONTEXTGO_ENABLE_REMOTE_MEMORY_HTTP=true`

## Context Awareness (auto-triggered behaviors)

You have access to ContextGO, a local session memory index. Use it proactively
as part of your natural workflow — do not wait for the user to ask.

### When to search automatically

- **Session start / new topic**: If the user's first message references ongoing work,
  a project name, or a continuation ("continue", "pick up", "where were we"),
  run `contextgo semantic "<topic>" --limit 3` before responding. Use the results
  to orient yourself silently — summarize briefly, do not dump raw output.

- **Uncertainty**: If you are unsure about a project's history, past decisions,
  or why something was done a certain way, search before guessing:
  `contextgo search "<keyword>" --limit 5`

- **User asks about the past**: "What did I do with X", "recall", "search memory",
  "find that thing", "what happened with Y" — these are direct recall requests.
  Run `contextgo semantic "<query>"` or `contextgo search "<query>"` and
  summarize the findings conversationally.

- **Before making architectural decisions**: Search for prior decisions on the
  same topic to avoid contradicting past choices:
  `contextgo search "<topic>" --limit 3`

### When to save automatically

- **Hard problem solved**: After finding a non-obvious root cause or fix,
  suggest saving: `contextgo save --title "..." --content "..." --tags "..."`

- **Architectural decision made**: When the user chooses approach A over B,
  save the rationale so future sessions know why.

- **Session wrap-up**: If the user says "done", "wrap up", "that's it for today",
  and significant work was done, save a handoff note.

### How to search

```bash
# Broad recall (checks saved memories first, then session history)
contextgo semantic "natural language question" --limit 3

# Keyword search (direct FTS5 against session index)
contextgo search "specific keyword" --limit 5

# Exact phrase match
contextgo search "exact error message" --limit 5 --literal
```

### How to save

```bash
contextgo save \
  --title "Brief: what was decided or learned" \
  --content "Details: rationale, file paths, gotchas, next steps" \
  --tags "project,topic,type"
```

### Rules

- Never paste raw search output to the user. Summarize in 2-3 sentences.
- Search silently when orienting yourself. Only mention it if results are relevant.
- If search returns nothing, do not mention the search — just proceed normally.
- Save only durable knowledge (decisions, root causes, warnings), not routine edits.
