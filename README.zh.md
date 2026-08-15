<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/media/logo-dark.svg">
    <img src="docs/media/logo.svg" alt="ContextGO" width="380">
  </picture>
</p>

<p align="center">
  <strong>面向多 Agent 协同的本地优先 AI 编码上下文与持久记忆运行时</strong><br>
  <em>跨 Agent 会话融合、BM25/向量混合召回、端到端加密跨机器同步</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/v/contextgo?color=2563eb&style=flat" alt="PyPI"></a>
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/pyversions/contextgo?color=3776ab&style=flat" alt="Python"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/verify.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/verify.yml/badge.svg" alt="Verify"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://github.com/dunova/ContextGO/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-6d28d9?style=flat" alt="License"></a>
</p>

<p align="center">
  <a href="#核心特性">核心特性</a> •
  <a href="#快速上手">快速上手</a> •
  <a href="#支持的-ai-agent--ide-矩阵">支持的 Agent</a> •
  <a href="#cli-核心命令参考">命令参考</a> •
  <a href="#隐私优先的跨机器加密同步">加密同步</a> •
  <a href="#ai-agent-智能上下文预热-scf">智能预热</a> •
  <a href="README.md">English</a>
</p>

---

## 什么是 ContextGO？

**ContextGO** 是专为现代 AI 编码工作流设计的高性能、本地优先（Local-First）上下文与长效记忆运行时。它打破了不同开发工具、编辑器与工作机器之间的记忆孤岛，自动发现并聚合来自 **15+ 种主流 AI Coding Agent** 的对话记录、架构决策与执行会话，统一建立毫秒级可检索的本地 SQLite 运行时。

无需云端绑定，无需外部中心化数据库，绝不静默上传遥测数据。您在所有开发环境中的技术资产与历史沉淀完全私有、长效保留且随处可查。

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            AI 编码环境与工具生态                             │
│  DeepSeek (dsh) │ Reasonix │ Hermes │ Claude Code │ Antigravity │ Copilot ...│
└───────┬─────────────┬───────────┬───────────┬─────────────┬───────────┬──────┘
        │             │           │           │             │           │
        ▼             ▼           ▼           ▼             ▼           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        ContextGO 多源适配器层 (Adapters)                     │
│  (原生 zstd 流式解压、高信噪比事件清洗过滤、会话投影缓存融合)                  │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         ContextGO 本地 SQLite 高性能引擎                     │
│   • FTS5 全文索引                 • BM25S 词法评分排序                       │
│   • 结构化持久记忆库 (Memory Store) • 可选 Model2Vec 向量嵌入 + RRF 融合     │
│   • 动态时效衰减加权 (Time-Decay) • 零依赖本地 Web 可视化仪表盘 (Viewer UI)  │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼ (用户显式开启)
┌──────────────────────────────────────────────────────────────────────────────┐
│                  隐私优先的 GitHub 端到端加密同步 (AES-256-GCM)              │
│     Windows 11 (任务计划程序) ◄───► macOS (launchd) ◄───► Linux (systemd)    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 核心特性

- 🧠 **全能多 Agent 记忆中枢**：原生支持并统一聚合 **DeepSeek Agent (`dsh`)**（支持 `.zstd` 压缩会话流实时解压解码）、**Reasonix**、**Hermes**、**Claude Code**、**Factory Droid**、**Antigravity (Gemini)**、**GitHub Copilot**、**Cursor**、**Windsurf**、**Kilo**、**Cline**、**Roo Code**、**OpenCode** 以及终端 Shell 历史。
- 🔌 **原生 Model Context Protocol (MCP) 服务**：内置零依赖标准 MCP Stdio Server（`contextgo mcp`），原生暴露 `tools/list` 与 `tools/call`，无缝支持 DeepSeek Agent、Claude Code、Cursor、Windsurf 及任意 MCP 客户端的原生 Function Calling 工具调用。
- ⚡ **亚秒级混合召回（Hybrid Recall）**：深度结合 SQLite FTS5 全文检索、BM25 词法排序与可选轻量级 Model2Vec 向量语义检索，配合倒数排序融合（RRF）与时效衰减机制，精准定位历史技术结论与会话细节。
- 🛡️ **零知识端到端加密同步**：借助用户私有 GitHub 仓库实现跨 Windows、macOS 与 Linux 的多机器同步；基于客户端 scrypt 口令派生与 AES-256-GCM 加密，云端绝不留存明文与密钥。
- 🎯 **智能上下文预热（Smart Context-First / SCF）**：提供一键配置命令（`contextgo setup`），自动在各 AI 工具的指令文件中注入前置召回规则，驱动 Agent 在回答历史架构或重构问题前先主动读取真实上下文。
- 💻 **跨平台守护进程与系统服务**：提供原生轻量级 Daemon 服务，无缝适配 Windows（Task Scheduler）、macOS（launchd）与 Linux（systemd user unit）自启。
- 🔍 **可视化持久记忆浏览器**：内置零依赖本地 Web 面板（`127.0.0.1:37677`），一览全平台技术决策、会话时间线与记忆沉淀。

