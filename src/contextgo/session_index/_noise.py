"""Noise filtering configuration and helpers for ContextGO session index."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Pre-compiled whitespace normalizer shared across the package.
_WHITESPACE_RE = re.compile(r"\s+")


def _load_noise_config() -> dict[str, list[str]]:
    """Load noise-filter marker tables from ``config/noise_markers.json``.

    The config file is resolved relative to this script's parent directory so
    the path works both in-repo and after pip-install.  Falls back to empty
    lists when the config file is absent.
    """
    _keys = (
        "search_noise_markers",
        "native_noise_markers",
        "text_noise_markers",
        "text_noise_lower_markers",
        "noise_prefixes",
    )
    # Search multiple candidate locations for the config file:
    # 1. Package data: src/contextgo/data/ (works after pip-install)
    # 2. Repository root: config/ (works during development)
    _here = Path(__file__).resolve().parent.parent
    candidates = [
        _here / "data" / "noise_markers.json",                  # pip-installed (package data)
        _here.parent.parent / "config" / "noise_markers.json",  # in-repo: config/ at project root
    ]
    for config_path in candidates:
        if config_path.exists():
            with open(config_path) as fh:
                data = json.load(fh)
            return {k: list(data.get(k, [])) for k in _keys}
    return {k: [] for k in _keys}


# Lazily loaded on first use; None means not yet loaded.
_NOISE_CONFIG: dict[str, list[str]] | None = None


def _get_noise_config() -> dict[str, list[str]]:
    """Return the noise config dict, loading it on first call (lazy initializer)."""
    global _NOISE_CONFIG
    if _NOISE_CONFIG is None:
        _NOISE_CONFIG = _load_noise_config()
    return _NOISE_CONFIG


# Module-level sentinel tuples; populated lazily via _ensure_noise_markers().
SEARCH_NOISE_MARKERS: tuple[str, ...] = ()
NATIVE_NOISE_MARKERS: tuple[str, ...] = ()
_NOISE_TEXT_MARKERS: tuple[str, ...] = ()
_NOISE_TEXT_LOWER_MARKERS: tuple[str, ...] = ()
_noise_markers_initialized: bool = False


def _ensure_noise_markers() -> None:
    """Populate noise-marker module globals on first call (idempotent)."""
    global SEARCH_NOISE_MARKERS, NATIVE_NOISE_MARKERS
    global _NOISE_TEXT_MARKERS, _NOISE_TEXT_LOWER_MARKERS, _noise_markers_initialized
    if _noise_markers_initialized:
        return
    cfg = _get_noise_config()
    SEARCH_NOISE_MARKERS = tuple(cfg["search_noise_markers"])
    NATIVE_NOISE_MARKERS = tuple(cfg["native_noise_markers"])
    _NOISE_TEXT_MARKERS = tuple(cfg["text_noise_markers"])
    _NOISE_TEXT_LOWER_MARKERS = tuple(cfg["text_noise_lower_markers"])
    _noise_markers_initialized = True

STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "what",
        "when",
        "where",
        "which",
        "who",
        "how",
        "please",
        "search",
        "session",
        "history",
        "continue",
        "find",
    }
)

# Chinese stopwords are only applied when the query contains enough
# non-stop CJK tokens (see ``build_query_terms``).  This avoids
# over-filtering short Chinese queries like "搜索方案" where every
# token would otherwise be discarded.
CJK_STOPWORDS: frozenset[str] = frozenset(
    {
        "继续",
        "搜索",
        "终端",
        "方案",
        "项目",
        "历史",
        "会话",
        "相关",
        "那个",
        "这个",
    }
)


def _is_noise_text(text: str) -> bool:
    """Return ``True`` if *text* should be excluded from the session index."""
    _ensure_noise_markers()
    compact = _WHITESPACE_RE.sub(" ", str(text or "")).strip()
    if not compact:
        return True
    if any(marker in compact for marker in _NOISE_TEXT_MARKERS):
        return True
    if compact.count("SKILL.md") >= 3:
        return True
    compact_lower = compact.lower()
    if any(marker in compact_lower for marker in _NOISE_TEXT_LOWER_MARKERS):
        return True
    if "已预热" in compact and "样本定位" in compact:
        return True
    return "主链不再是瓶颈" in compact and "native 搜索结果质量" in compact


def _search_noise_penalty(*parts: str) -> int:
    """Compute a numeric noise penalty for a candidate search result.

    Higher penalties push results further down the ranking.
    """
    _ensure_noise_markers()
    haystack = "\n".join(str(part or "") for part in parts).lower()
    penalty = 0

    marker_hits = sum(1 for marker in SEARCH_NOISE_MARKERS if marker in haystack)
    if marker_hits:
        penalty += min(120, marker_hits * 60)

    if "/skills/" in haystack or "skills-repo" in haystack:
        penalty += 120
    if "guardian_truncated" in haystack:
        penalty += 60
    if "chunk id:" in haystack or "wall time:" in haystack:
        penalty += 120

    lines = [line.strip() for line in haystack.splitlines() if line.strip()]
    short_token_lines = sum(
        1 for line in lines if len(line) <= 40 and " " not in line and line.count("/") < 2 and line.count("-") <= 3
    )
    if short_token_lines >= 8:
        penalty += 200

    if "drwx" in haystack or "rwxr-xr-x" in haystack or "\ntotal " in haystack:
        penalty += 200

    meta_terms = ("notebooklm", "search", "session_index", "native-scan")
    if all(term in haystack for term in meta_terms):
        penalty += 240
    if ("我先" in haystack or "我继续" in haystack) and ("native-scan" in haystack or "session_index" in haystack):
        penalty += 240

    return penalty


def _is_current_repo_meta_result(title: str, content: str, file_path: str) -> bool:  # noqa: ARG001
    """Return ``True`` if this result is meta-commentary about the current repo."""
    current_repo = str(Path.cwd().resolve())
    if title != current_repo:
        return False
    compact = _WHITESPACE_RE.sub(" ", str(content or "")).strip()
    if not compact:
        return True
    meta_markers = (
        "写集仅限",
        "改动文件：",
        "改动文件:",
        "**改动文件**",
        "核心变化：",
        "核心变化:",
        "建议验证命令：",
        "建议验证命令:",
        "职责只限测试",
        "测试集使用",
        "全平台对话测试集",
        "artifacts/testsets/dataset_",
        "仓库：",
        "你负责",
        "变更概览",
        "改动概览",
        "我先",
        "我继续",
        "我现在",
        "已收到任务",
        "已变更概览",
        "search NotebookLM",
        "native-scan",
        "session_index",
    )
    return any(marker in compact for marker in meta_markers)


def _looks_like_path_only_content(title: str, content: str) -> bool:
    """Return ``True`` if the document content is nothing but a filesystem path."""
    title_clean = _WHITESPACE_RE.sub(" ", str(title or "")).strip()
    content_clean = _WHITESPACE_RE.sub(" ", str(content or "")).strip()
    if not title_clean or not content_clean:
        return False
    if title_clean != content_clean:
        return False
    return "/" in content_clean and not any(ch in content_clean for ch in ("。", "，", ".", ":"))
