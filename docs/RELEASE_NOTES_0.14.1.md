# ContextGO 0.14.1 Release Notes

ContextGO 0.14.1 delivers native Model Context Protocol (MCP) standard server parity, dynamic project discovery, comprehensive pre-response delivery gates in Smart Context-First (SCF) policies, and an overhauled 2x Retina visual documentation showcase with interactive Star and release subscription badges.

ContextGO 0.14.1 带来了原生 Model Context Protocol (MCP) 标准协议服务支持、通用动态项目目录发现、SCF 智能召回策略与交付阻断门禁升级，以及全套 2x Retina 高清视觉展示图与一键 GitHub Star / 版本订阅徽章。

---

## 🌟 Highlights / 核心亮点

### 1. Native Model Context Protocol (MCP) Server / 原生 MCP 服务支持
- **Standard Protocol**: Built-in zero-dependency stdio server (`contextgo mcp`) compatible with MCP specification `2024-11-05`.
- **Exposed Tools**: `contextgo_search` (full-text lexical search), `contextgo_semantic` (hybrid BM25/vector recall), and `contextgo_save` (durable memory persistence).
- **Out-of-the-Box Function Calling**: Instant integration with Claude Code, Cursor, DeepSeek Agent (dsh), Windsurf, and any standard MCP client.

### 2. Smart Context-First (SCF) Policy Gate / 智能召回与交付阻断门禁
- **Exit Checklist Integration**: Pre-response verification to prevent ephemeral chat-only completions without durable artifact documentation.
- **Dynamic Project Discovery**: Sanitized and universalized project discovery for GitHub Copilot and Cursor without hardcoded path dependencies.
- **Strict Privacy Compliance**: Universal guidance for public repositories with zero personal or environment path leakage.

### 3. Visual Architecture Showcase & Community CTA / 2x Retina 高清全景与社区徽章
- **High-Resolution Showcase**: Rendered 2400x1260 2x Retina architectural overview card (`docs/media/contextgo-architecture-showcase.png`) detailing the 3-pillar engine, 15+ supported agents, and AES-256-GCM sync runtime.
- **Interactive Badges**: Added one-click GitHub Star and Release Watch subscription badges to both English and Chinese documentation.

---

## 📦 Verification & Quality / 验证与质量保证
- **Regression Suite**: 100% pass on all CLI, prewarm, and regression test suites.
- **Build Artifacts**: Successfully built `contextgo-0.14.1.tar.gz` and `contextgo-0.14.1-py3-none-any.whl`.
- **Global Tooling**: Upgraded local pipx runtime to `contextgo 0.14.1`.
