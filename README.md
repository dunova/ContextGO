<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/media/logo-dark.svg">
    <img src="docs/media/logo.svg" alt="ContextGO Logo" width="380">
  </picture>
</p>

<p align="center">
  <strong>Local-First Context &amp; Memory Runtime for Multi-Agent AI Coding Teams</strong><br>
  <em>Unified cross-agent memory, sub-30ms two-stage hybrid retrieval, native Model Context Protocol (MCP), and zero-knowledge encrypted multi-machine sync.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/v/contextgo?color=2563eb&style=flat" alt="PyPI"></a>
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/pyversions/contextgo?color=3776ab&style=flat" alt="Python"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/verify.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/verify.yml/badge.svg" alt="Verify"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://codecov.io/gh/dunova/ContextGO"><img src="https://img.shields.io/badge/coverage-86%25-brightgreen?style=flat" alt="Coverage"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-Compatible-10b981?style=flat&logo=anthropic" alt="MCP Compatible"></a>
  <a href="https://github.com/dunova/ContextGO/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-6d28d9?style=flat" alt="License"></a>
</p>

<p align="center">
  <a href="https://github.com/dunova/ContextGO/stargazers">
    <img src="https://img.shields.io/badge/⭐_Star_on_GitHub-Support_Open_Memory-ffd700?style=for-the-badge&logo=github&logoColor=black" alt="Star on GitHub">
  </a>
  <a href="https://github.com/dunova/ContextGO/subscription">
    <img src="https://img.shields.io/badge/🔔_Watch_Releases-Get_Instant_Updates-2563eb?style=for-the-badge&logo=github&logoColor=white" alt="Watch Releases">
  </a>
</p>

<p align="center">
  <a href="#overview--architecture">Architecture</a> •
  <a href="#why-contextgo">Why ContextGO?</a> •
  <a href="#whats-new-in-v0150-1260x-faster">What's New in v0.15.0</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#native-mcp-server-support">Native MCP</a> •
  <a href="#supported-ai-agents--ides">Supported Agents</a> •
  <a href="#hybrid-two-stage-retrieval-engine">Retrieval Engine</a> •
  <a href="#cli-command-reference">CLI Reference</a> •
  <a href="#zero-knowledge-multi-device-sync">Encrypted Sync</a> •
  <a href="README.zh.md">简体中文</a>
</p>

---

## Overview & Architecture

Modern AI software engineering rarely relies on a single isolated model. In practical workflows, engineers fluidly pivot across multiple AI assistants: **Claude Code** for terminal-based codebase reasoning, **Cursor** or **Windsurf** for editor completions, **Antigravity / Gemini** for autonomous multi-agent task execution, and **DeepSeek Agent / Codex** for heavy refactoring.

However, each AI assistant operates within a **siloed, ephemeral sandbox**. When you switch tools or reboot terminal sessions:
- **Historical context evaporates**: Architectural decisions, code explorations, and hard bug investigations disappear.
- **Agents repeat known failures**: An assistant tries the exact broken patch another agent already disproved an hour ago.
- **Context-switching friction explodes**: Engineers waste mental bandwidth manually copying logs, error traces, and decisions between different AI tools.

**ContextGO unifies these fragmented worlds into a private, local-first intelligence runtime.** It runs silently on your machine, auto-discovers and indexes sessions from **15+ AI coding environments**, exposes a native **Model Context Protocol (MCP)** stdio server, and delivers **sub-30ms hybrid lexical/vector recall** with zero data exfiltration.

<p align="center">
  <a href="docs/media/contextgo-architecture-showcase-en.png">
    <img src="docs/media/contextgo-architecture-showcase-en.png" alt="ContextGO Multi-Agent Context & Memory Architecture Showcase" width="100%">
  </a>
</p>
<p align="center"><em>ContextGO 4-Tier Architecture: Multi-Agent Adapters, Local SQLite Engine, Interfaces & Native MCP Server, and Encrypted Multi-Device Sync.</em></p>

---

## Why ContextGO?

