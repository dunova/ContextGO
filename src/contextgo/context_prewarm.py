#!/usr/bin/env python3
"""ContextGO automatic context prewarm engine.

Zero-config, zero-understanding-cost: install → ``contextgo setup`` → done.
Every new conversation auto-recalls relevant memories before the AI starts work.

Architecture:
- ``prewarm()``  — core: extract keywords from user message, search memory, return
  branded summary suitable for injection as hook output.
- ``setup()``    — one-command configuration of all detected AI coding tools.
- Brand output   — all prewarm activity prefixed with ``[ContextGO]``.

Hook integration (Claude Code):
  ``UserPromptSubmit`` hook calls ``contextgo prewarm``.
  stdin receives JSON ``{"prompt": {"content": "..."}}``.
  stdout is injected as ``<user-prompt-submit-hook>`` into the conversation.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

_logger = logging.getLogger(__name__)

__all__ = [
    "extract_keywords",
    "prewarm",
    "prewarm_from_stdin",
    "setup_all",
    "setup_claude_code",
]

# ───────────────────────────────────────────────
# Brand constants
# ───────────────────────────────────────────────

BRAND = "ContextGO"
_PREWARM_START = f"[{BRAND}] 正在召回相关记忆..."
_PREWARM_DONE = f"[{BRAND}] 上下文预热完成"
_PREWARM_EMPTY = f"[{BRAND}] 上下文预热完成 — 记忆库暂无相关记录"
_SETUP_BANNER = f"[{BRAND}] 自动预热配置"

# Chinese + common programming stop words to skip when extracting keywords.
_STOP_WORDS: frozenset[str] = frozenset(
    [
        # Chinese
        "的",
        "了",
        "在",
        "是",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
        "他",
        "她",
        "它",
        "们",
        "么",
        "那",
        "被",
        "它们",
        "些",
        "呢",
        "吗",
        "啊",
        "嗯",
        "哦",
        "吧",
        "哈",
        "嘛",
        "帮",
        "帮我",
        "请",
        "请帮",
        "一下",
        "现在",
        "然后",
        "还有",
        "看看",
        "可以",
        "能不能",
        "怎么",
        "如何",
        "什么",
        # English
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "need",
        "dare",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "it",
        "its",
        "they",
        "them",
        "their",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "when",
        "where",
        "why",
        "and",
        "or",
        "but",
        "not",
        "so",
        "if",
        "then",
        "else",
        "for",
        "at",
        "by",
        "from",
        "in",
        "on",
        "to",
        "with",
        "as",
        "of",
    ]
)

# Minimum keyword length after stripping.
_MIN_KW_LEN = 2


# ───────────────────────────────────────────────
# Keyword extraction
# ───────────────────────────────────────────────


def extract_keywords(text: str, *, max_keywords: int = 6) -> list[str]:
    """Extract meaningful search keywords from a user message.

    Strategy: split on whitespace and punctuation, remove stop words, keep
    the longest (most specific) tokens.  Simple and fast — no NLP needed.
    """
    # Split on anything that is not a word character or CJK.
    tokens = re.findall(r"[\w\u4e00-\u9fff\u3400-\u4dbf]+", text.lower())

    seen: set[str] = set()
    keywords: list[str] = []
    for t in tokens:
        if len(t) < _MIN_KW_LEN:
            continue
        if t in _STOP_WORDS:
            continue
        if t in seen:
            continue
        seen.add(t)
        keywords.append(t)

    # Prefer longer (more specific) keywords.
    keywords.sort(key=len, reverse=True)
    return keywords[:max_keywords]


# ───────────────────────────────────────────────
# Core prewarm
# ───────────────────────────────────────────────


def prewarm(message: str, *, limit: int = 5, timeout: float = 2.0) -> str:
    """Run context prewarm for a user message.  Returns branded output.

    Searches memory files first (fast path), then falls back to session index.
    Total wall time is bounded by *timeout* seconds.

    Returns empty string if nothing relevant is found (silent to user).
    """
    keywords = extract_keywords(message)
    if not keywords:
        return ""

    query = " ".join(keywords)
    t0 = time.monotonic()

    # ── Search paths (parallel, bounded by timeout) ──────────────
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: list[dict[str, Any]] = []
    session_text: str = ""

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="cg-prewarm") as pool:
        futures = {}

        # Path 1: local memory files (preferred).
        try:
            try:
                import context_core as _core  # type: ignore[import-not-found]
            except ImportError:
                from contextgo import context_core as _core  # type: ignore[import-not-found]
            try:
                from context_config import storage_root as _sr  # type: ignore[import-not-found]
            except ImportError:
                from contextgo.context_config import storage_root as _sr  # type: ignore[import-not-found]

            shared_root = _sr() / "resources" / "shared"
            futures["memory"] = pool.submit(
                _core.local_memory_matches,
                query,
                shared_root=shared_root,
                limit=limit,
                max_files=200,
                read_bytes=8192,
                uri_prefix="local://",
            )
        except Exception:
            _logger.debug("Memory search path unavailable", exc_info=True)

        # Path 2: session index FTS.
        try:
            try:
                import session_index as _si  # type: ignore[import-not-found]
            except ImportError:
                from contextgo import session_index as _si  # type: ignore[import-not-found]

            futures["session"] = pool.submit(
                _si.format_search_results,
                query,
                search_type="all",
                limit=min(limit, 10),
                literal=True,
            )
        except Exception:
            _logger.debug("Session index path unavailable", exc_info=True)

        remaining = max(0.1, timeout - (time.monotonic() - t0))
        for f in as_completed(futures.values(), timeout=remaining):
            key = next(k for k, v in futures.items() if v is f)
            try:
                val = f.result(timeout=0.1)
                if key == "memory" and isinstance(val, list):
                    results = val
                elif key == "session" and isinstance(val, str):
                    session_text = val
            except Exception:
                pass

    elapsed = time.monotonic() - t0

    # ── Format output ────────────────────────────────────────────
    return _format_prewarm_output(results, session_text, elapsed, keywords)


def _format_prewarm_output(
    memory_results: list[dict[str, Any]],
    session_text: str,
    elapsed: float,
    keywords: list[str],
) -> str:
    """Format branded prewarm output."""
    lines: list[str] = []

    if memory_results:
        lines.append(f"{_PREWARM_DONE} ({elapsed:.1f}s) — 找到 {len(memory_results)} 条相关记忆")
        lines.append(f"搜索关键词: {', '.join(keywords)}")
        lines.append("")
        for item in memory_results:
            title = item.get("title", "Untitled")
            tags = item.get("tags", "")
            date = item.get("date", "")
            snippet = item.get("snippet", item.get("content", ""))[:120]
            line = f"- {date} | {title}"
            if tags:
                line += f" (tags: {tags})"
            lines.append(line)
            if snippet:
                lines.append(f"  > {snippet}")
        return "\n".join(lines)

    if session_text and not session_text.startswith("No matches found"):
        # Count results from session text.
        count = session_text.count("\n[")
        if count == 0:
            count = 1
        lines.append(f"{_PREWARM_DONE} ({elapsed:.1f}s) — 找到 {count} 条历史会话记录")
        lines.append(f"搜索关键词: {', '.join(keywords)}")
        lines.append("")
        lines.append(session_text)
        return "\n".join(lines)

    # Nothing found — stay silent (return empty string).
    return ""


# ───────────────────────────────────────────────
# Hook entry point (stdin → stdout)
# ───────────────────────────────────────────────


def prewarm_from_stdin() -> int:
    """Read Claude Code hook JSON from stdin, run prewarm, print results.

    Called by: ``contextgo prewarm`` (which is registered as a
    ``UserPromptSubmit`` hook in ``~/.claude/settings.json``).

    Returns 0 always (prewarm is advisory, never blocks the user message).
    """
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    if not raw.strip():
        return 0

    # Parse the hook payload — try several possible shapes.
    message = _extract_message_from_hook(raw)
    if not message or len(message.strip()) < 4:
        return 0

    output = prewarm(message)
    if output:
        print(output)
    return 0


def _extract_message_from_hook(raw: str) -> str:
    """Extract user message text from a Claude Code hook JSON payload."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw.strip()

    # Claude Code format: {"prompt": {"content": "..."}}
    if isinstance(data, dict):
        prompt = data.get("prompt")
        if isinstance(prompt, dict):
            return prompt.get("content", "")
        if isinstance(prompt, str):
            return prompt
        # Fallback: top-level "content" or "message".
        return data.get("content", data.get("message", ""))
    return ""


