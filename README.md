# ContextGO

[![GitHub stars](https://img.shields.io/github/stars/dunova/ContextGO?style=flat)](https://github.com/dunova/ContextGO/stargazers)
[![Verify](https://github.com/dunova/ContextGO/actions/workflows/verify.yml/badge.svg)](https://github.com/dunova/ContextGO/actions/workflows/verify.yml)
[![Release](https://img.shields.io/github/v/release/dunova/ContextGO)](https://github.com/dunova/ContextGO/releases)
[![License](https://img.shields.io/github/license/dunova/ContextGO)](https://github.com/dunova/ContextGO/blob/main/LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/dunova/ContextGO)](https://github.com/dunova/ContextGO/commits/main)
![Local First](https://img.shields.io/badge/local--first-yes-1d4ed8)
![MCP Free](https://img.shields.io/badge/MCP-free-111827)

在本地把多 agent 的上下文体验变得可控、透明、可回滚。  
ContextGO 是一个面向多 agent AI 编码团队的本地优先上下文运行时：统一 CLI、精确检索、记忆管理、viewer、smoke 验证与 Native 热路径，全程默认无 MCP、无 Docker、无向量云依赖。

ContextGO is a local-first context runtime for multi-agent engineering teams.  
It unifies search, memory, viewer, smoke validation, and native hot paths behind one CLI, without requiring MCP, Docker, or cloud vector infrastructure by default.

如果你也在做 Codex / Claude / shell 协作，而且你需要一套本地优先、可回滚、可交付的上下文底座，先点个 `star`，等你真正要接这条链时能直接找回它。

## 一句话价值

当团队开始同时使用 Codex、Claude、shell、脚本和本地记忆文件时，真正缺的不是再多一层编排，而是一个可信、可查、可测、可交付的本地上下文底座。

## 为什么会被 star

- 不是 demo：它自带 `health / smoke / benchmark / installed-runtime` 验证闭环。
- 不是桥接拼装：它默认就是一个单体产品，不依赖 MCP 壳层存活。
- 不是云依赖产品：默认无向量云、无 Docker、无远程服务前置条件。
- 不是一次性重写：Python 主链稳定交付，Rust/Go 只替换热点路径。

## 信任块

- 默认运行链路：`local-first / MCP-free / Docker-free`
- 当前高分基线：`autoresearch = 99.0`
- 当前关键体积指标：
  - `health_bytes = 386`
  - `smoke_bytes = 346`
  - `search_bytes = 1417`
  - `native_total_bytes = 4382`
- 当前最佳轮次快照见：
  - [artifacts/autoresearch/contextgo_autoresearch_best.json](/Volumes/AI/GitHub/context-mesh-foundry/artifacts/autoresearch/contextgo_autoresearch_best.json)

## 快速判断它适不适合你

适合：

- 你在做多 agent AI 编码团队协作
- 你希望上下文、记忆、检索都留在本地
- 你需要一套可交付、可审计、可回滚的内部工具底座
- 你想提速，但不想把现有工作流全盘推翻

不适合：

- 你只想要一个简单聊天记录查看器
- 你优先接受云向量服务和中心化编排
- 你没有本地部署和本地验证的要求

## 为什么值得关注

- 本地优先：默认数据只落在本机 `SQLite + ~/.contextgo`。
- 多 agent 友好：把 Codex、Claude、shell、记忆文件统一到一条上下文链。
- 低 token：优先精确检索、局部 snippet、结构化回退，不先上重型语义层。
- 可商用交付：自带部署脚本、healthcheck、smoke、benchmark、release 文档。
- 渐进提速：先稳定 Python 主链，再用 Rust/Go 只替换热点，不破坏用户命令。

## 典型场景

- 多 agent 调试接力：上一个终端没讲清的上下文，下一终端直接搜回来。
- 私有团队记忆层：把关键信息沉淀在本地，而不是散在聊天窗口里。
- 交付前质量门：用 `smoke + health + benchmark` 验证安装态与工作副本一致。
- 渐进性能升级：不重写整套产品，只把最热的检索扫描链路逐步挪到 Rust/Go。

## 为什么不是另一个 MCP / 云记忆工具

| 对比项 | ContextGO | 典型 MCP / 云记忆方案 |
|---|---|---|
| 默认依赖 | 本地文件系统 + SQLite | 外部服务 / 桥接层 / 远程 API |
| 数据边界 | 默认留在本机 | 常常要把上下文送出本地 |
| 运维复杂度 | 单体部署 + 本地验证 | 多进程、多服务、多连接点 |
| 故障定位 | `health + smoke + benchmark` 一条链 | 常分散在多层桥接与外部状态 |
| 提速路径 | 渐进式 Rust/Go 热点替换 | 常常要改接口或改运行方式 |
| 目标用户 | 真正在交付内部工具的团队 | 更偏实验集成与演示编排 |

## 架构树

```text
ContextGO/
├── docs/                      # 架构、发布、故障排查、商业交付文档
├── scripts/                   # 单体主链：CLI / daemon / server / smoke / health / deploy
│   ├── context_cli.py         # 唯一对外入口：search / semantic / save / serve / smoke
│   ├── context_daemon.py      # 会话采集、脱敏、写盘
│   ├── session_index.py       # 会话索引与检索排序
│   ├── memory_index.py        # 记忆 / observation 索引
│   ├── context_server.py      # viewer 服务入口
│   ├── context_maintenance.py # 清理与维护
│   ├── context_smoke.py       # 工作副本 smoke
│   ├── context_healthcheck.sh # 安装态 / 本地健康检查
│   └── unified_context_deploy.sh
├── native/
│   ├── session_scan/          # Rust 热路径
│   └── session_scan_go/       # Go 热路径
├── benchmarks/                # Python / native-wrapper 基准
├── integrations/gsd/          # 与 GSD / gstack 工作流衔接
├── artifacts/                 # autoresearch 结果、测试集、QA 报告
├── templates/                 # launchd / systemd-user 模板
├── examples/                  # 配置示例
└── patches/                   # 兼容补丁说明
```

更详细的说明见 [docs/ARCHITECTURE.md](/Volumes/AI/GitHub/context-mesh-foundry/docs/ARCHITECTURE.md)。

## 核心链路

```text
Capture -> Index -> Search -> Save/Recall -> Viewer -> Smoke/Health -> Native Hot Paths
```

对应关系：

- `context_daemon.py`：采集与脱敏
- `session_index.py` / `memory_index.py`：索引与检索
- `context_cli.py`：统一命令入口
- `context_server.py`：viewer API
- `context_smoke.py` / `context_healthcheck.sh`：质量门
- `native/session_scan*`：热点扫描提速

## 10 分钟上手

```bash
git clone https://github.com/dunova/ContextGO.git
cd ContextGO
bash scripts/unified_context_deploy.sh
python3 scripts/context_cli.py health
python3 scripts/context_cli.py smoke
```

如果你只想先看“它到底能不能跑”，直接执行：

```bash
python3 scripts/context_cli.py health
python3 scripts/context_cli.py smoke
```

## 命令入口

```bash
python3 scripts/context_cli.py search "auth root cause" --limit 10 --literal
python3 scripts/context_cli.py semantic "数据库 schema 决策" --limit 5
python3 scripts/context_cli.py save --title "Auth fix" --content "..." --tags auth,bug
python3 scripts/context_cli.py export "" /tmp/contextgo-export.json --limit 1000
python3 scripts/context_cli.py import /tmp/contextgo-export.json
python3 scripts/context_cli.py serve --host 127.0.0.1 --port 37677
python3 scripts/context_cli.py maintain --dry-run
python3 scripts/context_cli.py health
python3 scripts/context_cli.py smoke
python3 scripts/context_cli.py native-scan --backend auto --threads 4
```

## 默认运行时

- 安装目录：`~/.local/share/contextgo`
- 数据目录：`~/.contextgo`
- 服务标签：`com.contextgo.daemon` / `com.contextgo.healthcheck`
- 默认远程同步：关闭
- 默认信任边界：本机文件系统

## 为什么它比“再加一个编排层”更靠谱

- 不把上下文拆成多个桥接项目，减少故障面。
- 不先依赖云向量库，先把本地命中率、可追溯性和稳定性做好。
- 所有优化都要过：
  - `health`
  - `smoke`
  - `e2e_quality_gate`
  - `benchmarks`
- Native 提速不是另起炉灶，而是挂在同一 CLI 和同一验证链路上。

## 验证矩阵

```bash
bash -n scripts/*.sh
python3 -m py_compile scripts/*.py benchmarks/*.py
python3 -m pytest scripts/test_context_cli.py scripts/test_context_core.py scripts/test_context_native.py scripts/test_context_smoke.py scripts/test_session_index.py
python3 scripts/e2e_quality_gate.py
python3 scripts/context_cli.py health
python3 scripts/context_cli.py smoke
python3 scripts/smoke_installed_runtime.py
cd native/session_scan_go && go test ./...
cd native/session_scan && CARGO_INCREMENTAL=0 cargo test
python3 -m benchmarks --mode both --iterations 1 --warmup 0 --query benchmark --format text
```

## 性能路线

当前不是“全面重写”，而是“热点替换”：

1. 先把 Python 主链做到最稳。
2. 用 benchmark 找出瓶颈。
3. 只把热点挪到 Rust / Go。
4. 用户侧仍然只面对同一套 `context_cli.py`。

## 商业化交付视角

ContextGO 适合这些团队：

- 多 agent AI 编码团队
- 私有研发知识库团队
- 对数据边界敏感的企业内网环境
- 想逐步提速，但不能承受“重写全栈”的团队

它强调的不是“更大编排”，而是：

- 更低 surprise
- 更低 token
- 更低依赖
- 更高可审计性

## 发布与增长素材

- 架构说明：[docs/ARCHITECTURE.md](/Volumes/AI/GitHub/context-mesh-foundry/docs/ARCHITECTURE.md)
- 发布说明：[docs/RELEASE_NOTES_0.6.1.md](/Volumes/AI/GitHub/context-mesh-foundry/docs/RELEASE_NOTES_0.6.1.md)
- 发布文案：[docs/LAUNCH_COPY.md](/Volumes/AI/GitHub/context-mesh-foundry/docs/LAUNCH_COPY.md)
- 故障排查：[docs/TROUBLESHOOTING.md](/Volumes/AI/GitHub/context-mesh-foundry/docs/TROUBLESHOOTING.md)

## English TL;DR

### What it is

ContextGO is a local-first context and memory runtime for AI coding teams.

### Why teams use it

- One CLI for search, memory, viewer, health, smoke, and native hot paths
- Local-only by default
- No MCP required
- No Docker required
- No cloud vector dependency required

### What makes it different

- It optimizes for operational trust, not demo complexity
- It keeps Python as the stable control plane
- It upgrades hot paths with Rust/Go without changing operator workflows
- It ships with validation, not just features

### Best fit

- Claude Code / Codex style agent teams
- private engineering memory layers
- local-first internal developer tooling
- incremental performance migration paths

## FAQ

### 它是库还是产品？

首先是产品，其次才是代码仓库。

### 它是否依赖 MCP？

默认不依赖。当前主链是 MCP-free。

### 它是否必须接远程服务？

不需要。默认完全本地。

### 它是否必须接向量数据库或向量 API？

默认不需要。只有当你要做跨语义、低关键词重合、超长文本弱召回时，才值得评估可选向量层。

### 为什么现在仓库里应该主要只看到 ContextGO？

因为当前主链目标就是彻底收敛为一个统一产品，而不是多个上游项目的拼接壳层。

## Star 指南

如果 ContextGO 对你的团队有帮助，欢迎：

- star 仓库
- 用它跑你自己的本地 AI 上下文底座
- 提 issue / PR / benchmark 数据
- 把你们的真实使用场景和性能数据反馈回来

## 版本

- 当前版本：`0.6.1`
- 发布说明：[docs/RELEASE_NOTES_0.6.1.md](/Volumes/AI/GitHub/context-mesh-foundry/docs/RELEASE_NOTES_0.6.1.md)
- 历史变更：[CHANGELOG.md](/Volumes/AI/GitHub/context-mesh-foundry/CHANGELOG.md)