| Capability | What ContextGO Delivers | Traditional Workflows |
|---|---|---|
| **Ecosystem Reach** | **15+ AI tools auto-indexed** (Claude Code, Cursor, Windsurf, Antigravity, Copilot, DeepSeek, OpenCode, etc.) | Isolated, vendor-locked proprietary log silos |
| **Retrieval Latency** | **Sub-30ms hybrid recall** (SQLite FTS5 BM25 coarse recall + 256D vector cosine rerank) | Multi-second lag or naive slow brute-force grep |
| **Incremental Sync** | **mtime-based bypass** (178ms scan across 4,500+ sessions; 83x faster) | Full disk re-reading and 600k+ repetitive JSON deserializations |
| **Model Context Protocol** | **Native MCP Server (`contextgo mcp`)** with stdio JSON-RPC 2.0 tool calling | Ad-hoc terminal hacks or no assistant integration |
| **Privacy & Security** | **100% Local-First**, zero telemetry, zero mandatory cloud dependencies | Remote cloud database lock-in, data privacy risks |
| **Multi-Device Mobility** | **AES-256-GCM encrypted sync** over private Git storage with conflict-free shards | Manual copy-pasting or fragmented machine state |
| **Durable Knowledge** | **ContextGO Save Gate** (`contextgo save`) for decisions, bug post-mortems, and handoffs | Ephemeral chat history that vanishes after session exit |

---

## ⚡ What's New in v0.15.0 (1,260x Faster Retrieval)

The `v0.15.0` release introduces a complete re-architecture of the search pipeline and session adapter synchronization, eliminating legacy bottlenecks:

1. **Two-Stage Coarse-to-Fine Search Funnel**:
   - **Stage 1 (Coarse BM25 Recall)**: Uses SQLite's persistent `FTS5` virtual table with BM25 scoring (`title 3x > file_path 2x > content 1x`). Retrieves Top-150 candidates in **~2ms** across 4,500+ sessions.
   - **Stage 2 (Fine Vector Cosine Reranking)**: Computes batch vector dot-products only for the candidate paths using ultra-compact 256-dimensional embeddings, followed by Reciprocal Rank Fusion (RRF).
   - **Benchmark Result**: Total hybrid retrieval latency plummeted from **35,224ms to 27.87ms (1,260x speedup)**.
2. **mtime-Based Short-Circuit in Adapters**:
   - `_sync_factory_sessions`, `_sync_hermes_sessions`, and all active adapters now maintain an existing mtime cache.
   - Files unmodified since the previous sync are skipped immediately without disk I/O or `json.loads`. Single adapter sync dropped from **14,904ms to 178ms (83x speedup)**.
3. **Offline Fast Snapshot Loading**:
   - Embedding models are loaded directly from local snapshots in **132ms**, bypassing redundant remote HuggingFace Hub network checks.
4. **Self-Healing Index Throttling**:
   - Synchronized commit timestamp tracking resolves throttle-bypass races during heavy multi-agent workflows.

---

## Quick Start

### 1. Installation

Install ContextGO globally using `pipx` to keep your environment isolated:

```bash
# Standard installation with lexical hybrid recall & core engine
pipx install "contextgo[vector]"

# Include zero-knowledge encrypted multi-machine sync
pipx install "contextgo[sync,vector]"
```

### 2. Shell Integration

Add instant shell aliases (`cg` for quick recall, `cgs` for full-text search, `cgse` for semantic recall):

```bash
eval "$(contextgo shell-init)"
```

*Tip: Append that line to your `~/.zshrc` or `~/.bashrc`.*

### 3. Verify Health & Auto-Detected Adapters

```bash
# Check runtime health, active databases, and vector status
contextgo health

# Inspect all detected AI coding tools and session counts on your machine
contextgo sources
```

### 4. Cross-Platform & Linux Deployment

ContextGO is engineered for instant operation across **macOS, Linux (Ubuntu, Debian, Fedora, Arch), and WSL2**.

#### One-Click Daemon Deployment (systemd --user / launchd)