# ───────────────────────────────────────────────
# One-command setup
# ───────────────────────────────────────────────

# Claude Code settings.json hook configuration.
_CLAUDE_CODE_HOOK = {
    "hooks": {
        "UserPromptSubmit": [
            {
                "matcher": "",
                "command": "contextgo prewarm",
            }
        ]
    }
}

# Codex AGENTS.md SCF policy block.
_SCF_MARKER_START = "<!-- SCF:CONTEXT-FIRST:START -->"
_SCF_MARKER_END = "<!-- SCF:CONTEXT-FIRST:END -->"
_SCF_POLICY_BLOCK = f"""{_SCF_MARKER_START}
## ContextGO Context-First Policy (auto-injected by `contextgo setup`)

When the task involves existing code optimization/debugging, historical decisions,
cross-terminal handoff, or system diagnosis — **always prewarm context first**.

**Mandatory execution order:**
1. Run ``contextgo semantic "<topic>" --limit 3`` (memory files first)
2. If no hits: ``contextgo search "<keywords>" --limit 5``
3. Narrow scope from results before any ``ls`` / ``rg`` scan
4. **Forbidden**: blind scanning of ``~/``, ``/Volumes/*``, etc. without prewarm

When saving important findings: ``contextgo save --title "..." --content "..." --tags "..."``
{_SCF_MARKER_END}"""


