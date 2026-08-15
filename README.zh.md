<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/media/logo-dark.svg">
    <img src="docs/media/logo.svg" alt="ContextGO" width="360">
  </picture>
</p>

<p align="center">
  <strong>面向 AI 编码 Agent 的本地优先上下文与记忆运行时。</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/v/contextgo?color=2563eb&style=flat" alt="PyPI"></a>
  <a href="https://pypi.org/project/contextgo/"><img src="https://img.shields.io/pypi/pyversions/contextgo?color=3776ab&style=flat" alt="Python"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/verify.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/verify.yml/badge.svg" alt="Verify"></a>
  <a href="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml"><img src="https://github.com/dunova/ContextGO/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://github.com/dunova/ContextGO/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-6d28d9?style=flat" alt="License"></a>
</p>

<p align="center">
  <a href="README.md">English</a> | <a href="#快速上手">快速上手</a> | <a href="#索引哪些来源">来源</a> | <a href="#隐私优先的-github-加密同步">加密同步</a> | <a href="#运维与验证">运维</a>
</p>

---

ContextGO 让 AI 编码 Agent 拥有跨工具、跨项目、跨会话的本地持久记忆。它会把 Codex、Claude Code、Gemini/Antigravity、OpenCode、OpenClaw、Accio、GitHub Copilot、Reasonix、DeepSeek Agent (dsh)、Cursor/Windsurf 类存储、Kilo/Cline/Roo、Hermes、Shell 历史以及其他本地来源统一索引到 SQLite 运行时里。默认路径是本地优先：不需要 Docker，不需要 MCP Broker，不需要外部向量数据库，也不会自动上传到云端。

`0.14.0` 深度增强了多 Agent 协同：新增 DeepSeek Agent 原生 `.zstd` 流式会话解压解析、Reasonix 多工作区适配器与高信噪比事件抽取、Hermes 跨目录同步，以及面向多 Agent 会话的混合检索排序调优。

## 快速上手

建议使用 `pipx` 安装，让 ContextGO 与系统 Python 隔离。

```bash
pipx install "contextgo[vector]"
eval "$(contextgo shell-init)"
contextgo health
contextgo sources
contextgo search "database migration" --limit 5
```

如果要启用 GitHub 加密同步，安装 sync extra：

```bash
pipx install "contextgo[sync,vector]"
```

本地源码开发：

```bash
git clone https://github.com/dunova/ContextGO.git
cd ContextGO
uv sync --extra dev --extra sync --extra vector
uv run python -m contextgo health
uv run pytest
```

## 平台支持

| 能力 | Windows | macOS | Linux |
|---|---:|---:|---:|
| CLI、health、search、export/import | 支持 | 支持 | 支持 |
| SQLite 索引与 WAL 运行时 | 支持 | 支持 | 支持 |
| GitHub 加密同步 | 支持 | 支持 | 支持 |
| daemon status/start/stop | 支持 | 支持 | 支持 |
| 用户级服务定义 | Task Scheduler | launchd | systemd user |
| 原生应用数据发现 | `%APPDATA%`、`%LOCALAPPDATA%` | `~/Library/...` | XDG 与 home 路径 |
| Shell 集成 | Git Bash / POSIX shell | bash/zsh/fish | bash/zsh/fish |

升级时，ContextGO 继续兼容历史 `~/.contextgo` 数据目录。只有在你明确设置 `CONTEXTGO_PLATFORM_STORAGE=1` 时，才会切换到系统原生目录，例如 `%LOCALAPPDATA%/ContextGO`、`~/Library/Application Support/ContextGO` 或 `~/.local/share/contextgo`。

## 索引哪些来源

ContextGO 会自动发现受支持的本地来源。仅做本地索引不需要任何 API key。

| 来源类型 | 示例 |
|---|---|
| 编码 Agent | Codex、Claude Code、OpenCode、OpenClaw、Accio、GitHub Copilot、Gemini/Antigravity |
| 编辑器与 IDE | Cursor、Windsurf 类存储、Continue 类存储、Kilo、Cline、Roo、Zed |
| 本地 Agent 运行时 | Hermes、Factory/Droid、其他 JSONL 会话目录 |
| 终端历史 | bash 与 zsh 历史 |
| 手动保存记忆 | `contextgo save`、便携导出、导入的 observation payload |

