<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/media/logo-dark.svg">
    <img src="docs/media/logo.svg" alt="ContextGO" width="380">
  </picture>
</p>

<p align="center">
  <strong>Local-First Context & Memory Runtime for Multi-Agent AI Coding Teams</strong><br>
  <em>Unified cross-agent memory, hybrid BM25/vector recall, and end-to-end encrypted multi-machine sync.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/v/contextgo?color=2563eb&style=flat" alt="PyPI"></a>
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/pyversions/contextgo?color=3776ab&style=flat" alt="Python"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/verify.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/verify.yml/badge.svg" alt="Verify"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://github.com/dunova/ContextGO/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-6d28d9?style=flat" alt="License"></a>
</p>

<p align="center">
  <a href="#key-features">Key Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#supported-ai-agents--tools">Supported Agents</a> •
  <a href="#core-cli-reference">CLI Reference</a> •
  <a href="#encrypted-multi-machine-sync">Encrypted Sync</a> •
  <a href="#ai-agent-smart-recall-scf">Smart Recall</a> •
  <a href="README.zh.md">简体中文</a>
</p>

---

## What is ContextGO?

**ContextGO** is a high-performance, local-first context and memory runtime engineered for modern AI coding workflows. It breaks down memory silos across tools, editors, and machines by indexing conversations, technical decisions, and execution sessions from **15+ AI coding agents** into an ultra-fast, local SQLite runtime.

No cloud lock-in, no remote database dependencies, and no silent telemetry uploads. Your project history and architecture memories remain private, durable, and instantly searchable on your machines.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            AI Coding Environments                            │
│  DeepSeek (dsh) │ Reasonix │ Hermes │ Claude Code │ Antigravity │ Copilot ...│
└───────┬─────────────┬───────────┬───────────┬─────────────┬───────────┬──────┘
        │             │           │           │             │           │
        ▼             ▼           ▼           ▼             ▼           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       ContextGO Source Adapters Layer                        │
│  (Streaming zstd decompression, high-SNR event filtering, projection cache)  │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         ContextGO Local SQLite Engine                        │
│   • FTS5 Full-Text Search        • BM25S Lexical Ranking                     │
│   • Durable Memory Store         • Optional Model2Vec Embeddings + RRF       │
│   • Time-Decay Scoring           • Low-Latency Local Web Viewer UI           │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼ (Optional Opt-In)
┌──────────────────────────────────────────────────────────────────────────────┐
│                Privacy-First Encrypted GitHub Sync (AES-256-GCM)              │
│       Windows 11 (Task Scheduler) ◄───► macOS (launchd) ◄───► Linux (systemd) │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

- 🧠 **Universal Multi-Agent Memory**: Natively discovers, parses, and harmonizes sessions from **DeepSeek Agent (dsh)** (with `.zstd` streaming event decoding), **Reasonix**, **Hermes**, **Claude Code**, **Factory Droid**, **Antigravity (Gemini)**, **GitHub Copilot**, **Cursor**, **Windsurf**, **Kilo**, **Cline**, **Roo Code**, **OpenCode**, and shell histories.
- 🔌 **Native Model Context Protocol (MCP) Server**: Built-in zero-dependency MCP stdio server (`contextgo mcp`) supporting standard `tools/list` and `tools/call`, enabling out-of-the-box Function Calling in DeepSeek Agent, Claude Code, Cursor, Windsurf, and any MCP client.
- ⚡ **Sub-Second Hybrid Recall**: Combines SQLite FTS5 full-text indexing, BM25 lexical ranking, and optional lightweight Model2Vec embeddings with Reciprocal Rank Fusion (RRF) and time-decay prioritization.
- 🛡️ **Zero-Knowledge Encrypted Sync**: Synchronize context across Windows, macOS, and Linux using a private GitHub repository with client-side scrypt key derivation and AES-256-GCM encryption.
- 🎯 **Smart Context-First (SCF) Policy**: Automatically configures prompt files across all AI tools (`contextgo setup`) to enforce proactive context retrieval before answering complex architectural or refactoring questions.
- 💻 **Cross-Platform Daemon & Native Services**: Native user daemon with automatic restart on Windows (Task Scheduler), macOS (launchd), and Linux (systemd user unit).
- 🔍 **Interactive Memory Viewer**: Built-in, zero-dependency local web dashboard (`127.0.0.1:37677`) for browsing memories, session timelines, and technical decisions.

