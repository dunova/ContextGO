# ContextGO 0.14.0 Release Notes

**Release Date:** August 15, 2026

## Overview / 版本概览

ContextGO 0.14.0 introduces full multi-agent support for **Reasonix**, **DeepSeek Agent (dsh)**, and **Hermes Agent**, featuring high-SNR context extraction, streaming `.zstd` decompression for DeepSeek session streams, unified hybrid ranking, and full smart recall policy injection.

ContextGO 0.14.0 全面增强了对 **Reasonix**、**DeepSeek Agent (dsh)** 与 **Hermes Agent** 的深度支持，带来高信噪比事件抽取、DeepSeek `.zstd` 会话流原生解压、混合检索排序优化与智能召回策略自动注入。

---

## Key Highlights / 核心亮点

### 1. DeepSeek Agent (dsh) Full Native Support
- **Streaming `.zstd` Decompression**: Automatically decodes and parses compressed DeepSeek event logs (`session.jsonl.zstd`) using system `zstd` or Python libraries.
- **Multidimensional Projection Fusion**: Merges `session_projcache.json` metadata (titles, statistics, summaries, turns) with fine-grained user/assistant/tool messages.
- **Full-Text & Hybrid Recall**: Enables instant sub-second lookup on DeepSeek conversations via `contextgo q` and `contextgo search`.

### 2. Reasonix Agent Adapter & High-SNR Filtering
- **Multi-Workspace Auto-Discovery**: Automatically discovers sessions across `~/.reasonix/projects/*/sessions`, `~/.reasonix/sessions`, and local workspace trees.
- **Noise Filtration**: Prunes voluminous base64 dumps and raw stdout while preserving core prompts, reasoning steps (`reasoning_content`), tool calls, and final conclusions.

### 3. Hermes Agent Deep Integration
- Enhanced multi-root session discovery and direct SOUL/AGENTS smart recall policy injection.

### 4. Smart Recall Prewarm Integration
- `contextgo setup` now automatically configures **Reasonix** (`~/.reasonix/AGENTS.md`) and **DeepSeek** (`~/.dsh/AGENTS.md`) with Context-First (SCF) Smart Recall rules.

---

## Upgrade Guide / 升级指南

```bash
# Upgrade installed ContextGO via pipx
pipx install /path/to/ContextGO --force

# Verify health and detected agent sources
contextgo sources
contextgo health
```
