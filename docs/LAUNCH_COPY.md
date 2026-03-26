# Launch Copy

## One-Liner / 一句话简介

ContextGO 是一个面向多 agent AI 编码团队的本地优先上下文运行时：统一 CLI、精确检索、记忆管理、smoke 验证与 Rust/Go 热路径，默认无 MCP、无 Docker、无向量云依赖。

ContextGO is a local-first context runtime for multi-agent AI coding teams, unifying search, memory, smoke validation, and Rust/Go hot paths behind one MCP-free CLI.

## GitHub Release Copy / GitHub 发布文案

ContextGO 是我们把“上下文系统”真正产品化之后的结果。

它不是另一个桥接壳层，也不是一个必须绑定云向量库的实验项目。  
它做的事情很直接：

- 把 Codex、Claude、shell 和记忆文件统一到一条上下文链
- 用同一套 CLI 提供 `search / semantic / save / serve / health / smoke / native-scan`
- 用 `health + smoke + benchmark` 保证它不是只能演示、不能交付
- 用 Rust/Go 只替换热点路径，而不是重写整个产品

如果你在做多 agent AI 编码团队协作，且你在乎：

- 数据留在本地
- 故障可定位
- 产物可回滚
- 优化能量化

那么 ContextGO 会比大多数“再多一层编排”更贴近真实工作流。

English version:

ContextGO is what happens when a context system stops being a demo and becomes an actual local product.

It is not another bridge layer, and it does not assume cloud vectors, Docker, or MCP as the default path.

What it does is straightforward:

- unify Codex, Claude, shell, and memory files into one searchable context chain
- expose one CLI for `search / semantic / save / serve / health / smoke / native-scan`
- ship with health, smoke, benchmark, and installed-runtime validation
- upgrade hot paths with Rust/Go without changing operator workflows

If your team cares about local data boundaries, reproducibility, rollback, and lower token cost, ContextGO is designed for that operating model.

## Hacker News Title / HN 标题

Show HN: ContextGO — a local-first context runtime for AI coding teams

## Reddit Title / Reddit 标题

I built ContextGO: a local-first context + memory runtime for AI coding teams (no MCP, no Docker, no cloud vector dependency)

## X Post / X 文案

Built `ContextGO`: a local-first context runtime for AI coding teams.

- one CLI for search / memory / smoke / native hot paths
- no MCP
- no Docker
- no cloud vector dependency by default
- Rust/Go speedups without changing operator workflow

Repo: https://github.com/dunova/ContextGO
