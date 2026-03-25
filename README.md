# Context Mesh Foundry

本地优先上下文基础设施，面向多 agent AI 编码团队的单体产品。
无 MCP、无 Docker、无分布式依赖，只有一个统一 CLI 和本地 runtime，帮助工程组在自己机器上完成调试、记忆、迁移和部署。

## 核心承诺

- **单体可控**：上下文采集、语义搜索、记忆存储、守护进程都由同一套 `contextmesh` 代码驱动，不再跳转多个桥接脚本。
- **本地优先**：默认路径 100% 在本地，远程同步默认关闭；部署目录、服务名、数据库都围绕单机运行优化。
- **无 MCP 依赖**：不需要 MCP 或其他云端服务即可完整运行，连接历史、终端和 agent 的唯一信任源是本地索引。
- **Benchmark 驱动**：自带 `benchmarks/` 验证真实热点，定期校准瓶颈，统计结果直接反馈到本地仪表盘。
- **Native 迁移路线**：在 Python monolith 上量化热点后，再逐步用 Rust/Go 取代，保持稳定性的同时提升速度。

## 商业定位

Context Mesh Foundry 0.5.0 面向需要可控本地上下文平台的工程团队，打造可商用的全栈单体体验：

- **确定性部署**：统一 CLI 与守护进程入口，避免多服务依赖，降低部署排查成本。
- **本地治理**：所有数据都在 SQLite + 本地目录，满足安全、合规与审计要求。
- **可度量升级**：Benchmark 驱动的迁移计划让工程师能量化性能收益，再决定何时用 Rust/Go 替换热点。
- **稳定演进**：Native 路线明确，从 `native/session_scan/`、`native/session_scan_go/` 原型切换时 CLI 留下不变的操作契约。

## 产品形态

- `python scripts/context_cli.py`：统一入口，提供 `search`、`semantic`、`save`、`export/import`、`serve`、`maintain`、`health` 等操作。
- `scripts/context_daemon.py`：canonical 守护进程，可由 `bash scripts/unified_context_deploy.sh` 注册为 `com.contextmesh.daemon`。
- `scripts/session_index.py` / `scripts/memory_index.py`：本地 SQLite 索引，直连 Codex/Claude/shell 历史，无同步延迟。
- `benchmarks/`：精确定位热路径，量化本地运行速度，为 Rust/Go 替换提供数据上下文。
- `native/session_scan/`：首个 Rust hot-path 原型，示例如何逐步迁移关键子系统。
- `native/session_scan_go/`：Go 版扫描原型，用于评估更轻的一体化二进制路径。

## 绩效与本地迁移路线

1. 在 Python 单体中保持业务稳定，确保部署脚本只需一条命令安装本地 runtime。
2. 利用 `python -m benchmarks` 对话串、存储、语义检索等真实场景打桩，生成可复现结果。
3. 标定瓶颈后，针对性将数据密集的功能抽象成 `native/session_scan` 等模块，保持单体 shell 无感知。
4. 每次 native 迁移都保持 CLI 不变，并通过 `cargo run --release`、`benchmarks` 复测，确保性能优于旧路径。

## 入门快线

```bash
git clone https://github.com/dunova/context-mesh-foundry.git
cd context-mesh-foundry
cp .env.example .env
bash scripts/unified_context_deploy.sh
python3 scripts/context_cli.py health
```

### 核心命令

```
python3 scripts/context_cli.py search "auth root cause" --limit 10 --literal
python3 scripts/context_cli.py semantic "数据库 schema 决策" --limit 5
python3 scripts/context_cli.py save --title "Auth fix" --content "..." --tags auth,bug
python3 scripts/context_cli.py export "" /tmp/contextmesh-export.json --limit 1000
python3 scripts/context_cli.py import /tmp/contextmesh-export.json
python3 scripts/context_cli.py serve --host 127.0.0.1 --port 37677
python3 scripts/context_cli.py maintain --dry-run
python3 scripts/context_cli.py health
python3 scripts/context_cli.py native-scan --backend auto --threads 4
python3 scripts/context_cli.py smoke
```

### 安装态烟测

```bash
python3 scripts/smoke_installed_runtime.py
# 或直接对当前工作副本运行
python3 scripts/context_cli.py smoke
```

## 部署与运维

- 默认安装目录：`~/.local/share/context-mesh-foundry`。
- 本地服务：`com.contextmesh.daemon`、`com.contextmesh.healthcheck`。
- `CONTEXT_MESH_*` 系列变量统一配置：`STORAGE_ROOT`、`REMOTE_URL`、`ENABLE_REMOTE_SYNC`、`VIEWER_HOST`、`VIEWER_PORT`、`SESSION_INDEX_DB_PATH`。
 - 旧桥接（`recall-lite`、`openviking`、`aline`）可清理，部署流程仅需 `bash scripts/unified_context_deploy.sh`。
 - health 验证：`python3 scripts/context_cli.py health`、`python3 scripts/context_cli.py smoke`、`python3 scripts/context_cli.py native-scan --backend auto --threads 4`。

