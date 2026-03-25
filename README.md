# Context Mesh Foundry

本地优先上下文基础设施，面向多 agent AI 编码团队的单体产品。
无 MCP、无 Docker、无分布式依赖，只有一个统一 CLI 和本地 runtime，帮助工程组在自己机器上完成调试、记忆、迁移和部署。

## 核心承诺

- **单体可控**：上下文采集、语义搜索、记忆存储、守护进程都由同一套 `contextmesh` 代码驱动，不再跳转多个桥接脚本。
- **本地优先**：默认路径 100% 在本地，远程同步默认关闭；部署目录、服务名、数据库都围绕单机运行优化。
- **无 MCP 依赖**：不需要 MCP 或其他云端服务即可完整运行，连接历史、终端和 agent 的唯一信任源是本地索引。
- **Benchmark 驱动**：自带 `benchmarks/` 验证真实热点，定期校准瓶颈，统计结果直接反馈到本地仪表盘。
- **Native 迁移路线**：在 Python monolith 上量化热点后，再逐步用 Rust/Go 取代，保持稳定性的同时提升速度。

## 商业定位与价值主张

Context Mesh Foundry 0.5.0 把本地上下文设施打磨成面向企业的单体产品：工程团队通过一套可复现的命令就能完成部署、验证、迁移与升级，所有操作始终在本地可控边界内。

- **确定性部署与运营**：统一的 `python3 scripts/context_cli.py` CLI（包含 `search`、`semantic`、`save`、`export`、`import`、`serve`、`maintain`、`health`、`smoke`、`native-scan`）联合 `bash scripts/unified_context_deploy.sh` 提供端到端流程，降低培训与交付成本。
- **本地治理与审计**：上下文数据、守护进程与 viewer 配置都落在 SQLite+本地目录，工程师只需运行 `python3 scripts/context_cli.py health`、`python3 scripts/context_cli.py smoke` 检查健康，所有验证命令可被审计并自动记录。
- **可度量迁移计划**：用 `python -m benchmarks --query <真实业务场景>` 先收集 latency/throughput，再用 `cargo run --release` / `go run` 与 `python3 scripts/context_cli.py native-scan --backend auto --threads 4` 的输出对比，形成可比绩效记录。
- **稳定演进不破坏体验**：Native 原型（`native/session_scan`、`native/session_scan_go`）只在 hot-path 替换中出现，CLI 参数、守护进程入口、验证命令始终保持一致，保障客户感知零差异。

## 产品形态

- `python3 scripts/context_cli.py`：统一 CLI（`search`、`semantic`、`save`、`export`、`import`、`serve`、`maintain`、`health`、`smoke`、`native-scan`）覆盖搜索、维护、守护进程验证与 Native 扫描，所有命令都可在任何支持 Python 3.11 的平台复现。
- `scripts/context_daemon.py`：canonical 守护进程入口，可由 `bash scripts/unified_context_deploy.sh` 注册成 `com.contextmesh.daemon`，daemon 与 viewer 均可通过 `context_cli.py health` 验证。
- `scripts/session_index.py` / `scripts/memory_index.py`：本地 SQLite 索引，直连 Codex/Claude/shell 历史，结果可用 `python3 scripts/context_cli.py search` 或 `semantic` 命令察看。
- `benchmarks/`：指令化 benchmark 目录帮助工程师在切换 Native 代码前验证 throughput 与 latency。
- `native/session_scan/`：Rust hot-path 原型，绑定 `context_cli.py native-scan --backend auto --threads 4` 入口。
- `native/session_scan_go/`：Go 版扫描原型，配合 `native-scan --backend go` 观察轻量化替代方案。

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
- 建议验证命令：`python3 scripts/context_cli.py health`，`python3 scripts/context_cli.py smoke`，`python3 scripts/context_cli.py native-scan --backend auto --threads 4`，必要时再配合 `cargo run --release` 或 `go run` 验证 Native 模块的性能。

## 安装矩阵

| 平台 | 先决条件 | 快速部署 | 建议验证命令 |
| --- | --- | --- | --- |
| Linux x86_64 / ARM64 | Python 3.11+、SQLite3、bash shell、可选 Rust/cargo 工具 | `git clone https://github.com/dunova/context-mesh-foundry.git && cd context-mesh-foundry && cp .env.example .env && bash scripts/unified_context_deploy.sh` | `python3 scripts/context_cli.py health` / `python3 scripts/context_cli.py smoke` / `python3 scripts/context_cli.py native-scan --backend auto --threads 4` |
| macOS (Intel / Apple Silicon) | 同上，确保 `/opt/homebrew/bin` 在 PATH，必要时 `brew install sqlite` | `git clone https://github.com/dunova/context-mesh-foundry.git && cd context-mesh-foundry && cp .env.example .env && bash scripts/unified_context_deploy.sh` | `python3 scripts/context_cli.py health` 与 `python3 scripts/context_cli.py smoke`、`python3 scripts/context_cli.py native-scan --backend auto --threads 4` |
| Windows (WSL2 / PowerShell) | WSL2 Ubuntu 22.04+ 与 Git Bash/Windows Terminal，启用 Linux 子系统 | 在 WSL 里 `git clone https://github.com/dunova/context-mesh-foundry.git && cd context-mesh-foundry && cp .env.example .env && bash scripts/unified_context_deploy.sh` | `python3 scripts/context_cli.py health` / `python3 scripts/context_cli.py native-scan --backend auto --threads 4` |

