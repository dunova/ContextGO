# Model Context Protocol (MCP) Registry Submission Proposal

**Target Repository:** `modelcontextprotocol/servers` / MCP Official Registry  
**Server Name:** `contextgo`  
**Description:** Local-first context and cross-agent memory runtime for AI coding assistants.

---

## 1. Metadata Schema

```json
{
  "$schema": "https://modelcontextprotocol.io/schema/server.json",
  "name": "contextgo",
  "title": "ContextGO Memory & Context Runtime",
  "description": "Local-first context and cross-agent memory runtime for multi-agent AI coding teams. Enables instant sub-second lookup on 15+ AI coding sessions (DeepSeek, Reasonix, Hermes, Claude Code, Copilot, Cursor, etc.) and durable architectural decisions.",
  "repository": {
    "type": "git",
    "url": "https://github.com/dunova/ContextGO"
  },
  "homepage": "https://github.com/dunova/ContextGO",
  "license": "AGPL-3.0-only",
  "categories": ["developer-tools", "memory", "context", "search"],
  "installation": {
    "pipx": "pipx install 'contextgo[vector]'",
    "pypi": "contextgo"
  },
  "command": "contextgo",
  "args": ["mcp"],
  "env": {
    "CONTEXTGO_STORAGE_ROOT": {
      "description": "Custom root directory for storage (default: ~/.contextgo)",
      "required": false
    }
  }
}
```

---

## 2. Tools Exposed

| Tool Name | Parameters | Description |
|---|---|---|
| `contextgo_recall` | `query: string`, `limit?: int` | Fast hybrid BM25S/vector recall across cross-agent session histories. |
| `contextgo_search` | `query: string`, `limit?: int` | Full-text lexical search over all indexed AI coding sessions and command runs. |
| `contextgo_semantic` | `topic: string`, `limit?: int` | Semantic search prioritizing durable architectural decisions and root causes. |
| `contextgo_save` | `title: string`, `content: string`, `tags?: string` | Save a confirmed bug root cause, key decision, or handoff note to local storage. |

---

## 3. Pull Request Description Template

### Title:
`Add ContextGO: Local-first context and cross-agent memory runtime`

### Body:
```markdown
### Server Overview
- **Name:** ContextGO
- **Repository:** https://github.com/dunova/ContextGO
- **Language:** Python (3.10+)
- **Transport:** stdio (JSON-RPC 2.0)

### What it does:
ContextGO gives AI coding agents (DeepSeek Agent, Claude Code, Cursor, Windsurf, OpenCode, etc.) durable local memory across tools, projects, and machines. It indexes sessions into a zero-latency SQLite runtime with BM25S and optional vector embeddings, without remote database or cloud lock-in.

### Compatibility:
- Tested against official Model Context Protocol TypeScript SDK (`@modelcontextprotocol/sdk`).
- Supports cross-platform environments (Windows, macOS, Linux).
```