---

## Quick Start

### 1. Installation

Install ContextGO globally using `pipx` to keep your environment isolated:

```bash
# Standard installation with lexical hybrid recall
pipx install "contextgo[vector]"

# Include encrypted multi-machine sync dependencies
pipx install "contextgo[sync,vector]"
```

### 2. Shell Integration

Add instant aliases (`cg` for quick recall, `cgs` for full-text search, `cgse` for semantic recall):

```bash
eval "$(contextgo shell-init)"
```

Add the line above to your `~/.zshrc`, `~/.bashrc`, or config file.

### 3. Verify Health & Detected Sources

```bash
# Check runtime health and active index statistics
contextgo health

# View all detected AI coding tools on your machine
contextgo sources
```

### 4. Search & Recall Context

```bash
# Instant hybrid recall (auto-routes to keyword search or session ID)
contextgo q "how did we resolve the router DNS latency?"

# Full-text exact search across all tool histories
contextgo search "AdGuard Home" --limit 5

# Memory-first semantic recall
contextgo semantic "architecture decisions for sync engine" --limit 3
```

---

## Supported AI Agents & Tools

ContextGO automatically indexes and standardizes sessions across your environment without manual configuration:

| Category | Supported Tools & Platforms | Discovery Mechanism |
|---|---|---|
| **Autonomous Agents** | **DeepSeek Agent (`dsh`)** | `.dsh/storages/session_projcache.json`, `sessions/**/*.zstd` |
| | **Reasonix Agent** | `.reasonix/projects/*/sessions`, `events.jsonl`, `turns` |
| | **Hermes Agent** | `~/.hermes/sessions/*.jsonl`, sidecar metadata |
| | **Claude Code** | `~/.claude/projects/`, `~/.claude/transcripts/` |
| | **Factory Droid** | `~/.factory/sessions/*.jsonl` |
| | **OpenClaw & Accio** | `~/.openclaw/agents/`, `~/.accio/agents/` |
| **IDEs & Coding Assistants** | **Antigravity (Gemini)** | `~/.gemini/antigravity/brain/*/walkthrough.md`, `logs` |
| | **GitHub Copilot** | `~/.copilot/session-state/*/events.jsonl` |
| | **Cursor & Windsurf** | Global storage workspaces & vscdb SQLite stores |
| | **Kilo, Cline & Roo Code**| VS Code globalStorage task state & transcripts |
| | **OpenCode & Zed** | `opencode.db`, `.config/zed/conversations/` |
| **Shell & Manual** | **Terminal Shells** | `~/.zsh_history`, `~/.bash_history` |
| | **Durable Memories** | `contextgo save`, exported JSON observation snapshots |

---

## Core CLI Reference

```
usage: contextgo [-h] [--version] <command> ...
```

| Command | Usage Example | Description |
|---|---|---|
| `q` | `contextgo q "query"` | **Fast hybrid recall**: Auto-routes query to BM25S/FTS or session ID lookup. |
| `search` | `contextgo search "keyword" --limit 10` | **Full-text search**: Query indexed session logs and tool calls. |
| `semantic` | `contextgo semantic "topic" --limit 5` | **Semantic search**: Memory-first retrieval with session fallback. |
| `save` | `contextgo save --title "..." --content "..."` | **Save durable memory**: Persist key architectural conclusions to local storage. |
| `sources` | `contextgo sources` | **Inspect adapters**: Print detected platforms, session counts, and paths. |
| `health` | `contextgo health` | **Health check**: Output JSON status report of DBs and subsystems. |
| `serve` | `contextgo serve --port 37677` | **Web UI**: Launch local zero-dependency memory viewer dashboard. |
| `sync` | `contextgo sync {init,push,pull,status,run}` | **Encrypted sync**: Manage cross-machine GitHub repository synchronization. |
| `setup` | `contextgo setup` | **One-command setup**: Inject Smart Recall (SCF) rules into all AI tools. |
| `unsetup` | `contextgo unsetup` | **Teardown**: Safely remove all injected ContextGO prompt rules. |
| `daemon` | `contextgo daemon {start,stop,status,install}` | **Daemon management**: Control background capture and OS service unit. |
| `export` | `contextgo export "" backup.json` | **Sanitized export**: Export observations with automatic secret redaction. |
| `import` | `contextgo import backup.json` | **Import**: Restore observation payloads into local memory store. |
| `smoke` | `contextgo smoke --sandbox` | **Quality gate**: Run end-to-end verification in an isolated sandbox. |

