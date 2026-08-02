<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/media/logo-dark.svg">
    <img src="docs/media/logo.svg" alt="ContextGO" width="360">
  </picture>
</p>

<p align="center">
  <strong>Local-first context and memory runtime for AI coding agents.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/v/contextgo?color=2563eb&style=flat" alt="PyPI"></a>
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/pyversions/contextgo?color=3776ab&style=flat" alt="Python"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/verify.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/verify.yml/badge.svg" alt="Verify"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://github.com/dunova/ContextGO/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-6d28d9?style=flat" alt="License"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> | <a href="#what-it-indexes">Sources</a> | <a href="#privacy-first-github-sync">Encrypted Sync</a> | <a href="#operations">Operations</a> | <a href="README.zh.md">中文</a>
</p>

---

ContextGO gives AI coding agents durable local memory across tools, projects, and sessions. It indexes local histories from Codex, Claude Code, Gemini/Antigravity, OpenCode, OpenClaw, Accio, GitHub Copilot, Cursor/Windsurf-style stores, Kilo/Cline/Roo, Hermes, shell history, and other supported local sources into a searchable SQLite runtime. The default path is local-first: no Docker, no MCP broker, no remote database, and no cloud upload.

Version `0.13.0` is a cross-platform overhaul. It adds a shared Windows/macOS/Linux runtime layer, privacy-first encrypted GitHub synchronization, daemon service management, Windows AppData discovery, portable subprocess handling, stronger export redaction, CI runtime matrices, and release-grade coverage gates.

## Quick Start

Install with `pipx` so ContextGO is isolated from your system Python.

```bash
pipx install "contextgo[vector]"
eval "$(contextgo shell-init)"
contextgo health
contextgo sources
contextgo search "database migration" --limit 5
```

For encrypted GitHub synchronization, install the sync extra as well:

```bash
pipx install "contextgo[sync,vector]"
```

For local development from source:

```bash
git clone https://github.com/dunova/ContextGO.git
cd ContextGO
uv sync --extra dev --extra sync --extra vector
uv run python -m contextgo health
uv run pytest
```

## Platform Support

| Area | Windows | macOS | Linux |
|---|---:|---:|---:|
| CLI, health, search, export/import | Yes | Yes | Yes |
| SQLite indexes and WAL runtime | Yes | Yes | Yes |
| Encrypted GitHub sync | Yes | Yes | Yes |
| Daemon status/start/stop | Yes | Yes | Yes |
| User service definition | Task Scheduler | launchd | systemd user |
| Native app data discovery | `%APPDATA%`, `%LOCALAPPDATA%` | `~/Library/...` | XDG and home paths |
| Shell integration | Git Bash / POSIX shells | bash/zsh/fish | bash/zsh/fish |

ContextGO keeps historical `~/.contextgo` storage readable for upgrades. Set `CONTEXTGO_PLATFORM_STORAGE=1` only when you explicitly want OS-native platform directories such as `%LOCALAPPDATA%/ContextGO`, `~/Library/Application Support/ContextGO`, or `~/.local/share/contextgo`.

## What It Indexes

ContextGO discovers supported local sources automatically. No API key is required for local indexing.

| Source family | Examples |
|---|---|
| Coding agents | Codex, Claude Code, OpenCode, OpenClaw, Accio, GitHub Copilot, Gemini/Antigravity |
| Editors and IDEs | Cursor, Windsurf-style stores, Continue-style stores, Kilo, Cline, Roo, Zed |
| Local agent runtimes | Hermes, Factory/Droid, other JSONL session stores |
| Shell history | bash and zsh histories |
| Saved memories | `contextgo save`, portable exports, imported observation payloads |

Run this to see what is detected on your machine:

```bash
contextgo sources
```

## Core Commands