---

## 快速上手

### 1. 安装

推荐使用 `pipx` 安装，使 ContextGO 运行在隔离的 Python 环境中：

```bash
# 标准安装（包含词法混合检索与核心引擎）
pipx install "contextgo[vector]"

# 包含跨机器加密同步功能
pipx install "contextgo[sync,vector]"
```

### 2. 终端集成

一键添加常用快捷别名（`cg` 快速召回、`cgs` 全文搜索、`cgse` 语义检索）：

```bash
eval "$(contextgo shell-init)"
```

可将上述命令添加到您的 `~/.zshrc`、`~/.bashrc` 或对应 Shell 配置文件中。

### 3. 校验健康状态与检测来源

```bash
# 检查运行时健康状态与索引统计
contextgo health

# 查看当前机器上已识别的 AI 编码工具与会话数量
contextgo sources
```

### 4. 检索与调阅历史上下文

```bash
# 快速混合召回（自动路由短查询或精准命中 Session ID）
contextgo q "当时是怎么解决路由器 DNS 延迟问题的？"

# 跨所有工具会话的全文检索
contextgo search "AdGuard Home" --limit 5

# 优先查阅长效记忆库的语义召回
contextgo semantic "关于同步引擎加密的架构决策" --limit 3
```

---

## 支持的 AI Agent 与 IDE 矩阵

ContextGO 能够自动扫描并持续同步以下本地开发环境，无需繁琐的人工配置：

| 平台类别 | 支持的工具与平台 | 自动探测与解析机制 |
|---|---|---|
| **自主编码 Agent** | **DeepSeek Agent (`dsh`)** | 原生解析 `.dsh/storages/session_projcache.json`、流式解码 `sessions/**/*.zstd` |
| | **Reasonix Agent** | 自动发现 `.reasonix/projects/*/sessions`、`events.jsonl`、`turns` 与高信噪比提纯 |
| | **Hermes Agent** | 解析 `~/.hermes/sessions/*.jsonl` 及 sidecar 元数据 |
| | **Claude Code** | 扫描 `~/.claude/projects/`、`~/.claude/transcripts/` |
| | **Factory Droid** | 扫描 `~/.factory/sessions/*.jsonl` |
| | **OpenClaw 与 Accio** | 扫描 `~/.openclaw/agents/`、`~/.accio/agents/` |
| **IDE 与辅助插件** | **Antigravity (Gemini)** | 索引 `~/.gemini/antigravity/brain/*/walkthrough.md` 及交互日志 |
| | **GitHub Copilot** | 索引 `~/.copilot/session-state/*/events.jsonl` |
| | **Cursor 与 Windsurf** | 提取 globalStorage 工作区与 vscdb SQLite 状态 |
| | **Kilo, Cline 与 Roo** | 解析 VS Code 全局存储的任务记录与会话流 |
| | **OpenCode 与 Zed** | 解析 `opencode.db`、`.config/zed/conversations/` |
| **终端与手工记忆** | **终端 Shell 历史** | 读取 `~/.zsh_history`、`~/.bash_history` |
| | **持久化记忆库** | `contextgo save` 手动记录、导出的 JSON observation 快照 |

---

## CLI 核心命令参考

```
usage: contextgo [-h] [--version] <command> ...
```

| 子命令 | 典型调用示例 | 说明 |
|---|---|---|
| `q` | `contextgo q "查询词"` | **快速智能召回**：自动路由 BM25S/FTS 检索或会话 ID 快速提取。 |
| `search` | `contextgo search "关键词" --limit 10` | **全文搜索**：在已索引的会话日志与工具调用中执行检索。 |
| `semantic` | `contextgo semantic "主题" --limit 5` | **语义检索**：优先检索持久记忆库，未命中时回退到会话历史。 |
| `save` | `contextgo save --title "..." --content "..."` | **保存持久记忆**：将关键技术结论或根因沉淀到本地存储。 |
| `sources` | `contextgo sources` | **适配器探测**：列出已识别的 AI 平台、会话文件数与适配路径。 |
| `health` | `contextgo health` | **健康检查**：以 JSON 格式输出数据库完整性与运行时状态。 |
| `serve` | `contextgo serve --port 37677` | **可视化面板**：在本地启动零依赖的 Memory Viewer Web UI。 |
| `sync` | `contextgo sync {init,push,pull,status,run}` | **加密同步**：管理基于 GitHub 私有仓库的多机器端到端加密同步。 |
| `setup` | `contextgo setup` | **一键规则注入**：为所有已安装的 AI 工具注入智能预热（SCF）规则。 |
| `unsetup` | `contextgo unsetup` | **卸载规则**：安全移除 ContextGO 注入的所有提示词规则。 |
| `daemon` | `contextgo daemon {start,stop,status,install}` | **守护服务管理**：控制后台自动索引与系统级自启服务。 |
| `export` | `contextgo export "" backup.json` | **安全导出**：自动脱敏 API Key 与敏感路径后导出记忆快照。 |
| `import` | `contextgo import backup.json` | **记忆导入**：将便携记忆快照导入到本地记忆库中。 |
| `smoke` | `contextgo smoke --sandbox` | **质量门禁**：在隔离沙箱环境中执行全链路冒烟测试。 |