---

## Encrypted Multi-Machine Sync

ContextGO provides private, zero-knowledge multi-machine synchronization backed by any private GitHub repository:

```bash
# 1. Initialize sync on your primary machine (e.g. Windows 11)
contextgo sync init --repo your-user/my-contextgo-sync --device-id desktop-win11

# 2. Push encrypted shards
contextgo sync push

# 3. Pull and merge on your secondary machine (e.g. macOS)
pipx install "contextgo[sync,vector]"
contextgo sync init --repo your-user/my-contextgo-sync --device-id macbook-m4
contextgo sync pull
```

### Security Architecture

- **Client-Side AES-256-GCM**: Payloads are compressed and encrypted locally before leaving your machine.
- **Passphrase-Derived Key**: Key derived with `scrypt` using per-repository salt. Your password never leaves your device.
- **Independent Device Shards**: Each machine commits to its own encrypted partition (`shards/<device-id>.enc.json`) to eliminate merge conflicts.
- **Pre-Upload Sanitization**: Absolute paths, API keys, tokens, and secret patterns are automatically redacted before encryption.

---

## AI Agent Smart Recall (SCF)

Configure all your AI assistants to read project context automatically:

```bash
contextgo setup
```

This injects the **Smart Context-First (SCF)** policy into active agent instruction files (e.g., `~/.gemini/GEMINI.md`, `~/.reasonix/AGENTS.md`, `~/.dsh/AGENTS.md`, `~/.hermes/SOUL.md`, `~/.claude/CLAUDE.md`, `.github/copilot-instructions.md`, `.cursorrules`).

### Proactive Recall Policy Table

| Trigger | Agent Action |
|---|---|
| Continuation task (`接着做` / `continue`) | Run `contextgo semantic "<topic>" --limit 3` |
| Uncertainty regarding past decisions | Run `contextgo search "<keyword>" --limit 5` |
| Before major architectural refactoring | Query previous design decisions before altering code |
| Root cause confirmed | Save durable memory via `contextgo save --title "..."` |

---

## Daemon & Background Services

Run ContextGO as a native, background-indexed service:

```bash
# Manage daemon state
contextgo daemon start
contextgo daemon status
contextgo daemon stop

# Install native OS service unit
contextgo daemon install
```

| Operating System | Service Backend |
|---|---|
| **macOS** | Native user `launchd` service (`~/Library/LaunchAgents/`) |
| **Linux** | Native `systemd` user service (`~/.config/systemd/user/`) |
| **Windows** | Native Windows Task Scheduler user task |

---

## Development & Verification

ContextGO maintains rigorous release gates with **86%+ test coverage** and extensive platform matrices:

```bash
# Clone repository
git clone https://github.com/dunova/ContextGO.git
cd ContextGO

# Sync dependencies with uv
uv sync --extra dev --extra sync --extra vector

# Run code style & security gates
uv run ruff check src/contextgo tests
uv run ruff format --check src/contextgo tests
uv run mypy src/contextgo --ignore-missing-imports
uv run bandit -r src/contextgo -c pyproject.toml --quiet

# Run test suite
uv run pytest
uv run python -m contextgo smoke --sandbox
```

---

## License

ContextGO is licensed under the [AGPL-3.0-only](LICENSE) license.

Copyright © 2025-2026 [Dunova](https://github.com/dunova).
