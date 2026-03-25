# ContextGO

ContextGO 是一个面向多 agent AI 编码团队的本地优先上下文运行时。
它把上下文采集、会话索引、记忆存储、viewer、运维验证和 Native 热点迁移收进一个单体产品里：无 MCP、无 Docker、默认无远程依赖。

## 产品定位

- 本地单体：默认所有核心能力都在本机完成，数据留在本地 SQLite 与本地目录。
- 统一入口：统一通过 `python3 scripts/context_cli.py` 驱动搜索、记忆、导入导出、viewer、运维与 smoke。
- 低 token：优先精确检索、局部 snippet、结构化回退，不依赖向量云调用。
- 可商用：带部署脚本、healthcheck、smoke、benchmark、release 文档，适合直接交付团队使用。
- 渐进提速：Python 主链先稳定交付，Rust/Go 只替换热点路径，不破坏 CLI 体验。

## 为什么存在

多数 AI 编码团队真正缺的不是再加一个编排层，而是一个可控、可审计、可回滚的本地上下文底座。

ContextGO 解决的是四个直接问题：

- 会话和历史分散在 Codex、Claude、shell、本地记忆文件里，难统一搜索。
- 一旦把上下文能力拆成多个桥接项目，维护成本和故障面会迅速上升。
- 为了“更智能”而引入远程依赖，常常会增加 token、延迟和不确定性。
- 热点模块需要提速，但团队不能接受每次提速都改命令、改部署、改运维路径。

## 核心能力

- `search`：统一搜 Codex、Claude、shell 与本地索引。
- `semantic`：先查本地记忆，再回退历史内容。
- `save` / `export` / `import`：沉淀与迁移团队记忆。
- `serve`：启动本地 viewer。
- `maintain`：执行维护与修复。
- `health`：检查主链健康。
- `smoke`：跑完整工作副本 smoke。
- `native-scan`：验证 Rust/Go 热路径原型。

## 10 分钟上线

```bash
git clone https://github.com/dunova/context-mesh-foundry.git
cd context-mesh-foundry
cp .env.example .env
bash scripts/unified_context_deploy.sh
python3 scripts/context_cli.py health
python3 scripts/context_cli.py smoke
```

当前品牌名已切到 `ContextGO`，但 GitHub 仓库 slug 如未在 GitHub 后台重命名，仍会暂时保持 `context-mesh-foundry`。

## 统一命令

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

## 部署与运行时

- 默认安装目录：`~/.local/share/context-mesh-foundry`
- 默认数据目录：`~/.unified_context_data`
- 本地服务标签：`com.contextmesh.daemon`、`com.contextmesh.healthcheck`
- 默认远程同步：关闭
- 默认信任边界：本机文件系统

这里刻意保留了旧目录名与服务标签，以确保现有安装态可平滑升级、可回滚。

## 验证矩阵

发布前推荐至少执行：

```bash
bash -n scripts/*.sh
python3 -m py_compile scripts/*.py benchmarks/*.py
python3 -m pytest scripts/test_context_cli.py scripts/test_context_core.py scripts/test_session_index.py scripts/test_context_native.py
python3 scripts/e2e_quality_gate.py
python3 scripts/context_cli.py health
python3 scripts/context_cli.py smoke
python3 scripts/smoke_installed_runtime.py
python3 -m benchmarks --mode both --iterations 1 --warmup 0 --query benchmark --format text
go test ./...
```

如果你在本地启用了 Native 热路径，还应补跑：

```bash
python3 scripts/context_cli.py native-scan --backend go --threads 2 --query NotebookLM --limit 5 --json
python3 scripts/context_cli.py native-scan --backend rust --threads 2 --query NotebookLM --limit 5 --json
```

## 性能与 Native 路线

ContextGO 当前的路线不是“全面重写”，而是“热点替换”：

1. 先让 Python 主链成为最稳的默认路径。
2. 用 `benchmarks/` 明确测出瓶颈。
3. 只把热路径抽到 Rust/Go。
4. 对外仍然保持同一套 CLI、同一套部署脚本、同一套 smoke。

当前 benchmark 已明确区分：

- `python`：进程内主链成本
- `native-wrapper`：子进程包装层成本，不等于纯 Go/Rust 核心执行时间

这让性能判断更诚实，不会再把“解释器启动成本”误写成“Native 核心变慢”。

## 架构原则

- 如无必要，勿增实体
- 默认本地优先
- 默认低 token、低 surprise
- 统一入口优先于多模块拼接
- 兼容保留优先于破坏式重命名
- 任何优化都必须通过 smoke 与已安装运行时验证

## 商业化交付视角

ContextGO 适合作为以下场景的内部产品：

- AI 编码团队的本地上下文底座
- 研发组织的私有记忆与检索运行时
- 需要低 token、低泄露风险的本地辅助层
- 需要逐步替换热点而不是整体重写的过渡平台

它不假设云端向量库，不假设中心化编排服务，也不要求运维额外托管一套旁路基础设施。

## FAQ

### 它是库还是产品？

首先是产品，其次才是代码仓库。

### 它是否依赖 MCP？

默认不依赖。当前主链是 MCP-free。

### 它是否必须接远程服务？

不需要。默认完全本地。

### 它是否必须接向量数据库或向量 API？

当前默认不需要。精确索引、结构化 snippet、SQLite 回退和本地记忆已经覆盖主需求。只有当你要处理超长文本块、跨语义弱匹配、跨知识域召回时，才值得评估可选向量层。

### 为什么还保留 `context-mesh-foundry` 路径和 `contextmesh` 服务名？

为了升级平滑和可回滚。品牌可以切到 `ContextGO`，运行时兼容路径不必在同一天全部打断。

## 版本

- 当前发布版本：`0.6.1`
- 本轮发布说明：[`docs/RELEASE_NOTES_0.6.1.md`](/Volumes/AI/GitHub/context-mesh-foundry/docs/RELEASE_NOTES_0.6.1.md)
- 历史变更：[`CHANGELOG.md`](/Volumes/AI/GitHub/context-mesh-foundry/CHANGELOG.md)

## English Snapshot

ContextGO is a local-first context runtime for multi-agent engineering teams.
It ships as a commercializable monolith: unified CLI, local indexing, memory storage, smoke checks, deployment scripts, and gradual Rust/Go hot-path migration without changing operator workflows.
