# ContextGO 0.15.0 Release Notes

**ContextGO 0.15.0 makes memory genuinely portable. A memory is no longer "a file in some folder on some machine" — it is an identified, provenance-stamped record that any machine can hold.**

**ContextGO 0.15.0 让记忆真正可以跨机器流动。记忆不再是"某台机器某个文件夹里的一个文件"，而是一条带身份与来源的、任何机器都能持有的记录。**

---

## 🌟 Highlights / 核心亮点

### 1. Memory-First Identity / 记忆优先的身份模型（schema v6）

The row identity of a session memory used to be its **machine-local absolute path**:

```sql
file_path TEXT PRIMARY KEY     -- identity == /Users/alice/... on THIS machine
```

That single choice is why cross-machine sharing failed: the same memory indexed on two machines produced two rows that could not see each other, and any scan on the receiving machine concluded "these paths do not exist here → delete them".

Identity is now derived from content:

```python
doc_id = sha256(source_type ‖ session_id ‖ title ‖ content ‖ created_at_epoch)
```

会话记忆的主键从**本机绝对路径**改为**内容指纹**。同一段会话在两台机器上索引会得到同一个 `doc_id`，因此合并为一条记忆，而不是两条互相不可见的记录。

### 2. Provenance & Origin-Scoped Pruning / 来源标记与按来源剪枝

Every document now records which node produced it (`origin_host`, `origin_os`, `origin_label`, `origin_path`). The only question that matters for safe deletion is answered directly:

```
delete  ⇔  (origin_host == this node)  AND  (the local file really disappeared)
```

**Imported memories are never pruned by the receiving machine**, even though their original paths can never exist there.

### 3. Four Root Causes of Cross-Machine Memory Loss — Fixed / 四个跨机器丢失根因已修复

| # | Root cause | Before | After |
|---|---|---|---|
| 1 | Path-as-identity | Foreign paths look "stale" → deleted | Content identity; foreign rows exempt from local pruning |
| 2 | Schema-skew reset | `DELETE FROM session_documents` on version mismatch | Reconcile in place, **never** a table-wide delete |
| 3 | `sha256(home)` mirror namespace | Same machine via a different home = a "new" node with an empty mirror | Persistent `node.json` identity; legacy dirs adopted automatically |
| 4 | "Tool not installed ⇒ wipe mirror" | `_prune_stale(dir, keep=∅)` erased mirrored history | Empty keep-set means *unknown sources*, not *all stale* |

### 4. Portable Memory Packs / 可携带记忆包

```bash
contextgo memory-pack export --out ~/memories.memories.json
contextgo memory-pack import ~/memories.memories.json
```

- Merges by content fingerprint → **idempotent**, safe to re-run
- Recomputes identity from content on import → a pack cannot inject a forged identity
- Preserves the sender's provenance → imported rows are exempt from local pruning
- Needs **no shared filesystem** between the machines

### 5. Memory Survives File Loss / 记忆不再因文件消失而蒸发

`CONTEXTGO_SESSION_PRUNE_ENABLED` defaults to **off**. A row is a memory, not a pointer: once indexed, losing the originating log file (cleaned-up directories, a relocated home, a transient mount, a snapshot restored without its raw mirror) no longer destroys recall.

### 6. Diagnostics / 可观测

```bash
$ contextgo node
ContextGO node identity / 节点身份
  node_id   : f08fe06af2654ce9
  label     : omarchy
  platform  : linux

Session memories / 会话记忆（共 4562 条）
     4556  f08fe06af2654ce9     omarchy    ← this node / 本机
        6  bbbb333344445555     mac-mini
```

### 7. MCP Server Repaired / 顺带修复的 MCP 缺陷

While building the regression suite, three defects in the shipped MCP server surfaced:

| Defect | Impact | Fix |
|---|---|---|
| `contextgo_save` called a non-existent `context_core.save_memory` | **Every** save through MCP raised `AttributeError` — the one operation an agent most needs to be reliable | Delegates to the same path as `contextgo save` |
| `SERVER_VERSION` hardcoded to `0.14.1` | Clients were told the wrong version after every release | Read from the installed package |
| `readline()` `OSError` retried forever | A broken pipe spun the server at 100% CPU | Terminates like EOF |

Two further data-safety defects in the SCF policy injector were found and fixed:

| Defect | Impact | Fix |
|---|---|---|
| `setup` / `unsetup` swept **every** project under `$HOME` | Running `unsetup` (or the test suite) rewrote `.cursorrules` in unrelated repositories — this is what emptied the ContextGO checkout's own rule files during this work | Sweep is now opt-in via `CONTEXTGO_SETUP_SCAN_HOME=1`; default is the current directory |
| Removal left a 0-line file when the policy block was the whole file | A blank rules file silently overrides nothing but looks configured | The file is deleted instead |

---

## ✅ Verified on real data / 真实数据实测

Migrating a live 4,556-row index produced by an earlier release:

| Check | Result |
|---|---|
| Rows after in-place v5→v6 migration | **4,556 / 4,556** (zero loss) |
| Rows with a unique `doc_id` | 4,556 distinct |
| Rows stamped with this node's origin | 4,556 |
| Forced full rescan afterwards | `scanned=4233, updated=4227, added=6, **removed=0**` |
| Total after rescan | 4,562 (nothing lost) |

The same forced rescan on 0.14.1 would have deleted every imported row.

---

## 🔄 Upgrade Notes / 升级说明

- **Automatic**: the v5→v6 migration runs on first command after upgrade. No manual step, no data export required.
- **Downgrade is not supported**: 0.14.x cannot read a v6 database. Back up `~/.contextgo/index/session_index.db` before downgrading.
- **Cross-machine workflow**: prefer `contextgo memory-pack` (or the existing encrypted `contextgo sync`) over copying the index database or `raw/` between machines. Those are machine-local caches; reconciling their foreign paths is exactly the operation that used to delete imported memory.
- **New tests**: `tests/test_cross_machine_memory.py`, `tests/test_coverage_error_paths.py`, `tests/test_mcp_tool_dispatch.py`. Full suite: **1,594 passed, 0 failed**, coverage **86.06%** (the 86% gate was already failing at 84.46% before this release).

---

## 📐 Design Document / 设计文档

`docs/CROSS_MACHINE_MEMORY.md` documents the failure taxonomy, the three-layer model (raw corpus → session memory → curated memory), the memory pack wire format, the migration matrix, the 16 testable invariants, and the known boundaries (content truncation, vector index not yet packed, no incremental packs, no conflict resolution).

---

## 🙏 Acknowledgements

This release exists because a real cross-machine migration destroyed an index from 4,556 rows down to 1 — and the fix had to be architectural, not another patch.

本次发版源于一次真实的跨机器迁移事故：索引从 4,556 条掉到 1 条。这类问题只能靠架构修复，而不是再加一个补丁。
