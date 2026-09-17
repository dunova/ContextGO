# ContextGO as a Shared Memory Body — 跨平台 · 跨工具 · 跨机器记忆体设计

> **状态**：Implemented (schema v6, "memory-first")
> **适用范围**：ContextGO ≥ 0.15.0
> **一句话结论**：记忆的身份必须来自**内容**，不能来自**文件路径**。把路径当身份的那一刻，你的"记忆库"就退化成了"某台机器某个文件夹的缓存"。

---

## 1. 问题：文件缓存陷阱（The File-Cache Trap）

ContextGO 的目标是让多个 AI 工具、多台机器共享同一份记忆。但在 v6 之前，`session_documents` 的表结构是：

```sql
CREATE TABLE session_documents (
    file_path        TEXT PRIMARY KEY,   -- ← 身份 = 本机绝对路径
    ...
    file_mtime       INTEGER NOT NULL,   -- ← 新鲜度 = 本机文件元数据
    file_size        INTEGER NOT NULL
)
```

这一行定义决定了整个系统的性质：**索引是本机文件系统的派生缓存，不是可迁移的记忆资产。**

### 1.1 实测事故（2026-09-17，真实跨机器迁移）

把 Mac 上的记忆快照搬到 Linux 节点后：

| 阶段 | 观察结果 |
|---|---|
| 解包完成 | `session_documents` 11 分钟后从 **4,556 条 → 1 条** |
| 根因 A | 全量扫描执行 `DELETE ... WHERE file_path NOT IN (seen_paths)`，而外来路径在本机全部不存在 |
| 根因 B | 适配器镜像目录名 = `sha256(home)[:12]`，Mac 是 `226c42ad0dce`、Linux 是 `634d0ab99fe5`，运行时找不到镜像 |
| 根因 C | `sync_all_adapters()` 对"本机未安装的工具"调用 `_prune_stale(dir, keep=∅)`，把镜像整目录清空 |
| 根因 D | `schema_version` 一变就执行 `DELETE FROM session_documents`——**无条件清空整张表** |

四个根因互不相同，但都指向同一个设计缺陷：**系统无法区分"这条记忆是我写的"和"这条记忆是别人给我的"。**

### 1.2 为什么"同步整库"永远不可靠

即使把上述四点的补丁都打上，把 `session_index.db` 整库复制到另一台机器仍然不成立：

- 库里混着**纯本机的事实**（绝对路径、mtime、size、inode 语义）；
- 接收方必须把这些外来路径跟**自己的**文件系统对账，而对账的默认结论就是"文件不存在 → 删掉"；
- 任何一次 schema 演进都会让旧库变成"需要重建"的对象，而"重建"的旧实现等于"清空"。

**结论：跨机器共享的载体必须是记忆本身，不是存记忆的那个文件。**

---

## 2. 设计：Memory-First 架构

### 2.1 三层模型

| 层 | 内容 | 是否可移植 | 载体 |
|---|---|---|---|
| **L1 原始语料** | 各工具会话日志的镜像（`raw/adapters/...`） | ⚠️ 半可移植（含本机路径） | 本机缓存，**不作为同步单元** |
| **L2 会话记忆** | 索引化后的会话（`session_documents`） | ✅ 可移植 | 记忆包 / 加密同步 |
| **L3 沉淀记忆** | 人工落盘的结论、根因、决策（`observations`） | ✅ 可移植 | 记忆包 / 加密同步 |

**关键**：L2 与 L3 必须以同样的身份模型工作。v6 之前只有 L3 是内容寻址的（`observations.fingerprint = sha256(source_type|title|content|created_at_epoch)`），L2 是路径寻址的——两层身份模型不一致，正是跨机器失败的深层原因。

### 2.2 身份：内容寻址（Content-Addressed Identity）

```python
doc_id = sha256(source_type ‖ session_id ‖ title ‖ content ‖ created_at_epoch)
```

由此直接得到三条性质：

| 性质 | 含义 |
|---|---|
| **可移植** | 同一段会话在两台机器上索引 → 同一个 `doc_id` → 一行，而不是两行互相不可见 |
| **改名安全** | `/Users/x/...` 与 `/home/x/...` 是同一份记忆，重挂载/改名不产生重复 |
| **可剪枝** | 删除决策可以限定在"真正拥有该文件的那台机器"上 |