查看当前机器探测到的来源：

```bash
contextgo sources
```

## 核心命令

| 命令 | 用途 |
|---|---|
| `contextgo q "query"` | 快速召回，自动路由到会话 ID 查找或搜索。 |
| `contextgo search "query" --limit 10` | 对已索引会话做全文搜索。 |
| `contextgo semantic "query" --limit 5` | 先查本地记忆，再回退到会话历史。 |
| `contextgo save --title "Decision" --content "..."` | 保存一条持久本地记忆。 |
| `contextgo export "" snapshot.json --limit 1000` | 导出已脱敏的 observation。 |
| `contextgo import snapshot.json` | 导入便携 observation 快照。 |
| `contextgo vector-sync` | 构建或刷新可选向量索引。 |
| `contextgo vector-status` | 查看向量索引状态。 |
| `contextgo health` | 以 JSON 输出运行时健康状态。 |
| `contextgo smoke --sandbox` | 在沙箱中运行本地 smoke gate。 |
| `contextgo maintain --enqueue-missing` | 将缺失会话加入索引队列。 |
| `contextgo serve` | 在 `127.0.0.1` 启动本地 Viewer API。 |

## 隐私优先的 GitHub 加密同步

同步默认关闭。安装 ContextGO 或执行普通搜索时，不会静默上传本地历史。

```bash
contextgo sync init --repo OWNER/REPO --device-id work-laptop
contextgo sync status
contextgo sync run
```

另一台机器上：

```bash
pipx install "contextgo[sync,vector]"
contextgo sync init --repo OWNER/REPO --device-id home-desktop
contextgo sync pull
contextgo sync status --remote
```

同步协议遵循保守的隐私边界。

| 规则 | 行为 |
|---|---|
| 显式开启 | 执行 `sync init` 前不会远程读取或写入。 |
| 端到端加密 | payload 先压缩，再用 AES-256-GCM 加密。 |
| 口令派生密钥 | 同步口令只留在本机，通过 scrypt 派生密钥。 |
| 公开 manifest | 远端 manifest 只保存格式元数据和 KDF salt，不含密钥。 |
| 每设备分片 | 每台设备写自己的加密 shard，降低写冲突。 |
| 上传前脱敏 | token 和本机绝对路径在加密前被移除。 |
| 冲突 fail-closed | 远端 manifest salt 不一致时拒绝覆盖。 |
| 本地优先 daemon | 网络失败只退避，不阻塞本地索引和搜索。 |

关闭自动同步但保留本地数据：

```bash
contextgo sync disable
```

## Daemon 与系统服务

daemon 用于后台索引和可选周期加密同步。

```bash
contextgo daemon status
contextgo daemon start
contextgo daemon stop
```

安装或移除当前用户的服务定义：

```bash
contextgo daemon install
contextgo daemon uninstall
```

服务安装会映射到 Windows Task Scheduler、macOS launchd 或 Linux systemd user service。卸载服务只移除服务定义，不删除 ContextGO 数据。

## 混合搜索

没有向量依赖时，ContextGO 依然可以工作。安装 `vector` extra 后，会启用 model2vec 嵌入、BM25 关键词评分和 RRF 融合。

```bash
pipx inject contextgo "contextgo[vector]"
export CONTEXTGO_EXPERIMENTAL_SEARCH_BACKEND=vector
contextgo vector-sync
contextgo q "why did the auth migration change?"
```

缺少向量依赖时，会自动降级为 SQLite FTS 和 literal matching。测试里也会强制使用 fake vector model，避免 CI 意外下载远程模型。

## 配置

大多数用户不需要配置。环境变量主要用于部署、测试和隔离。