| Command | Purpose |
|---|---|
| `contextgo q "query"` | Quick recall. Routes to session ID lookup or search. |
| `contextgo search "query" --limit 10` | Full-text search over indexed sessions. |
| `contextgo semantic "query" --limit 5` | Memory-first search with session fallback. |
| `contextgo save --title "Decision" --content "..."` | Save durable local memory. |
| `contextgo export "" snapshot.json --limit 1000` | Export sanitized observations. |
| `contextgo import snapshot.json` | Import a portable observation snapshot. |
| `contextgo vector-sync` | Build or refresh optional vector embeddings. |
| `contextgo vector-status` | Show vector index state. |
| `contextgo health` | Verify runtime health as JSON. |
| `contextgo smoke --sandbox` | Run the local smoke gate without touching real storage. |
| `contextgo maintain --enqueue-missing` | Queue missing local sessions for indexing. |
| `contextgo serve` | Start the local viewer API on `127.0.0.1`. |

## Privacy-First GitHub Sync

Synchronization is disabled until you explicitly initialize it. ContextGO never silently uploads local history during installation or normal search.

```bash
contextgo sync init --repo OWNER/REPO --device-id work-laptop
contextgo sync status
contextgo sync run
```

On another machine:

```bash
pipx install "contextgo[sync,vector]"
contextgo sync init --repo OWNER/REPO --device-id home-desktop
contextgo sync pull
contextgo sync status --remote
```

The sync protocol is intentionally conservative.

| Rule | Behavior |
|---|---|
| Explicit opt-in | No remote read or write occurs before `sync init`. |
| End-to-end encryption | Payloads are compressed and encrypted with AES-256-GCM. |
| Password-derived key | The passphrase stays local and derives the key with scrypt. |
| Public manifest only | The remote manifest stores format metadata and KDF salt, not secrets. |
| Per-device shards | Each device writes its own encrypted shard to reduce write conflicts. |
| Redaction before upload | Tokens and absolute local paths are removed before encryption. |
| Fail-closed conflicts | A remote manifest salt mismatch stops the push instead of overwriting data. |
| Local-first daemon | Network failures back off and do not block local indexing or search. |

Disable automatic sync without deleting local data:

```bash
contextgo sync disable
```

## Daemon and Services

Use the daemon for background indexing and optional periodic encrypted sync.

```bash
contextgo daemon status
contextgo daemon start
contextgo daemon stop
```

Install or remove the per-user service definition:

```bash
contextgo daemon install
contextgo daemon uninstall
```

Service installation maps to Task Scheduler on Windows, launchd on macOS, and systemd user services on Linux. The command writes the service definition only for the current user and preserves all ContextGO data on uninstall.

## Hybrid Search

ContextGO works without vector dependencies. Installing the `vector` extra enables hybrid semantic search with model2vec embeddings, BM25 scoring, and Reciprocal Rank Fusion.

```bash
pipx inject contextgo "contextgo[vector]"
export CONTEXTGO_EXPERIMENTAL_SEARCH_BACKEND=vector
contextgo vector-sync
contextgo q "why did the auth migration change?"
```

When vector dependencies are missing, ContextGO falls back to SQLite FTS and literal matching. Tests also force fake vector models where needed, so CI does not download remote embedding models unexpectedly.

## Configuration

Most users do not need configuration. Environment variables are available for deployment and testing.

| Variable | Default | Purpose |
|---|---|---|
| `CONTEXTGO_STORAGE_ROOT` | `~/.contextgo` | Legacy-compatible root for indexes and logs. |
| `CONTEXTGO_PLATFORM_STORAGE` | unset | Set to `1` to use native OS data/config/cache directories. |
| `CONTEXTGO_HOME` | user home | Test and sandbox override for home directory resolution. |
| `CONTEXTGO_SESSION_INDEX_DB_PATH` | `$ROOT/index/session_index.db` | Session index database. |
| `MEMORY_INDEX_DB_PATH` | `$ROOT/index/memory_index.db` | Memory index database. |
| `CONTEXTGO_EXPERIMENTAL_SEARCH_BACKEND` | unset | Set to `vector` for hybrid search. |
| `CONTEXTGO_VIEWER_HOST` | `127.0.0.1` | Viewer bind host. |
| `CONTEXTGO_VIEWER_PORT` | `37677` | Viewer port. |
| `CONTEXTGO_GITHUB_TOKEN` / `GITHUB_TOKEN` | unset | Optional token override for sync; `gh auth token` is also supported. |