`file_path` 从主键降级为**来源线索**（provenance hint），`file_mtime`/`file_size` 只对本机行有意义。

### 2.3 来源：稳定节点身份（Node Identity）

机器身份不再由 home 路径哈希派生，而是持久化在 `<storage_root>/node.json`：

```json
{ "schema_version": 1, "node_id": "f08fe06af2654ce9", "label": "omarchy", "platform": "linux" }
```

- `node_id` 生成一次，永不变更，**与路径、用户名、主机名无关**；
- `label`（主机名）仅用于展示，可随时变；
- 适配器镜像命名空间随之改为 `raw/adapters/node-<node_id>/`，并**自动接管**旧版 `sha256(home)[:12]` 目录（避免升级后看着像一台新机器）。

### 2.4 剪枝语义：按来源作用域（Origin-Scoped Prune）

这是本次修复的**承重墙**：

```
删除条件 = (origin_host == 本机)  AND  (本地文件确实消失)
```

- **外来行永不被本机剪枝**——它们的 `origin_path` 指向另一台机器的文件系统，在本机"不存在"是常态，不是陈旧；
- 本地行默认也**不删**（见 2.5）；
- 唯一的例外是显式开关 `CONTEXTGO_SESSION_PRUNE_ENABLED=1`。

### 2.5 默认不删：记忆一旦沉淀就不该因文件消失而蒸发

```
CONTEXTGO_SESSION_PRUNE_ENABLED  (默认 0)
```

在"记忆体"语义下，行就是记忆：内容在索引时就已捕获，源文件的消失（日志被清理、home 被迁移、挂载点临时缺失、快照恢复时漏了 raw 镜像）**不应该静默摧毁可召回的记忆**。想要旧的"索引镜像文件系统"行为，可显式打开。

### 2.6 交换：记忆包（Memory Pack）

```bash
contextgo memory-pack export --out ~/memories.memories.json
contextgo memory-pack import ~/memories.memories.json
```

记忆包只携带**可移植的事实**：身份、内容、时间、来源。

```json
{
  "format": "contextgo-memory-pack",
  "schema_version": 1,
  "node": {"node_id": "...", "label": "...", "platform": "..."},
  "counts": {"documents": 4556},
  "documents": [
    {"doc_id": "...", "source_type": "factory_session", "session_id": "...",
     "title": "...", "content": "...", "created_at": "...", "created_at_epoch": 0,
     "origin_host": "...", "origin_os": "darwin", "origin_label": "mac",
     "origin_path": "/Users/dunova/..."}
  ]
}
```

导入语义：

| 规则 | 原因 |
|---|---|
| 按 `doc_id` 合并，已存在则跳过 | **幂等**，可反复执行 |
| `doc_id` 由接收方**从内容重算** | 记忆包无法注入一个与内容不符的身份 |
| 保留原始 `origin_host` | 导入行永不被接收方剪枝 |
| `file_path` 留空 | 不伪造一个不存在的本地文件 |
| 不依赖发送方文件存在 | 收发双方无需共享任何文件系统 |

### 2.7 两条通道的分工

| 通道 | 用途 | 特点 |
|---|---|---|
| `contextgo sync`（既有） | GitHub Contents API，AES-256-GCM，按设备分片 | 端到端加密，自动增量，适合网络化常态同步 |
| `contextgo memory-pack`（新增） | 文件级记忆包 | 离线可传（U 盘 / NAS / IM），可审计，可纳入备份 |

两者**都建立在 L2/L3 的内容寻址之上**，因此可以混用：加密通道负责日常，记忆包负责跨空气隔断与归档。

---

## 3. 不变量（Invariants）

以下性质由 `tests/test_cross_machine_memory.py` 逐条锁定，可作为验收清单：