Run the unified deploy script to sync code, create shims, and configure auto-starting background daemons:

```bash
# Clone the repository
git clone https://github.com/dunova/ContextGO.git
cd ContextGO

# One-click deployment
bash scripts/unified_context_deploy.sh
```

- **On Linux**: Automatically generates and activates `systemd --user` service and timer units:
  ```bash
  systemctl --user status contextgo-daemon.service
  systemctl --user list-timers
  ```
- **On macOS**: Automatically installs and kickstarts LaunchAgents (`com.contextgo.daemon.plist`).

#### Remote Linux Node Synchronization & Migration

Easily deploy runtime or replicate memory packs to remote Linux development servers via `sync_linux_node.sh`:

```bash
# 1. Export and import memory package to a remote server
bash scripts/sync_linux_node.sh ubuntu@remote-server.internal

# 2. Full remote deployment (syncs runtime + configures systemd service remotely)
bash scripts/sync_linux_node.sh ubuntu@remote-server.internal --full-deploy
```

#### Air-Gapped / Offline Memory Pack Migration

```bash
# Export memory package to a portable JSON file
contextgo memory-pack export --out ./memories_backup.json

# Import into another machine (idempotent, deduplicated by content hash)
contextgo memory-pack import ./memories_backup.json

# Inspect node identity and multi-device memory distribution
contextgo node
```

---

## Native MCP Server Support

ContextGO natively implements the **Model Context Protocol (MCP)** specification via standard I/O (JSON-RPC 2.0). Any MCP-compliant client can discover, query, and record durable memory directly.

### Launch Server

```bash
contextgo mcp
```

### Configure in Claude Desktop / Cursor / Windsurf / Antigravity

Add ContextGO to your MCP client configuration (`claude_desktop_config.json` or IDE MCP settings):

```json
{
  "mcpServers": {
    "contextgo": {
      "command": "contextgo",
      "args": ["mcp"]
    }
  }
}
```

### Available MCP Tools

| Tool Name | Parameters | Description |
|---|---|---|
| `contextgo_search` | `query` (str), `limit` (int, default 5), `literal` (bool) | High-speed FTS5 full-text & keyword search across sessions |
| `contextgo_semantic` | `query` (str), `limit` (int, default 5) | Semantic vector retrieval over shared memory observations |
| `contextgo_save` | `title` (str), `content` (str), `tags` (str) | Save durable memory (architecture decisions, bug post-mortems, handoffs) |
| `contextgo_status` | *none* | Return runtime health, indexed document counts, and adapter status |

---

## Supported AI Agents & IDEs

ContextGO auto-discovers session data from the following tools without requiring manual configuration:

| Tool / Agent | Source Type Identifier | Session Format | Auto-Discovery |
|---|---|---|:---:|
| **Claude Code** | `claude_session` | JSONL events | ✅ |
| **Cursor** | `cursor_session` | SQLite state & transcripts | ✅ |
| **Windsurf / Cascade** | `windsurf_session` | State databases & JSON logs | ✅ |
| **Antigravity / Gemini** | `gemini_session` / `antigravity_session` | Trajectory transcripts & subagents | ✅ |
| **DeepSeek Agent (`dsh`)** | `deepseek_session` | Stream logs & markdown history | ✅ |
| **OpenCode** | `opencode_session` | JSON transcripts | ✅ |
| **GitHub Copilot CLI** | `copilot_session` | CLI conversation logs | ✅ |
| **Codex CLI** | `codex_session` | Rollout logs & JSONL | ✅ |
| **Aider** | `aider_session` | Chat markdown logs | ✅ |
| **Factory / Droid** | `factory_session` | Multi-turn sessions | ✅ |
| **Hermes** | `hermes_session` | Task execution traces | ✅ |
| **Kilo** | `kilo_session` | Conversation logs | ✅ |

---

## Hybrid Two-Stage Retrieval Engine

ContextGO does not force a false choice between speed and semantic depth:

