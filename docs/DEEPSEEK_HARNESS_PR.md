# DeepSeek Harness (`deepseek-ai/deepseek-harness`) PR 提案与收录申请

**Target Repository:** `deepseek-ai/deepseek-harness`  
**PR Title:** `feat(plugin): add dsh-plugin-contextgo for cross-agent local memory & hybrid recall`

---

## PR 描述模板 (Pull Request Description)

```markdown
### Summary

Adds `dsh-plugin-contextgo`, an official Cordis/DSH integration plugin for **ContextGO** (Local-first context & memory runtime for multi-agent AI coding teams).

### Features & Capabilities for DeepSeek Agent
- **Cross-Agent Memory Recall**: Empowers DeepSeek Agent (`dsh`) to search and recall past solutions, technical decisions, and sessions across 15+ AI coding platforms (DeepSeek, Reasonix, Hermes, Claude Code, Factory, Copilot, Cursor, etc.).
- **High-Signal Function Calling**: Registers 4 first-class tools (`contextgo_recall`, `contextgo_search`, `contextgo_semantic`, `contextgo_save`) on `ctx.tools`.
- **Zero-Cloud & Zero-Latency**: Runs directly on local SQLite + BM25S ranking with sub-millisecond retrieval.
- **Smart Context-First (SCF)**: Automatically respects the prewarm/recall lifecycle to avoid token budget waste.

### Installation for DSH Users
```bash
pnpm add dsh-plugin-contextgo
```

### Verification
- Tested with DeepSeek V4 / Flash models in local `dsh web` workbench.
- Tool registration verified in `packages/client/ui-settings-plugin-inventory`.
```