---

## 隐私优先的跨机器加密同步

ContextGO 支持基于任意私有 GitHub 仓库的多机器零知识同步：

```bash
# 1. 在主开发机上初始化同步（例如 Windows 11）
contextgo sync init --repo 用户名/我的同步仓库 --device-id desktop-win11

# 2. 推送本地加密分片
contextgo sync push

# 3. 在另一台机器上拉取并合并（例如 macOS）
pipx install "contextgo[sync,vector]"
contextgo sync init --repo 用户名/我的同步仓库 --device-id macbook-m4
contextgo sync pull
```

### 安全机制

- **客户端 AES-256-GCM**：所有会话与记忆数据均在本地压缩后加密，云端仅存储密文分片。
- **本地口令派生（scrypt）**：加密密钥仅由本地口令和仓库 Salt 派生，口令绝不离开设备。
- **独立设备分片**：每台机器写入独立的加密分片文件（`shards/<device-id>.enc.json`），杜绝 Git 合并冲突。
- **脱敏前置**：在加密前自动剔除环境变量 Token、私密凭证与本地绝对文件路径。

---

## AI Agent 智能上下文预热 (SCF)

执行一键配置，让所有 AI 编码助手在回答前主动调阅历史记忆：

```bash
contextgo setup
```

该命令会自动向各工具的全局策略文件注入 **Smart Context-First (SCF)** 规则（例如 `~/.gemini/GEMINI.md`、`~/.reasonix/AGENTS.md`、`~/.dsh/AGENTS.md`、`~/.hermes/SOUL.md`、`~/.claude/CLAUDE.md`、`.github/copilot-instructions.md`、`.cursorrules`）。

### 触发与调用准则

| 场景 | Agent 动作 |
|---|---|
| 续做任务 / 状态恢复 (`接着做` / `continue`) | 执行 `contextgo semantic "<主题>" --limit 3` 快速对齐历史 |
| 不确定项目历史或过往设计决策 | 执行 `contextgo search "<关键词>" --limit 5` |
| 进行重大架构改动或底层重构前 | 先检索过往根因与架构决策，避免反复试错 |
| 确认重要技术根因或敲定架构方案 | 建议调用 `contextgo save --title "..."` 保存为永久记忆 |

---

## Daemon 与后台系统守护

支持将 ContextGO 作为系统原生服务运行，实现后台静默索引：

```bash
# 管理守护进程
contextgo daemon start
contextgo daemon status
contextgo daemon stop

# 安装系统级自启服务
contextgo daemon install
```

| 操作系统 | 对应的系统服务后端 |
|---|---|
| **macOS** | 原生用户级 `launchd` 服务（位于 `~/Library/LaunchAgents/`） |
| **Linux** | 原生 `systemd` 用户服务（位于 `~/.config/systemd/user/`） |
| **Windows** | 原生 Windows 任务计划程序（Task Scheduler）用户任务 |

---

## 开发者与测试验证

ContextGO 遵循严格的工程质量标准，核心测试覆盖率保持在 **86% 以上**：

```bash
# 克隆仓库
git clone https://github.com/dunova/ContextGO.git
cd ContextGO

# 使用 uv 同步依赖
uv sync --extra dev --extra sync --extra vector

# 运行代码规范与安全扫描
uv run ruff check src/contextgo tests
uv run ruff format --check src/contextgo tests
uv run mypy src/contextgo --ignore-missing-imports
uv run bandit -r src/contextgo -c pyproject.toml --quiet

# 运行完整单元测试与沙箱冒烟门禁
uv run pytest
uv run python -m contextgo smoke --sandbox
```

---

## 开源许可证

ContextGO 基于 [AGPL-3.0-only](LICENSE) 协议开源。

版权所有 © 2025-2026 [Dunova](https://github.com/dunova)。