```
 User Query: "Why did we switch to Cloudflare Anycast IP?"
                      │
                      ▼
 ┌────────────────────────────────────────────────────────┐
 │ Stage 1: SQLite FTS5 BM25 Coarse Search (~2ms)         │
 │ 4,500+ documents filtered down to Top-150 candidates   │
 └────────────────────────────────────────────────────────┘
                      │
                      ▼
 ┌────────────────────────────────────────────────────────┐
 │ Stage 2: 256D Dense Vector Cosine Reranking (~15ms)    │
 │ Batch dot-product on candidate matrix + RRF fusion     │
 └────────────────────────────────────────────────────────┘
                      │
                      ▼
 Result: Top-K Ranked Context Snippets (Total Latency: ~27ms)
```

- **Lexical Precision (FTS5 + BM25)**: Exact hashes, function names, error codes, and configuration parameters match reliably without semantic fuzziness.
- **Semantic Understanding (Vectors)**: Conceptual topics, past rationale, and natural language questions recall relevant context even when keywords differ.
- **Reciprocal Rank Fusion (RRF)**: Combines rankings mathematically:
  $$\text{RRF Score}(d) = \sum_{m \in \{\text{BM25}, \text{Vector}\}} \frac{1}{k + \text{rank}_m(d)}$$

---

## CLI Command Reference

### Quick Recall & Search

```bash
# 1. Quick Recall (Auto-detects session ID vs keyword query)
contextgo q "network latency issue"
contextgo q "20260921-114317-codex"

# 2. High-Speed Full-Text Search
contextgo search "memory leak in worker" --limit 5
contextgo search "0925v8_opt.yaml" --literal

# 3. Semantic Vector Search
contextgo semantic "how did we fix websocket dropouts?" --limit 5
```

### Knowledge Persistence

Record durable knowledge when finishing a task, fixing a hard bug, or making architectural decisions:

```bash
contextgo save \
  --title "Decision: Adopted SQLite FTS5 for Stage 1 Retrieval" \
  --content "docs/handovers/20260926_search_engine_upgrade.md\n\nReplaced linear brute-force scan with FTS5 BM25 coarse filtering, reducing retrieval latency from 35s to 27ms." \
  --tags "search,sqlite,perf,architecture"
```

### System Inspection & Housekeeping

```bash
# Health check (validates SQLite DB, vector embeddings, permissions)
contextgo health

# List active data sources and document counts
contextgo sources

# Force re-index across all adapters
contextgo sync --force
```

---

## Zero-Knowledge Multi-Device Sync

ContextGO supports peer-to-peer encrypted sync across laptops and workstations using any private Git repository as an encrypted storage backend:

```
 Workstation A                          Private Git Remote                         Workstation B
┌──────────────┐                        ┌─────────────────┐                       ┌──────────────┐
│ Local Memory │ -- AES-256-GCM Push -> │ Encrypted Blobs │ <- AES-256-GCM Pull - │ Local Memory │
│ Observations │    (Zero-Knowledge)    │ (No plaintext)  │    (Zero-Knowledge)   │ Observations │
└──────────────┘                        └─────────────────┘                       └──────────────┘
```

1. **Zero-Knowledge Encryption**: All session summaries, handoffs, and memory observations are encrypted locally using **AES-256-GCM** before leaving your machine.
2. **Conflict-Free Sharding**: Each machine writes to its own isolated cryptographically signed shard (`<machine_id>.shard`), eliminating merge conflicts.
3. **Zero Third-Party Accounts**: Uses standard Git SSH/HTTPS credentials—no proprietary cloud SaaS accounts required.

---

## Privacy, Security & Anti-Hallucination

- **No Remote Telemetry**: ContextGO contains zero tracking scripts, analytic pings, or background data collection.
- **Local SQLite Storage**: Your data resides strictly in `~/.contextgo/index/` on your own disk.
- **Air-Gapped Embedding Support**: Pre-cached compact embedding models run entirely offline on local CPU / Apple Silicon.
- **Safe Path Normalization**: User directory paths are normalized dynamically at runtime, preventing accidental leakage of usernames or local directory structures.

---

## License

ContextGO is licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