| 变量 | 默认值 | 用途 |
|---|---|---|
| `CONTEXTGO_STORAGE_ROOT` | `~/.contextgo` | 兼容旧版本的索引与日志根目录。 |
| `CONTEXTGO_PLATFORM_STORAGE` | 未设置 | 设为 `1` 后使用系统原生 data/config/cache 目录。 |
| `CONTEXTGO_HOME` | 当前用户 home | 测试和沙箱中覆盖 home 目录解析。 |
| `CONTEXTGO_SESSION_INDEX_DB_PATH` | `$ROOT/index/session_index.db` | 会话索引数据库。 |
| `MEMORY_INDEX_DB_PATH` | `$ROOT/index/memory_index.db` | 记忆索引数据库。 |
| `CONTEXTGO_EXPERIMENTAL_SEARCH_BACKEND` | 未设置 | 设为 `vector` 启用混合搜索。 |
| `CONTEXTGO_VIEWER_HOST` | `127.0.0.1` | Viewer 绑定地址。 |
| `CONTEXTGO_VIEWER_PORT` | `37677` | Viewer 端口。 |
| `CONTEXTGO_GITHUB_TOKEN` / `GITHUB_TOKEN` | 未设置 | 同步使用的可选 token；也支持 `gh auth token`。 |

完整配置见 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 面向 AI Agent

ContextGO 的目标是让 Agent 在回答历史相关问题前，先读取真实项目记忆，而不是凭印象猜测。

```bash
contextgo setup
contextgo health
contextgo semantic "what did we decide about sync encryption?" --limit 3
```

建议 Agent 行为：

| 场景 | 动作 |
|---|---|
| 继续旧任务 | 执行 `contextgo semantic "topic" --limit 3`，再简要总结。 |
| 不确定项目历史 | 执行 `contextgo search "keyword" --limit 5`。 |
| 做架构决策 | 改设计前先搜索历史决策。 |
| 解决了持久根因 | 建议用 `contextgo save` 保存短记忆。 |

完整 Agent 入门文件见 [AGENTS.md](AGENTS.md)。

## 运维与验证

`0.13.0` 发布前在 Windows 本机通过的门禁为：`1483 passed`、`8 skipped`、覆盖率 `86.28%`。仓库 CI 覆盖 Ubuntu、macOS、Windows、Python 3.10 到 3.13、Go、Rust、lint、format、Bandit、E2E、smoke 和 wheel 安装验证。

常用本地命令：

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

## 仓库结构

| 路径 | 作用 |
|---|---|
| `src/contextgo/context_cli.py` | CLI 入口和子命令。 |
| `src/contextgo/context_runtime.py` | 跨平台路径、原子写入、PID 文件和服务定义。 |
| `src/contextgo/context_sync.py` | GitHub 加密同步协议和客户端。 |
| `src/contextgo/context_daemon.py` | 后台采集、本地优先同步调度和 daemon 主循环。 |
| `src/contextgo/source_adapters.py` | 各工具本地存储发现与文本抽取。 |
| `src/contextgo/session_index.py` | 会话 SQLite 索引、搜索、排序和 FTS fallback。 |
| `src/contextgo/memory_index.py` | 持久记忆索引、导出/导入、脱敏和路径清理。 |
| `src/contextgo/vector_index.py` | 可选向量索引和混合搜索。 |
| `native/session_scan/` | Rust 热路径扫描器。 |
| `native/session_scan_go/` | Go 并行扫描器。 |
| `.github/workflows/verify.yml` | 完整 CI 验证流水线。 |

## 安全模型

ContextGO 默认本地优先。远程同步、Viewer 非回环暴露等高风险能力都必须显式启用。导出和同步会在数据离开本机运行时前清理已知 secret 模式和绝对用户路径。GitHub 同步只存加密 payload；GitHub token 和同步口令不会写入导出快照或远端 shard。

安全问题请按 [.github/SECURITY.md](.github/SECURITY.md) 披露。

## 文档

| 主题 | 链接 |
|---|---|
| 配置 | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| 架构 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| API | [docs/API.md](docs/API.md) |
| 迁移 | [docs/MIGRATION.md](docs/MIGRATION.md) |
| 故障排查 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Shell 补全 | [docs/SHELL_COMPLETION.md](docs/SHELL_COMPLETION.md) |
| 变更日志 | [.github/CHANGELOG.md](.github/CHANGELOG.md) |

## 许可证

ContextGO 使用 [AGPL-3.0-only](LICENSE) 许可证。

Copyright 2025-2026 [Dunova](https://github.com/dunova).
