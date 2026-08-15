# dsh-plugin-contextgo

> Official DeepSeek Agent (`dsh`) plugin for [ContextGO](https://github.com/dunova/ContextGO) — Local-first context & cross-agent memory runtime.

## Overview / 概览

`dsh-plugin-contextgo` connects **DeepSeek Agent (`dsh`)** with ContextGO's local-first multi-agent memory runtime, empowering DeepSeek models to seamlessly search and recall technical decisions, execution histories, and solutions across **15+ AI coding platforms** (including DeepSeek, Reasonix, Hermes, Claude Code, Factory, Copilot, Cursor, etc.).

## Installation / 安装

Inside your DeepSeek Agent workspace or profile directory:

```bash
pnpm add dsh-plugin-contextgo
# or
npm install dsh-plugin-contextgo
```

## Tools Provided / 提供的工具

1. **`contextgo_recall`**: Fast hybrid recall for cross-agent technical history and session context.
2. **`contextgo_search`**: Full-text lexical search over all indexed AI coding sessions.
3. **`contextgo_semantic`**: Semantic retrieval for architectural decisions and durable bug root causes.
4. **`contextgo_save`**: Persist key architectural conclusions and debugging handoffs to local storage.

## License

AGPL-3.0-only © [Dunova](https://github.com/dunova)
