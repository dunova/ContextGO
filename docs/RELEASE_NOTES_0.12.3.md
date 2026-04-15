# Release Notes — ContextGO 0.12.3 / 发布说明

## Highlights / 亮点

- **Factory / Droid is now a first-class source**: local Droid sessions under `~/.factory/sessions/**` are now indexed and searchable across platforms. / Droid 会话正式接入统一索引
- **Hermes is now a first-class source**: Hermes session files under `~/.hermes/sessions/` are now indexed and searchable from other agents. / Hermes 会话正式接入统一索引
- **Default smart recall is now wired for OpenCode, Hermes, and Factory/Droid**: `contextgo setup` updates their real config/prompt entrypoints instead of leaving them as “search-only” platforms. / OpenCode、Hermes、Factory/Droid 默认智能召回已接通

## Breaking Changes / 破坏性变更

None. This is an additive compatibility release. / 无破坏性变更。

## New Features / 新增功能

- `factory_session` adapter for local Factory/Droid JSONL conversations.
- `hermes_session` adapter for local Hermes JSONL conversations.
- `source_inventory()` and `contextgo sources` now expose `factory` and `hermes`.
- `contextgo setup` now configures:
  - OpenCode via `~/.opencode/opencode.json` / `~/.config/opencode/opencode.json`
  - Hermes via `~/.hermes/SOUL.md`
  - Factory/Droid via `~/.factory/AGENTS.md` and `~/.factory/droids/*.md`

## Improvements / 改进

- Session index search types now include `factory` and `hermes`.
- Source weights now rank Factory and Hermes sessions as adapter-backed primary sessions rather than miscellaneous history.
- README and CLI help now match the real supported platform surface.

## Bug Fixes / 修复

- Fixed the gap where Factory/Droid conversations existed locally but were invisible to ContextGO search.
- Fixed the gap where Hermes conversations existed locally but were invisible to ContextGO search.
- Fixed the gap where OpenCode / Hermes / Factory/Droid had no built-in smart-recall setup path despite being active platforms.

## Performance / 性能

- No algorithmic slowdown added to the recall path; new platform adapters normalize to cached JSONL mirrors like existing adapters. / 新增平台沿用统一镜像缓存，不引入额外热路径开销

## Documentation / 文档

- Updated README and README.zh support lists and instruction-entrypoint table.
- Updated CLI `setup --help` copy.
- Added these release notes and refreshed docs index.

## Contributors / 贡献者

- Dunova
- Codex

## Verification / 验证

- `python3 -m py_compile src/contextgo/context_prewarm.py src/contextgo/source_adapters.py src/contextgo/session_index.py src/contextgo/context_cli.py`
- `python3 -m pytest -o addopts='' tests/test_context_prewarm.py tests/test_source_adapters.py`
- `PYTHONPATH=src python3 -m contextgo.context_cli setup`
- `PYTHONPATH=src python3 -m contextgo.context_cli sources`

## Upgrade Path / 升级路径

```bash
pipx upgrade "contextgo[vector]"
contextgo setup
contextgo sources
contextgo health
```

Re-run `contextgo setup` after upgrading so OpenCode, Hermes, and Factory/Droid receive the new smart-recall policy wiring. / 升级后请重新运行 `contextgo setup`，让 OpenCode、Hermes、Factory/Droid 写入新的 smart-recall 配置。
