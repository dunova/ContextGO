# Context Mesh Foundry 1.0 架构说明

## 核心组件

1. `viking_daemon.py`
- 采集终端会话。
- 执行脱敏与低价值过滤。
- 导出结构化记忆并支持失败重试。

2. `start_openviking.sh`
- 启动 OpenViking 服务。
- 管理虚拟环境与端口占用。
- 支持配置生成与启动前检查。

3. `openviking_mcp.py`
- 提供 MCP 工具层。
- 集成 OneContext 精确检索与 OpenViking 语义检索。
- 提供记忆写入与系统健康快照。

4. `context_healthcheck.sh`
- 巡检进程、端口、API、数据库、日志与权限。
- 输出可读的健康状态报告。

5. `unified_context_deploy.sh`
- 将核心脚本同步到多终端技能目录。
- 可选自动修补并重载 launchd 模板。

6. `scf_context_prewarm.sh`
- 在执行任务前进行上下文预热。
- 优先拉取历史精确命中，再补充语义召回。

## 数据流

1. 终端会话进入 `viking_daemon.py`。
2. 会话被脱敏、过滤并导出。
3. OpenViking 对导出内容建立索引。
4. MCP 请求进入 `openviking_mcp.py`。
5. 检索时并行走 OneContext 与 OpenViking。
6. 返回融合结果给 AI 终端。

## 当前边界

1. 本仓库不再包含 AO（Agent Orchestrator）执行层。
2. 本仓库只负责上下文采集、检索、沉淀与健康运维。
