#!/usr/bin/env bash
# apply_context_first_policy.sh -- inject the SCF context-first policy block
# into agent entry-point files (AGENTS.md / CLAUDE.md).
#
# Usage: apply_context_first_policy.sh [--help]
#
# Idempotent: removes any existing SCF block before appending the current one.
# Missing target files are silently skipped (not an error).
#
# Exit codes:
#   0  Policy applied (or skipped for absent files) successfully.
#   1  Unexpected error (e.g. mktemp failure).
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") [--help]

Inject the SCF context-first policy block into agent entry-point files.
Currently targets:
  ~/.codex/AGENTS.md
  ~/.claude/CLAUDE.md
  ~/.factory/AGENTS.md
  ~/.gemini/GEMINI.md
  ~/.openclaw/workspace/AGENTS.md

Idempotent -- safe to run repeatedly.
EOF
    exit 0
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    usage
fi

log() { printf '[context-first] %s\n' "$*"; }

readonly START_MARK="<!-- SCF:CONTEXT-FIRST:START -->"
readonly END_MARK="<!-- SCF:CONTEXT-FIRST:END -->"

read -r -d '' POLICY_BLOCK <<'EOF' || true
<!-- SCF:CONTEXT-FIRST:START -->
## 🛑 交付阻断门禁（Exit Checklist / Pre-response Gate · 全局最高优先级铁律）

凡涉及架构变更、系统优化、网络调试、故障排查、根因定位、参数调优与配置落地的任务，**严禁仅在聊天对话框中输出总结！在向用户输出最终回复前，必须无条件执行以下阻断检查并闭环**：

### 铁律 1：【非落盘不交付（No Artifact, No Finish）】
1. **严禁口头交付**：严禁将聊天输出作为交付成果的唯一载体。未在磁盘落盘技术成果并产生持久文档，视为**未完成任务**。
2. **强制落盘路径与规范**：
   - **运维与基础设施类项目**（如网络、网关、VPS、数据库、服务运维）：必须在项目对应运维文档目录（优先 `06-运维文档/`，次选 `docs/ops/`、`docs/`、`operations/`）下落盘独立的结构化交底文档，命名规范：`YYYYMMDD_<模块/故障>_<操作/结论>.md`。
   - **研发/代码/策略/系统类项目**：必须在项目对应的架构或交底文档目录（如 `docs/`、`rfcs/`、`architecture/`）落盘技术文档。
3. **技术交底文档五要素（缺一不可）**：
   - **背景与目标**：明确变更动机、影响范围与预期收益；
   - **根因剖析与确凿证据**：详实记录诊断过程、指标对比、错误日志截取或链路追踪数据；
   - **变更清单（Diff 对比）**：精确记录「变更前旧值」与「变更后新值」，标明具体文件路径、配置项与代码行号；
   - **实测验证记录**：列出实际执行过的复核命令与客观结果证据（delay、HTTP 状态码、吞吐测试、单元测试输出）；
   - **回退方案（Rollback）**：必须提供**可直接复制粘贴执行的单行命令或脚本入口**，严禁使用“手动改回”、“按原样恢复”等模糊表述。
4. **变更留痕联动**：若当前项目维护有变更总账（例如 `06-运维文档/网络优化变更总账.md` 或 `CHANGELOG.md`），在交底文档落盘的同时必须立即向总账追加精确到秒的变更记录，严禁遗漏。

### 铁律 2：【ContextGO 持久化强制门禁（ContextGO Save Gate）】
1. **任务结束前强制阻断自检**：在组织向用户的最终汇报前，必须显式检查本轮交互是否包含以下三类持久化资产：
   - **Hard Bug 根因确诊**（已定位/复现/修复的疑难故障与隐藏陷阱）；
   - **架构决策与技术选型**（已拍板的技术路线、协议选择、参数基准、拓扑调整）；
   - **跨窗口交接与运维上下文**（下一轮对话、其他 Agent 或其他平台高概率复用的关键信息与操作入口）。
2. **命中即执行终端落盘**：只要命中上述任意一项，**必须立即在终端执行保存命令**，将结构化要点同步至 ContextGO 知识库：
   ```bash
   ~/.local/bin/contextgo save --title "<Bug/Decision/Handoff>: <简短说明>" --content "<技术交底文档路径 + 核心要点总结>" --tags "<项目名>,<模块名>,<类型>"
   ```
3. **闭环汇报**：汇报时必须显式汇报文档落盘路径以及 `contextgo save` 的执行状态与标题，坚决杜绝“纸上谈兵、聊完即忘”！

---

## ⚠️ ContextGO Smart Recall Policy (HIGHEST PRIORITY)

