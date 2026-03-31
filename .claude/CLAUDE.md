# CLAUDE.md — Project Instructions for Claude Code

## Project / 项目

ContextGO — local-first context and memory runtime for AI coding teams.
Entry point: `python3 src/contextgo/context_cli.py` (or `contextgo` if pip-installed)

Auto-behaviors (search on uncertainty, save on milestones) are defined in `AGENTS.md`.
自动行为（不确定时检索、里程碑时保存）规则见 `AGENTS.md`。

---

## Architecture / 架构

```
src/contextgo/     Python runtime package
  context_cli.py       CLI entry point (all commands)
  context_config.py    Env var resolution, storage root
  session_index.py     SQLite session index (FTS5 primary, LIKE fallback)
  memory_index.py      Memory index, export/import
  context_daemon.py    Session capture and sanitization
  context_server.py    Local viewer API
  context_core.py      Shared helpers: file scan, memory write
  context_native.py    Rust/Go backend orchestration
  context_smoke.py     Smoke test suite
  context_maintenance.py  Index cleanup and repair
  context_prewarm.py   Auto context prewarm engine (hooks + setup)
  vector_index.py      Optional hybrid vector search (model2vec + BM25 + RRF)
  source_adapters.py   External tool auto-discovery + normalization
tests/             Full automated test suite
scripts/           Operational scripts and compatibility wrappers
native/session_scan/       Rust hot-path binary
native/session_scan_go/    Go parallel binary
docs/              Full documentation suite
benchmarks/        Performance harness
templates/         systemd/launchd service templates
artifacts/         Autoresearch outputs (do not edit)
patches/           Compatibility notes (do not edit)
```

---

## Test Commands / 测试命令

```bash
bash -n scripts/*.sh && python3 -m py_compile src/contextgo/*.py

python3 -m pytest \
  tests/test_context_cli.py \
  tests/test_context_core.py \
  tests/test_session_index.py \
  tests/test_context_native.py \
  tests/test_context_smoke.py \
  tests/test_autoresearch_contextgo.py

python3 scripts/e2e_quality_gate.py
contextgo smoke --sandbox
python3 scripts/smoke_installed_runtime.py
bash scripts/context_healthcheck.sh
```

---

## Style Rules / 代码规范

| Language | Rule |
|---|---|
| Python | ruff-compatible; type hints on all new functions; English docstrings; Python 3.10+ |
| Rust | `cargo clippy` clean before commit |
| Go | `go vet` clean before commit |
| Shell | `shellcheck` clean; `#!/usr/bin/env bash`; `set -euo pipefail` |

---

## Project Rules / 项目规则

- All user-facing text: bilingual (English primary, Chinese secondary) / 用户可见文本双语
- No hardcoded absolute paths — use `~` or env vars / 禁止硬编码绝对路径
- No secrets, tokens, or API keys in any committed file / 禁止提交密钥
- Never commit to `artifacts/` or `patches/` without an explicit request / 勿直接修改这两个目录
- Default storage root: `~/.contextgo`; override: `CONTEXTGO_STORAGE_ROOT`
- Remote sync disabled by default; enable via `CONTEXTGO_ENABLE_REMOTE_MEMORY_HTTP=true`
- Run full test suite before every commit / 提交前必须跑完整测试