def setup_claude_code() -> bool:
    """Configure Claude Code's ``~/.claude/settings.json`` with the prewarm hook.

    Merges the hook into existing settings without overwriting other config.
    Returns True if the hook was installed or already present.
    """
    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    hooks = existing.setdefault("hooks", {})
    upsub = hooks.setdefault("UserPromptSubmit", [])

    # Check if our hook is already registered.
    for entry in upsub:
        if isinstance(entry, dict) and "contextgo prewarm" in entry.get("command", ""):
            return True  # Already installed.

    upsub.append({"matcher": "", "command": "contextgo prewarm"})
    settings_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True


def _inject_scf_policy(filepath: Path) -> bool:
    """Inject the SCF context-first policy block into a Markdown file.

    Idempotent: skips injection if the marker is already present.
    Returns True if the file was modified or already has the policy.
    """
    if not filepath.parent.exists():
        return False

    content = ""
    if filepath.exists():
        try:
            content = filepath.read_text(encoding="utf-8")
        except OSError:
            return False

    if _SCF_MARKER_START in content:
        return True  # Already present.

    # Append policy block.
    updated = content.rstrip() + "\n\n" + _SCF_POLICY_BLOCK + "\n"
    try:
        filepath.write_text(updated, encoding="utf-8")
    except OSError:
        return False
    return True


def setup_codex() -> bool:
    """Inject SCF policy into ``~/.codex/AGENTS.md``."""
    return _inject_scf_policy(Path.home() / ".codex" / "AGENTS.md")


def setup_openclaw() -> bool:
    """Inject SCF policy into ``~/.openclaw/workspace/AGENTS.md``."""
    return _inject_scf_policy(Path.home() / ".openclaw" / "workspace" / "AGENTS.md")


def setup_claude_md() -> bool:
    """Inject SCF policy into ``~/.claude/CLAUDE.md``."""
    return _inject_scf_policy(Path.home() / ".claude" / "CLAUDE.md")


def setup_all() -> dict[str, bool]:
    """Detect and configure all supported AI coding tools.

    Returns a dict mapping tool name → success boolean.
    """
    results: dict[str, bool] = {}

    # Claude Code — hook-based (strongest: system-enforced prewarm).
    results["Claude Code (hook)"] = setup_claude_code()

    # Claude Code — CLAUDE.md policy (fallback for tools that ignore hooks).
    results["Claude Code (policy)"] = setup_claude_md()

    # Codex CLI.
    results["Codex CLI"] = setup_codex()

    # OpenClaw.
    results["OpenClaw"] = setup_openclaw()

    return results
