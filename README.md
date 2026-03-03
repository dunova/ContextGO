# Context Mesh Foundry 1.0

一个面向多终端 AI 协作的本地上下文系统。

## 项目定位

Context Mesh Foundry 1.0 由三套开源能力粘合而成：

1. OneContext：历史会话检索（规则检索）。
2. OpenViking：语义记忆检索与写入（向量检索）。
3. GSD：任务执行流程约束（讨论、计划、执行、验证）。

说明：AO（Agent Orchestrator）层已从本仓库移除，不再作为核心依赖。

## 1.0 最终功能

1. 双通道检索。
- OneContext 提供精确历史命中。
- OpenViking 提供语义近似召回。

2. 记忆沉淀与去噪。
- 守护进程持续采集终端会话。
- 写入前执行敏感信息脱敏与低价值过滤。

3. 跨终端统一上下文。
- 支持 Codex、Claude、Gemini Antigravity 等终端共享记忆底座。

4. 健康检查与自恢复。
- 巡检服务、日志、数据库、权限、端口、积压队列。
- 支持 launchd 与 systemd 用户级模板。

## 架构流程

终端会话输入 -> 守护进程清洗与导出 -> OpenViking 写入索引 -> MCP 查询桥接 -> AI 终端读取与追问

检索采用双路径：
- 路径 A：OneContext 精确检索。
- 路径 B：OpenViking 语义检索。

## 仓库结构（1.0）

- `scripts/viking_daemon.py`：会话采集、脱敏、导出与重试。
- `scripts/start_openviking.sh`：OpenViking 启动与环境准备。
- `scripts/openviking_mcp.py`：MCP 工具桥接（检索、写入、健康）。
- `scripts/context_healthcheck.sh`：系统健康检查。
- `scripts/unified_context_deploy.sh`：统一部署与脚本同步。
- `scripts/scf_context_prewarm.sh`：执行前上下文预热。
- `templates/launchd/*`：macOS 常驻模板。
- `templates/systemd-user/*`：Linux 用户级常驻模板。

## 快速开始

1. 准备环境变量。
- 在仓库根目录执行 `cp .env.example .env`。
- 至少设置 `GEMINI_API_KEY`。

2. 启动 OpenViking。
- 在仓库根目录执行 `bash scripts/start_openviking.sh`。

3. 启动守护进程。
- 在仓库根目录执行 `python3 scripts/viking_daemon.py`。

4. 运行健康检查。
- 在仓库根目录执行 `bash scripts/context_healthcheck.sh --deep`。

## 安全与隐私

1. 默认本地优先，不上传原始终端日志。
2. 写入前自动脱敏（密钥、令牌、密码等）。
3. 建议 `.env` 与本地密钥文件仅当前用户可读写。

## 版本说明

- 当前版本：1.0.0
- 目标：稳定、轻量、可维护。