## 安装矩阵

| 平台 | 先决条件 | 快速部署 | 说明 |
| --- | --- | --- | --- |
| Linux x86_64 / ARM64 | Python 3.11+、SQLite3、本地 shell、可选 Rust 工具链 | `git clone https://github.com/dunova/context-mesh-foundry.git && cd context-mesh-foundry && cp .env.example .env && bash scripts/unified_context_deploy.sh`，再用 `python3 scripts/context_cli.py health` 验证 | Rust/cargo 仅在构建 `native/session_scan` 原型时必须，其他模块只要 Python 即可运行。 |
| macOS (Intel / Apple Silicon) | 同上，确保 `/opt/homebrew/bin` 在 PATH 中 | `git clone https://github.com/dunova/context-mesh-foundry.git && cd context-mesh-foundry && cp .env.example .env && bash scripts/unified_context_deploy.sh`，再用 `python3 scripts/context_cli.py smoke` 复测 | `brew install sqlite` 仅在缺失时使用；`bash` 与 `cargo` 同样可用。 |
| Windows (WSL2 / PowerShell) | WSL 2 (Ubuntu 22.04+) / Git Bash + Windows Terminal，启用 Windows Subsystem for Linux | `git clone https://github.com/dunova/context-mesh-foundry.git` 后在 WSL 里 `cp .env.example .env && bash scripts/unified_context_deploy.sh`，再用 `python3 scripts/context_cli.py health` 检查 | 建议在 WSL 环境中运行，避免混合文件权限。WSL 内可用 `rustup` 安装 native 依赖。 |

## Native 路线

1. 在 Python 单体内用 `python -m benchmarks --query <真实业务场景>` 按主权路径收集 latency/throughput 数据。
2. 识别 CPU、IO 或内存重度热点后，把路径抽象成 `native/session_scan`（Rust）或 `native/session_scan_go`（Go）原型，复用 `context_cli.py native-scan` 入口。
3. 每次 Native 替换都保持相同 CLI 参数，先用 `python3 scripts/context_cli.py native-scan --backend auto --threads 4` 复测，再用 `cargo run --release` 或 `go run` 校验性能。
4. 发布前用 `python3 -m benchmarks --iterations 1 --warmup 0 --query perf` 记录对比数据，把结果写入 release notes 目录。

## FAQ

### 这是一个库、一个工具，还是一套本地服务？

三者都是，但对使用者来说它首先是一套本地产品：

- CLI：`context_cli.py`
- daemon：`context_daemon.py`
- viewer：`context_server.py`
- health/deploy：`context_healthcheck.sh` / `unified_context_deploy.sh`

你可以只把它当命令行工具用，也可以把它部署成常驻本地上下文基础设施。

### 为什么默认不启用远程同步？

因为默认目标是：

- 最少依赖
- 最低 surprise
- 最稳定本地链路
- 最低 token / 网络开销

远程同步是可选增强，不是默认主路径。

### 为什么不直接全部用 Rust/Go 重写？

因为当前最优路线是：

1. 先把 Python 主链收敛成稳定单体
2. 用 benchmark 找真实热点
3. 只把热点模块逐步替换成 Rust/Go

这样能同时兼顾速度、稳定性和迁移成本。

### 如何在不同平台选择安装流程？

参考上面 `安装矩阵` 表格，所有平台都可以从 `git clone https://github.com/dunova/context-mesh-foundry.git` 开始，依赖同一套 `bash scripts/unified_context_deploy.sh` 和 `python3 scripts/context_cli.py health` 验证。Mac/Windows 需要先确认 Python 3.11 与 SQLite 可用，Linux 则额外可以直接在 shell 里按步骤运行脚本。

### Native 迁移路线会影响操作体验吗？

不会。每次用 `native/session_scan` 或 `native/session_scan_go` 替换热点时，仍然通过 `python3 scripts/context_cli.py native-scan` 触发，CLI 参数与守护进程入口一致。工程师只要在 `benchmarks/` 跑一次对比，确认 `cargo run --release` 与 `go run` 输出与 `python -m benchmarks` 的 latency 信息相当，就可以安全切换。

## 版本与发布

- 当前版本：`0.5.0`，详见本地 [`VERSION`](./VERSION)。
- 发布纪要：[`CHANGELOG.md`](./CHANGELOG.md) 与 [`docs/RELEASE_NOTES_0.5.0.md`](./docs/RELEASE_NOTES_0.5.0.md)。
***
## English Snapshot

Context Mesh Foundry is a local-context monolith built for AI coding teams. No MCP, no Docker, fully self-hosted CLI and runtime. Start with the unified `contextmesh` CLI, benchmark real workloads with `benchmarks/`, and migrate hot paths into the `native/session_scan` prototype without touching the operator experience.

For detailed steps, refer to the same sections above.