| # | 不变量 | 测试 |
|---|---|---|
| I1 | `doc_id` 只由内容决定，与路径无关 | `test_doc_id_is_independent_of_file_path` |
| I2 | `doc_id` 稳定可复现 | `test_doc_id_is_deterministic` |
| I3 | 节点身份不随 home 变化 | `test_node_id_is_not_derived_from_home` |
| I4 | 镜像命名空间不随 home 变化 | `test_adapter_root_ignores_home_variations` |
| I5 | 旧版镜像目录被接管而非孤立 | `test_legacy_digest_directory_is_adopted` |
| I6 | v5→v6 迁移**零丢行** | `test_migration_preserves_every_row` |
| I7 | 迁移幂等 | `test_migration_is_idempotent` |
| I8 | **schema 版本变更不再清库** | `test_schema_version_change_does_not_wipe_rows` |
| I9 | 外来记忆扛过本机强制全量扫描 | `test_foreign_rows_survive_forced_full_sync` |
| I10 | 源文件消失的记忆默认被保留 | `test_local_missing_file_is_retained_by_default` |
| I11 | 显式开关开启时才按旧语义剪枝 | `test_local_missing_file_is_pruned_when_explicitly_enabled` |
| I12 | 未探测到工具时镜像不被清空 | `test_prune_stale_keeps_everything_when_no_sources_detected` |
| I13 | 工具已探测时仍能正常回收陈旧镜像 | `test_prune_stale_still_collects_genuinely_superseded_files` |
| I14 | 记忆包导入幂等 | `test_roundtrip_into_a_second_node` |
| I15 | 记忆包无法伪造身份 | `test_import_recomputes_doc_id_from_content` |
| I16 | 记忆包拒绝错误格式 / 未来版本 | `test_import_rejects_wrong_format` / `..._future_schema` |

---

## 4. 迁移与兼容

| 场景 | 行为 |
|---|---|
| 全新安装 | 直接建 v6 表 |
| v5 及更早的单机库 | 启动时**就地迁移**：加 `doc_id` + provenance，全部行保留，打上本机 `origin_host`，旧表删除 |
| 旧版镜像目录 | 首次访问时 `rename` 到 `node-<node_id>`，历史镜像不丢 |
| 未装工具的镜像 | 不再被清空（`keep=∅` 视为"来源未知"） |
| 已导入的外来记忆 | 与本地记忆一样可搜索、可导出，但永不被本机剪枝 |

`contextgo node` 用于查看节点身份与来源分布：

```
$ contextgo node
ContextGO node identity / 节点身份
  node_id   : f08fe06af2654ce9
  label     : omarchy
  platform  : linux
  home      : /home/dunova

Session memories / 会话记忆（共 4562 条）
     4556  f08fe06af2654ce9     omarchy    ← this node / 本机
        6  bbbb333344445555     mac-mini
```

---

## 5. 变更清单（0.15.0）

| 文件 | 变更 |
|---|---|
| `session_documents` schema | `file_path` 主键 → `doc_id` 主键；新增 `origin_host/origin_os/origin_label/origin_path`；新增 `file_path`/`origin_host` 索引 |
| `session_index.py` | 新增 `compute_doc_id`；新增 v5→v6 就地迁移；**移除 schema 变更时的整表 DELETE**；剪枝改为来源作用域；新增 `PRUNE_LOCAL_MISSING` 策略；新增记忆包导出/导入/读写；`health_payload` 增加来源切分 |
| `source_adapters.py` | 镜像命名空间改为 `node-<node_id>` 并接管旧目录；`_prune_stale` 在 `keep=∅` 时不再删除 |
| `node_identity.py`（新） | 稳定节点身份，持久化于 `<storage_root>/node.json` |
| `context_cli.py` | 新增 `contextgo node`、`contextgo memory-pack export\|import` |
| `tests/test_cross_machine_memory.py`（新） | 16 条不变量的回归测试 |

---

## 6. 尚未解决 / 后续方向

诚实记录边界：

1. **内容截断**：会话内容在索引时会被截断（`CONTEXTGO_SESSION_MAX_CONTENT_CHARS`）。记忆包携带的是截断后的内容，超长会话的完整原文仍只存在于原机 raw 镜像里。
2. **向量索引未纳入记忆包**：`vector_index` 仍是派生数据，需在接收方重建（`contextgo vector-sync`）。
3. **记忆包无增量**：当前是全量导出；大规模节点的增量/差分同步仍应走 `contextgo sync`。
4. **无冲突解决策略**：`doc_id` 相同视为同一记忆（内容相同，无冲突）；但同一会话在两机上被**不同地截断**会产生两个 `doc_id`。需要时的方向是以 `session_id` 做二级归并。
5. **`vector_index.py` 的 file_path 依赖**：其 `DELETE ... WHERE file_path NOT IN (SELECT file_path ...)` 仍假设路径唯一，在多来源场景需要改为按 `doc_id`。