## Native 路线

1. 在 Python 单体中用 `python -m benchmarks --query <真实业务场景>` 量化 latency/throughput，数据写入 release notes 以建立迁移前 baseline。
2. 把瓶颈抽象成 `native/session_scan`（Rust）或 `native/session_scan_go`（Go）原型，保持 `python3 scripts/context_cli.py native-scan --backend <auto|rust|go>` 入口不变，为工程师提供一致的调用体验。
3. 每次 Native 替换先运行 `python3 scripts/context_cli.py native-scan --backend auto --threads 4` 复测，再用 `cargo run --release` / `go run` 校验性能，最后串联 `python3 scripts/context_cli.py health`、`python3 scripts/context_cli.py smoke` 与 `python3 scripts/context_cli.py native-scan --backend auto --threads 4` 确保守护进程、viewer 和扫描链路正常。
4. 发布前执行 `python3 -m benchmarks --iterations 1 --warmup 0 --query perf` 记录对比数据，并把验证命令与差异写入 `docs/RELEASE_NOTES_0.5.0.md` 与 `CHANGELOG.md`，让客户看到迁移前后指标与验证流程。

## FAQ

### 这是一个库、一个工具，还是一套本地服务？

三者兼备，但首先是一个本地产品交付套件：

- CLI：`context_cli.py`
- daemon：`context_daemon.py`
- viewer：`context_server.py`
- health/deploy：`context_healthcheck.sh` / `unified_context_deploy.sh`

可按需选用：作为命令行工具，或注册守护进程/healthcheck 做常驻基础设施。

### 为什么默认不启用远程同步？

因为我们优先保障：

- 最少外部依赖
- 最低 surprise
- 最稳定本地链路
- 最少 token / 网络开销

远程同步是可选增强，非默认主路径；先把本地体验打磨稳再逐步加装。

### Native 迁移路线会影响操作体验吗？

不会。任何热点替换都通过 `python3 scripts/context_cli.py native-scan` 入口触发，CLI 参数、守护进程名称与验证链路（`health`、`smoke`、`native-scan`）都不变。

### 如何在不同平台快速部署并确认状态？

以 `git clone https://github.com/dunova/context-mesh-foundry.git` 为起点，依赖 `bash scripts/unified_context_deploy.sh` 与 `python3 scripts/context_cli.py health` 完成主流程。详细依赖与差异请参阅上方安装矩阵；在 macOS/Windows 上先确认 Python 3.11 与 SQLite 可用，Linux 可直接在 shell 中运行相同步骤。

### 如何验证部署与 Native 替换后的状态？

每次部署或 Native 替换后依次运行：

1. `python3 scripts/context_cli.py health`
2. `python3 scripts/context_cli.py smoke`
3. `python3 scripts/context_cli.py native-scan --backend auto --threads 4`

必要时再对比 `cargo run --release` / `go run` 的输出，把 benchmark 结果与验证命令写入 `docs/RELEASE_NOTES_0.5.0.md` 与 `CHANGELOG.md` 供商业审计。

### 为什么不直接全部用 Rust/Go 重写？

因为最优路线是：

1. 先把 Python 主链收敛成稳定单体
2. 用 benchmark 找真实热点
3. 只把热点模块逐步替换成 Rust/Go

如此既能保持速度，又能兼顾稳定性与迁移成本。

## 版本与发布

- 当前版本：`0.5.0`，详见本地 [`VERSION`](./VERSION)。
- 发布纪要：[`CHANGELOG.md`](./CHANGELOG.md) 与 [`docs/RELEASE_NOTES_0.5.0.md`](./docs/RELEASE_NOTES_0.5.0.md)。
***
## English Snapshot

Context Mesh Foundry is a local-context monolith built for AI coding teams. No MCP, no Docker, fully self-hosted CLI and runtime. Start with the unified `contextmesh` CLI, benchmark real workloads with `benchmarks/`, and migrate hot paths into the `native/session_scan` prototype without touching the operator experience.

For detailed steps, refer to the same sections above.