Full reference: [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## AI Agent Setup

ContextGO is designed to be called by agents before they answer questions about old work.

```bash
contextgo setup
contextgo health
contextgo semantic "what did we decide about sync encryption?" --limit 3
```

Recommended behavior for agents:

| Situation | Action |
|---|---|
| Continuing an old task | Run `contextgo semantic "topic" --limit 3`, then summarize briefly. |
| Unsure about project history | Run `contextgo search "keyword" --limit 5`. |
| Making an architecture decision | Search previous decisions before changing the design. |
| Solving a durable root cause | Suggest saving a short memory with `contextgo save`. |

The full agent onboarding file is [AGENTS.md](AGENTS.md).

## Development and Verification

The release gate used for `0.13.0` on Windows passed with `1483 passed`, `8 skipped`, and `86.28%` coverage. The repository also includes CI jobs for Ubuntu, macOS, Windows, Python 3.10 through 3.13, Go, Rust, linting, formatting, Bandit, E2E, smoke, and wheel install validation.

Useful local commands:

```bash
uv sync --extra dev --extra sync --extra vector
uv run ruff check src/contextgo scripts tests
uv run ruff format --check src/contextgo scripts tests
uv run mypy src/contextgo --ignore-missing-imports --no-error-summary
uv run bandit -r src/contextgo -c pyproject.toml --quiet
uv run pytest
uv run python scripts/e2e_quality_gate.py
uv run python -m contextgo smoke --sandbox
uv run python -m build --wheel
```

## Repository Map

| Path | Role |
|---|---|
| `src/contextgo/context_cli.py` | CLI entry point and subcommands. |
| `src/contextgo/context_runtime.py` | Cross-platform paths, atomic writes, PID files, and service definitions. |
| `src/contextgo/context_sync.py` | Encrypted GitHub sync protocol and client. |
| `src/contextgo/context_daemon.py` | Background capture, local-first sync scheduling, and daemon loop. |
| `src/contextgo/source_adapters.py` | Tool-specific local storage discovery and extraction. |
| `src/contextgo/session_index.py` | Session SQLite index, search, ranking, and FTS fallback. |
| `src/contextgo/memory_index.py` | Durable memory index, export/import, redaction, and path sanitization. |
| `src/contextgo/vector_index.py` | Optional vector index and hybrid search. |
| `native/session_scan/` | Rust hot-path scanner. |
| `native/session_scan_go/` | Go parallel scanner. |
| `.github/workflows/verify.yml` | Full CI verification pipeline. |

## Security Model

ContextGO is local-first by default. The highest-risk operations, including remote sync and viewer exposure beyond loopback, are explicit. Export and sync paths sanitize known secret patterns and absolute user paths before data leaves the local runtime. GitHub sync stores encrypted payloads only; GitHub tokens and sync passphrases are never written into exported snapshots or remote shards.

Report vulnerabilities through [.github/SECURITY.md](.github/SECURITY.md).

## Documentation

| Topic | Link |
|---|---|
| Configuration | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| API | [docs/API.md](docs/API.md) |
| Migration | [docs/MIGRATION.md](docs/MIGRATION.md) |
| Troubleshooting | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Shell completion | [docs/SHELL_COMPLETION.md](docs/SHELL_COMPLETION.md) |
| Changelog | [.github/CHANGELOG.md](.github/CHANGELOG.md) |

## License

ContextGO is licensed under [AGPL-3.0-only](LICENSE).

Copyright 2025-2026 [Dunova](https://github.com/dunova).