目标：只在真正需要时调用 ContextGO；默认保持静默，避免每轮对话都灌上下文和浪费 token。

### 应当调用
- 新窗口 / 冷启动：第一次进入一个仓库或新任务
- 续做任务：`continue` / `接着做` / `上次做到哪` / `当前状态`
- 交接与历史：用户提到之前的决定、根因、方案、另一个 agent 的工作
- 主题切换：和当前主题重叠很低，明显进入新问题
- 结构问题：架构、依赖、调用链、影响半径、重构落点、`哪个文件/模块/函数`

### 不应调用
- 同一主题里的连续追问、澄清、微调
- 简短确认：`好的`、`收到`、`ok`、`谢谢`
- 纯闲聊、翻译、润色、礼貌回复
- 已经在当前窗口刚做过召回，且问题仍是同一主题

### 调用顺序
1. 若问题包含明确标识符、文件名、报错串、函数/类名：先 `contextgo search "<query>" --limit 5 --literal`
2. 若问题是续做、历史、主题级问题：用 `contextgo semantic "<topic>" --limit 3`
3. 若当前环境有 code graph，且问题是架构/调用链/影响半径/重构定位：
   先用 graph，看结构；再用 ContextGO 补历史决策与过往根因
4. 结果必须压缩成 2-3 句；禁止粘贴原始长输出
5. 在没有命中时静默继续，不要为了“显得勤奋”重复检索

### 检索启发
- 用户说“昨天 / 今天 / 上次 / 前天”时，先转成绝对日期再检索
- 若当前工作区明确，给查询补一个工作区锚点（如 `ContextGO` 或当前工作区/目录名）
- 先试 2-3 条紧凑查询，不要一上来堆很多词：
  - `contextgo search "2026-04-14 ContextGO codex" --limit 5 --literal`
  - `contextgo search "2026-04-14 127.0.0.1:5050 monitoring codex" --limit 5 --literal`
  - `contextgo semantic "2026-04-14 Codex progress in ContextGO" --limit 3`
- 只有这些紧凑查询都无效时，才考虑回退到平台原生 session 查询或原始会话文件

### 强约束
- 禁止每次聊天都跑 ContextGO
- 禁止在没有历史需求时先扫全仓再说“我去查一下”
- 禁止盲扫 `~/`、`/Volumes/*` 等大目录

### 持久记忆与落盘门禁（强制执行）
在任务结束向用户汇报前，必须显式自检并执行：
- 凡确诊 Hard Bug 根因、拍板架构决策、或产生关键交接，**必须立即调用命令写入 ContextGO**；
- 凡涉及架构变更、故障排查、根因定位、参数落地，**必须先落盘技术交底文档（非落盘不交付）**。

保存命令：
`~/.local/bin/contextgo save --title "<Bug/Decision/Handoff>: <简短说明>" --content "<技术交底文档路径 + 核心要点>" --tags "<项目名>,<模块名>,<类型>"`
<!-- SCF:CONTEXT-FIRST:END -->
EOF

strip_old_block() {
    local file="$1"
    awk -v s="$START_MARK" -v e="$END_MARK" '
        BEGIN { skip=0 }
        index($0, s) { skip=1; next }
        index($0, e) { skip=0; next }
        skip==0 { print }
    ' "$file"
}

ensure_policy() {
    local file="$1"
    if [ ! -f "$file" ]; then
        log "skip (missing): $file"
        return 0
    fi

    python3 -c "
import sys
from pathlib import Path

path = Path(sys.argv[1])
policy = sys.argv[2]
start_mark = '<!-- SCF:CONTEXT-FIRST:START -->'
end_mark = '<!-- SCF:CONTEXT-FIRST:END -->'

try:
    content = path.read_text(encoding='utf-8')
except Exception:
    sys.exit(1)

if start_mark in content:
    s_idx = content.index(start_mark)
    e_idx = content.index(end_mark, s_idx) + len(end_mark)
    old = content[s_idx:e_idx]
    if old != policy:
        updated = content[:s_idx] + policy + content[e_idx:]
        path.write_text(updated, encoding='utf-8')
else:
    updated = policy + '\n\n' + content.lstrip()
    path.write_text(updated, encoding='utf-8')
" "$file" "$POLICY_BLOCK"

    log "patched: $file"
}

FILES=(
    "$HOME/.codex/AGENTS.md"
    "$HOME/.claude/CLAUDE.md"
    "$HOME/.factory/AGENTS.md"
    "$HOME/.gemini/GEMINI.md"
    "$HOME/.openclaw/workspace/AGENTS.md"
)

for f in "${FILES[@]}"; do
    ensure_policy "$f"
done

log "done"
