<!-- SCF:CONTEXT-FIRST:START -->
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
- 若当前工作区明确，给查询补一个工作区锚点（如 `ContextGO`、`QuantX` 或当前目录名）
- 先试 2-3 条紧凑查询，不要一上来堆很多词：
  - `contextgo search "2026-04-14 ContextGO codex" --limit 5 --literal`
  - `contextgo search "2026-04-14 127.0.0.1:5050 monitoring codex" --limit 5 --literal`
  - `contextgo semantic "2026-04-14 Codex progress in ContextGO" --limit 3`
- 只有这些紧凑查询都无效时，才考虑回退到平台原生 session 查询或原始会话文件

### 强约束
- 禁止每次聊天都跑 ContextGO
- 禁止在没有历史需求时先扫全仓再说“我去查一下”
- 禁止盲扫 `~/`、`/Volumes/*` 等大目录

### 持久记忆
仅在以下情况保存：
- 已确认的根因
- 已拍板的架构决策
- 下一窗口高概率会复用的交接信息

保存命令：
`~/.local/bin/contextgo save --title "..." --content "..." --tags "..."`
<!-- SCF:CONTEXT-FIRST:END -->

