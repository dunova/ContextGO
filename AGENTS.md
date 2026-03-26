# AGENTS.md — AI Agent Onboarding for ContextGO
# AI 智能体入门指南

> If you are an AI agent (Claude, Codex, Cursor, Windsurf, or any LLM-powered tool),
> this file tells you everything you need to set up and use ContextGO in under 60 seconds.
>
> 如果你是 AI 智能体（Claude、Codex、Cursor、Windsurf 等），本文档可让你在 60 秒内完成 ContextGO 的配置与上手。

---

## Quick Setup (AI Auto-Install) / 快速安装

**Requirements:** Python 3.10+, Bash, Git.

```bash
git clone https://github.com/dunova/ContextGO.git && cd ContextGO && bash scripts/unified_context_deploy.sh && python3 scripts/context_cli.py smoke --sandbox
```

Works on macOS and Linux. No Docker. No MCP. No external services required.

适用于 macOS 和 Linux。无需 Docker、无需 MCP、无外部服务依赖。

> For full configuration options, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).
> For HTTP API reference, see [docs/API.md](docs/API.md).

---

## What is ContextGO?

ContextGO is a local-first context and memory runtime that unifies Codex, Claude, and shell session histories into one searchable, auditable index stored in local SQLite. It gives AI agents persistent cross-session memory, semantic search over past decisions, and a save/recall loop — all via a single CLI with no external infrastructure.

---

## Project Map

| Path | Role |
|---|---|
| `scripts/context_cli.py` | **CLI entry point** — all commands go through here |
| `scripts/context_config.py` | Storage root, env var resolution |
| `scripts/session_index.py` | SQLite-backed session index and FTS5 search |
| `scripts/memory_index.py` | Memory and observation index, export/import |
| `scripts/context_daemon.py` | Session capture and sanitization daemon |
| `scripts/context_server.py` | Local viewer API server |
| `scripts/context_core.py` | Core helpers: file scan, memory write, mtime |
| `scripts/context_native.py` | Rust/Go hot-path orchestration |
| `scripts/context_smoke.py` | Smoke test suite |
| `native/session_scan/` | Rust scanner binary |
| `native/session_scan_go/` | Go parallel scanner binary |
| `benchmarks/` | Performance harness |
| `templates/` | systemd/launchd service templates |
| `artifacts/` | Autoresearch outputs — do not edit |
| `patches/` | Compatibility notes — do not edit |

---

## Key Commands

```bash
# 1. Health check — verify installation state
python3 scripts/context_cli.py health

# 2. Smoke gate — confirm full command surface is working (sandboxed, does not touch ~/.contextgo)
python3 scripts/context_cli.py smoke --sandbox

# 3. Search past sessions by keyword
python3 scripts/context_cli.py search "auth root cause" --limit 10

# 4. Semantic search across local memories
python3 scripts/context_cli.py semantic "database design decision" --limit 5

# 5. Save a memory for future retrieval
python3 scripts/context_cli.py save --title "Fix: JWT expiry" --content "Set exp to 3600 in auth.py line 42" --tags auth,jwt
```

---

## Do Not Modify

These paths are managed automatically or are read-only references. Do not edit them directly:

- `artifacts/` — autoresearch outputs, test sets, QA reports
- `patches/` — compatibility notes
- `.github/` — CI/CD workflows

---

## Before Any Commit

All steps must pass:

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

# Health check
bash scripts/context_healthcheck.sh
```

---

## Automatic Context Behaviors

These are not commands you wait for the user to invoke. As an AI agent, you
should execute these behaviors proactively during your normal workflow.

### Auto-search (do this silently, without being asked)

| Situation | Action |
|-----------|--------|
| Session starts with a continuation task | `contextgo semantic "<topic>" --limit 3` |
| You are unsure about project history | `contextgo search "<keyword>" --limit 5` |
| User asks about past work | `contextgo semantic "<question>"` |
| Before an architectural decision | `contextgo search "<topic>" --limit 3` |

**How to present results**: Summarize in 2-3 sentences. Do NOT paste raw output.
If search returns nothing, proceed silently -- do not mention the search.

### Auto-save (suggest or execute at milestones)

| Situation | Action |
|-----------|--------|
| Hard bug root cause found | `contextgo save --title "Bug: ..." --content "..." --tags bug,...` |
| Architectural decision made | `contextgo save --title "Decision: ..." --content "rationale" --tags decision,...` |
| Session wrap-up ("done", "wrap up") | `contextgo save --title "Handoff: ..." --content "next steps" --tags handoff,...` |

### Commands

```bash
# Broad recall (saved memories first, then session history)
contextgo semantic "natural language question" --limit 3

# Keyword search (direct FTS5)
contextgo search "specific keyword" --limit 5

# Exact match
contextgo search "exact phrase" --literal --limit 5

# Save conclusion
contextgo save --title "Brief title" --content "Full details" --tags "project,topic"

# Cross-tool handoff
contextgo export "" /tmp/snapshot.json --limit 5000
contextgo import /tmp/snapshot.json
```

Storage root: `~/.contextgo` (override: `CONTEXTGO_STORAGE_ROOT`).

---

## Skills (optional Claude Code integration)

For Claude Code users, ContextGO ships skills in `skills/` that provide
additional structure for the GSD workflow:

```bash
bash skills/install.sh
```

| Skill | Purpose |
|-------|---------|
| `contextgo-gsd` | Full recall-execute-persist workflow reference |
| `contextgo-recall` | Context search and summarization guide |
| `contextgo-save` | When and how to persist conclusions |

These skills complement the auto-behaviors above. The auto-behaviors work
without skills installed -- they are driven by the instructions in this file
and `.claude/CLAUDE.md`.

### GSD Loop

1. **Recall** -- At session start, `contextgo semantic` to prime context
2. **Execute** -- Work normally; daemon captures everything in background
3. **Persist** -- At milestones, `contextgo save` key decisions

This replaces MCP with a zero-dependency CLI + Skill pattern. No server, no protocol negotiation, no Docker. The AI agent calls the CLI directly.

### Design Philosophy

- **CLI-first**: Skills wrap CLI commands, not HTTP APIs
- **Local-only**: All data stays in `~/.contextgo`, zero cloud dependency
- **Zero-config**: `pip install contextgo && bash skills/install.sh` is the entire setup
- **Composable**: Each skill is standalone; use one, two, or all three
