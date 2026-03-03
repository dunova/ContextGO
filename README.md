# Context Mesh Foundry 1.0

多终端 AI 上下文系统（AGPL-3.0）。

## 核心目标

1. 统一记忆采集：跨 Codex、Claude、Gemini Antigravity、Shell。
2. 双路径检索：OneContext 精确检索 + OpenViking 语义检索。
3. 低噪声记忆沉淀：脱敏、去重、私密块过滤、失败重试。
4. 可审计运维：健康检查、索引统计、可视化查看。

## 融合能力（含本次吸收）

1. P0：三层检索工作流。  
• `search`：只拿轻量索引（ID 列表）。  
• `timeline`：围绕锚点看时序上下文。  
• `get_observations`：按 ID 拉完整详情。  

2. P0：私密标签隔离。  
• 支持 `<private>...</private>`，写入前剔除。  
• 避免低价值或敏感内容沉淀到长期记忆。  

3. P1：导入导出与去重。  
• `export_memories.py` 导出记忆 JSON。  
• `import_memories.py` 按 `fingerprint` 去重导入。  

4. P2：实时查看面板。  
• `memory_viewer.py` 提供 API + SSE。  
• 可直接在浏览器查看索引、时间线与详情。  

## 目录结构

- `scripts/viking_daemon.py`：多源采集、脱敏、导出、重试。
- `scripts/memory_index.py`：统一本地记忆索引。
- `scripts/openviking_mcp.py`：MCP 工具层。
- `scripts/memory_viewer.py`：查看面板与 API/SSE。
- `scripts/export_memories.py`：记忆导出。
- `scripts/import_memories.py`：记忆导入（去重）。
- `scripts/context_healthcheck.sh`：系统巡检。
- `scripts/start_openviking.sh`：OpenViking 启动脚本。
- `scripts/start_memory_viewer.sh`：Viewer 启动脚本。

## 快速开始

1. 复制环境文件：在仓库根目录执行 `cp .env.example .env`。  
2. 启动 OpenViking：在仓库根目录执行 `bash scripts/start_openviking.sh`。  
3. 启动守护进程：在仓库根目录执行 `python3 scripts/viking_daemon.py`。  
4. 启动 Viewer：在仓库根目录执行 `bash scripts/start_memory_viewer.sh`。  
5. 健康检查：在仓库根目录执行 `bash scripts/context_healthcheck.sh --deep`。  

## MCP 工具

1. 三层检索：`workflow_important`、`search`、`timeline`、`get_observations`。  
2. 记忆写入：`save_conversation_memory`。  
3. 双检索通道：`search_onecontext_history`、`query_viking_memory`。  
4. 系统状态：`context_system_health`。  

## 导入导出示例

1. 导出：在仓库根目录执行 `python3 scripts/export_memories.py "认证故障" ./exports/auth.json --limit 500`。  
2. 导入：在仓库根目录执行 `python3 scripts/import_memories.py ./exports/auth.json`。  

## 安全说明

1. 默认本地存储，文件权限收敛到当前用户。  
2. 守护进程内置密钥/令牌/密码/私钥块脱敏。  
3. `<private>` 标签内容不进入长期记忆索引。  

## 许可证

本仓库采用 `GNU Affero General Public License v3.0`。详见 `LICENSE`。
