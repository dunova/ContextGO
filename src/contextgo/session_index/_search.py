"""Search, ranking, and snippet generation for ContextGO session index."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._noise import (
    CJK_STOPWORDS,
    NATIVE_NOISE_MARKERS,
    STOPWORDS,
    _WHITESPACE_RE,
    _ensure_noise_markers,
    _is_current_repo_meta_result,
    _looks_like_path_only_content,
    _search_noise_penalty,
)

_logger = logging.getLogger(__name__)

# Pre-compiled CJK character matcher used in snippet and scoring helpers.
_CJK_CHAR_RE: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")

_SNIPPET_MAX_CHARS = 120

SOURCE_WEIGHT: dict[str, int] = {
    "codex_session": 40,
    "claude_session": 40,
    "opencode_session": 36,
    "kilo_session": 36,
    "openclaw_session": 36,
    "codex_history": 8,
    "claude_history": 8,
    "opencode_history": 6,
    "kilo_history": 6,
    "shell_zsh": 2,
    "shell_bash": 2,
}

# ---------------------------------------------------------------------------
# In-process search result cache (TTL-based)
# ---------------------------------------------------------------------------
# Cache TTL in seconds.  Set CONTEXTGO_SESSION_SEARCH_CACHE_TTL=0 to disable.
try:
    _SEARCH_RESULT_CACHE_TTL: int = int(os.environ.get("CONTEXTGO_SESSION_SEARCH_CACHE_TTL", "5") or "5")
except (ValueError, TypeError):
    _SEARCH_RESULT_CACHE_TTL: int = 5
# Mapping of cache_key -> (expiry_monotonic_float, results_list)
_SEARCH_RESULT_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_SEARCH_CACHE_MAX_ENTRIES: int = 64


def _cache_put_results(cache_key: str, results: list[dict[str, Any]]) -> None:
    """Insert *results* into the search result cache, evicting stale/excess entries."""
    if _SEARCH_RESULT_CACHE_TTL <= 0:
        return
    if len(_SEARCH_RESULT_CACHE) >= _SEARCH_CACHE_MAX_ENTRIES:
        _now = time.monotonic()
        expired = [k for k, (exp, _) in _SEARCH_RESULT_CACHE.items() if exp <= _now]
        for k in expired:
            del _SEARCH_RESULT_CACHE[k]
        while len(_SEARCH_RESULT_CACHE) >= _SEARCH_CACHE_MAX_ENTRIES:
            _SEARCH_RESULT_CACHE.pop(next(iter(_SEARCH_RESULT_CACHE)))
    _SEARCH_RESULT_CACHE[cache_key] = (time.monotonic() + _SEARCH_RESULT_CACHE_TTL, results)


# Text helpers


def _home() -> Path:
    """Return the current user's home directory.

    Isolated as a function so tests can monkeypatch it without affecting
    ``Path.home`` globally.
    """
    return Path.home()


def _normalize_file_path(path: Path) -> str:
    """Return the resolved, absolute string form of *path*.

    Falls back to the un-resolved string if ``Path.resolve`` raises.
    """
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _compact_snippet(text: str, max_chars: int = _SNIPPET_MAX_CHARS) -> str:
    """Collapse internal whitespace and truncate *text* to *max_chars* with an ellipsis."""
    clean = _WHITESPACE_RE.sub(" ", str(text or "")).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "\u2026"


def _highlight_query(text: str, query: str) -> str:
    """Highlight *query* terms in *text* using ANSI bold (case-insensitive).

    Only applies when stdout is a TTY.  Falls back to plain text otherwise.
    """
    if not sys.stdout.isatty() or not query.strip():
        return text
    _BOLD = "\033[1m"
    _RESET = "\033[0m"
    for term in query.split():
        if len(term) < 2:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        text = pattern.sub(lambda m: f"{_BOLD}{m.group()}{_RESET}", text)
    return text


# Query decomposition


def build_query_terms(query: str) -> list[str]:
    """Decompose a query into at most 8 deduplicated, stopword-filtered search terms.

    CJK stopwords are only applied when the query yields at least one
    non-CJK-stop term, preventing short Chinese queries (e.g. "搜索方案")
    from being entirely discarded.
    """
    raw = (query or "").strip()
    if not raw:
        return []

    terms: list[str] = []
    seen: set[str] = set()
    # Collect CJK tokens that matched a CJK stopword so we can add them
    # back if the final term list would otherwise be empty.
    cjk_stopped: list[str] = []

    def _add(term: str) -> None:
        clean = term.strip().strip("\"'")
        if not clean or len(clean) < 2:
            return
        lower = clean.lower()
        if lower in seen or lower in STOPWORDS:
            return
        if lower in CJK_STOPWORDS:
            if lower not in seen:
                cjk_stopped.append(clean)
                seen.add(lower)
            return
        seen.add(lower)
        terms.append(clean)

    date_match = re.fullmatch(r"\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*", raw)
    if date_match:
        y, m, d = date_match.groups()
        _add(f"{y}-{int(m):02d}-{int(d):02d}")
        _add(f"{y}{int(m):02d}{int(d):02d}")

    for token in re.findall(r"(?:~?/[A-Za-z0-9._/-]+)", raw):
        _add(Path(token).name or token)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9._-]{2,40}", raw):
        if token.lower() not in STOPWORDS and token.lower() not in CJK_STOPWORDS:
            _add(token)
    for token in re.findall(r"[\u4e00-\u9fff]{2,12}", raw):
        _add(token)
        normalized = token.lstrip("的了将把从向在对与和及并或再先后")
        if normalized != token or len(normalized) >= 6:
            if len(normalized) >= 2:
                _add(normalized[:2])
                _add(normalized[-2:])
            if len(normalized) >= 4:
                _add(normalized[:4])
                _add(normalized[-4:])

    if not terms:
        # Re-add CJK-stopped tokens when no other terms survived filtering;
        # fall back to the raw query as a last resort.
        if cjk_stopped:
            terms.extend(cjk_stopped)
        else:
            # Bypass stopword checks — the raw query itself is the only signal.
            clean = raw.strip().strip("\"'")
            if clean and len(clean) >= 2 and clean.lower() not in seen:
                seen.add(clean.lower())
                terms.append(clean)
    return terms[:8]


# Snippet generation


def _cjk_safe_boundary(text: str, pos: int, direction: int) -> int:
    """Adjust *pos* so it does not split the middle of a CJK character run.

    *direction* should be -1 (move left) for a start boundary or +1 (move
    right) for an end boundary.  The function walks at most 4 characters in
    the given direction until it finds a non-CJK character or a whitespace
    boundary.
    """
    length = len(text)
    adjusted = max(0, min(pos, length))
    for _ in range(4):
        check = adjusted + (direction if direction == 1 else 0) - (1 if direction == -1 else 0)
        if check < 0 or check >= length:
            break
        if _CJK_CHAR_RE.match(text[check]):
            adjusted += direction
            adjusted = max(0, min(adjusted, length))
        else:
            break
    return adjusted


def _build_snippet(text: str, terms: list[str], radius: int = 80) -> str:
    """Extract a context window around the best term match in *text*.

    Snippet selection strategy (in priority order):
      1. Find all candidate windows (one per term occurrence) and pick the
         window that covers the *most distinct query terms* (coverage scoring).
      2. Among windows with equal coverage, prefer those containing a
         conclusion marker (最终, 结论, …) and those closer to the start.
      3. If no term matches, fall back to known summary headings or the
         first ``2*radius`` characters.

    CJK boundary handling: start/end positions are nudged outward to avoid
    splitting a contiguous run of CJK characters.
    """
    compact = _WHITESPACE_RE.sub(" ", text or "").strip()
    if not compact:
        return ""
    lower = compact.lower()
    conclusion_markers = ("最终", "结论", "交付", "已完成", "核心")
    lower_terms = [t.lower() for t in terms if t]

    # Detect CJK query so we apply boundary adjustment selectively.
    is_cjk_query = any(_CJK_CHAR_RE.search(t) for t in lower_terms)

    # --- Phase 1: collect candidate windows ---
    # Each candidate is (start, end, matched_term_lower).
    candidates: list[tuple[int, int, str]] = []
    for term_lower in lower_terms:
        start = 0
        while True:
            pos = lower.find(term_lower, start)
            if pos < 0:
                break
            w_start = max(0, pos - radius)
            w_end = min(len(compact), pos + len(term_lower) + radius)
            if is_cjk_query:
                w_start = _cjk_safe_boundary(compact, w_start, -1)
                w_end = _cjk_safe_boundary(compact, w_end, 1)
            candidates.append((w_start, w_end, term_lower))
            start = pos + max(1, len(term_lower))

    if not candidates:
        # Fallback: summary headings.
        for marker in ("最终交付", "变更概览", "核心变化", "改动文件", "建议验证", "结论", "Summary"):
            pos = compact.find(marker)
            if pos >= 0:
                fb_start = max(0, pos - radius // 2)
                fb_end = min(len(compact), pos + len(marker) + radius + radius // 2)
                return compact[fb_start:fb_end]
        return compact[: radius * 2]

    # --- Phase 2: score each candidate window by coverage ---
    best_window: tuple[int, int] = candidates[0][:2]
    best_coverage = -1
    best_has_conclusion = False
    best_pos = len(compact)

    for w_start, w_end, _ in candidates:
        window_lower = lower[w_start:w_end]
        coverage = sum(1 for t in lower_terms if t in window_lower)
        has_conclusion = any(m in window_lower for m in conclusion_markers)
        # Higher coverage wins; tie-break: conclusion markers > earlier position.
        if (
            coverage > best_coverage
            or (coverage == best_coverage and has_conclusion and not best_has_conclusion)
            or (coverage == best_coverage and has_conclusion == best_has_conclusion and w_start < best_pos)
        ):
            best_coverage = coverage
            best_has_conclusion = has_conclusion
            best_pos = w_start
            best_window = (w_start, w_end)

    return compact[best_window[0] : best_window[1]]


# Native backend search


def _get_context_native() -> Any:
    """Lazily import and return the context_native module."""
    try:
        import context_native as _cn  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover
        from contextgo import context_native as _cn  # type: ignore[import-not-found]
    return _cn


def _native_search_rows(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Run a query against the native (Rust/Go) backend.

    Returns an empty list when the backend is not configured or fails.
    """
    _ensure_noise_markers()
    if not query.strip():
        return []
    backend = os.environ.get("CONTEXTGO_EXPERIMENTAL_SEARCH_BACKEND", "").strip().lower()
    if backend not in {"rust", "go"}:
        return []

    try:
        _cn = _get_context_native()
        result = _cn.run_native_scan(
            backend=backend,
            threads=4,
            query=query,
            json_output=True,
            release=(backend == "rust"),
            timeout=120,
        )
    except (OSError, RuntimeError):
        return []

    if result.returncode != 0:
        return []

    max_results = max(1, min(limit, 100))
    query_lower = query.lower().strip()
    rows: list[dict[str, Any]] = []

    for item in _cn.extract_matches(result):
        snippet = str(item.get("snippet", "") or "")
        snippet_lower = snippet.lower()
        if not snippet_lower:
            continue
        if any(marker in snippet_lower for marker in NATIVE_NOISE_MARKERS):
            continue
        if query_lower and query_lower not in snippet_lower:
            continue
        rows.append(
            {
                "source_type": item.get("source", "native_session"),
                "session_id": item.get("session_id", ""),
                "title": item.get("path", ""),
                "file_path": item.get("path", ""),
                "created_at": "",
                "created_at_epoch": 0,
                "snippet": snippet,
            }
        )
        if len(rows) >= max_results:
            break

    return rows


def _fetch_session_docs_by_paths(conn: sqlite3.Connection, file_paths: Iterable[str]) -> dict[str, sqlite3.Row]:
    """Batch-fetch ``session_documents`` rows by a collection of file paths."""
    from ._db import _retry_sqlite

    unique_paths: list[str] = []
    seen: set[str] = set()
    for raw_path in file_paths:
        if not raw_path:
            continue
        path_str = _normalize_file_path(Path(str(raw_path)))
        if path_str not in seen:
            seen.add(path_str)
            unique_paths.append(path_str)

    if not unique_paths:
        return {}

    placeholders = ",".join("?" for _ in unique_paths)
    sql = f"SELECT * FROM session_documents WHERE file_path IN ({placeholders})"
    return {str(row["file_path"]): row for row in _retry_sqlite(conn, sql, tuple(unique_paths))}


def _enrich_native_rows(
    rows: list[dict[str, Any]],
    conn: sqlite3.Connection,
    terms: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Augment native-backend rows with metadata from the local SQLite index."""
    max_results = max(1, min(limit, 100))
    docs = _fetch_session_docs_by_paths(conn, (row.get("file_path") for row in rows if row.get("file_path")))
    enriched: list[dict[str, Any]] = []

    for row in rows:
        enriched_row = dict(row)
        raw_fp = row.get("file_path") or ""
        file_path = _normalize_file_path(Path(str(raw_fp))) if raw_fp else ""
        doc = docs.get(file_path)

        if doc:
            enriched_row["source_type"] = doc["source_type"]
            enriched_row["session_id"] = doc["session_id"]
            enriched_row["title"] = doc["title"]
            enriched_row["created_at"] = doc["created_at"]
            enriched_row["created_at_epoch"] = doc["created_at_epoch"]
            snippet_source = doc["content"]
        else:
            snippet_source = row.get("snippet") or ""
            enriched_row.setdefault("created_at", "")
            enriched_row.setdefault("created_at_epoch", 0)

        snippet = _build_snippet(snippet_source, terms)
        enriched_row["snippet"] = snippet or str(snippet_source or row.get("snippet") or "")
        enriched.append(enriched_row)

        if len(enriched) >= max_results:
            break

    return enriched


# FTS5 and LIKE search


def _fts5_search_rows(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
) -> list[sqlite3.Row]:
    """Search the FTS5 virtual table using BM25 ranking.

    Builds a simple FTS5 MATCH expression from *query*.  Each whitespace-
    separated token is treated as a prefix match (``token*``) which works
    well for both ASCII and CJK text (CJK characters have no word boundaries
    so individual character n-grams match naturally).

    Returns an empty list when the FTS5 table does not exist, when *query* is
    empty, or when the query fails for any reason.
    """
    from ._db import _check_fts5_available, _retry_sqlite

    if not query.strip():
        return []

    def _build_fts_query(raw: str) -> str:
        """Convert *raw* to a safe FTS5 MATCH expression."""
        tokens = raw.split()
        parts: list[str] = []
        for tok in tokens:
            if not tok:
                continue
            safe = tok.replace('"', '""')
            parts.append(f'"{safe}"*')
        return " ".join(parts) if parts else '""'

    if not _check_fts5_available(conn):
        return []

    fts_query = _build_fts_query(query)
    row_limit = max(1, min(limit * 10, 500))

    try:
        sql = (
            "SELECT sd.* FROM session_documents sd "
            "JOIN session_documents_fts fts ON sd.rowid = fts.rowid "
            "WHERE session_documents_fts MATCH ? "
            "ORDER BY bm25(session_documents_fts, 10.0, 5.0, 1.0) "
            "LIMIT ?"
        )
        return _retry_sqlite(conn, sql, (fts_query, row_limit)).fetchall()
    except sqlite3.OperationalError as exc:
        _logger.debug("FTS5 search failed, falling back to LIKE: %s", exc)
        return []


def _fetch_rows(
    conn: sqlite3.Connection,
    active_terms: list[str],
    row_limit: int = 200,
) -> list[sqlite3.Row]:
    """Build and execute a LIKE-based SQL query for the given terms."""
    from ._db import _retry_sqlite

    where_parts: list[str] = []
    args: list[Any] = []
    for term in active_terms:
        like_term = f"%{term.lower()}%"
        where_parts.append(
            "(title LIKE ? COLLATE NOCASE OR content LIKE ? COLLATE NOCASE OR file_path LIKE ? COLLATE NOCASE)"
        )
        args.extend([like_term, like_term, like_term])
    where_clause = f"WHERE {' OR '.join(where_parts)}" if where_parts else ""
    sql = f"SELECT * FROM session_documents {where_clause} ORDER BY created_at_epoch DESC, file_path DESC LIMIT ?"
    args.append(max(1, int(row_limit)))
    return _retry_sqlite(conn, sql, args).fetchall()


# Scoring


def _score_term_frequency(text: str, terms: list[str]) -> float:
    """Compute a TF-IDF-inspired term-frequency score for *text* against *terms*."""
    if not text or not terms:
        return 0.0
    lower = text.lower()
    total = 0.0
    for term in terms:
        term_lower = term.lower()
        if not term_lower:
            continue
        count = lower.count(term_lower)
        if count:
            total += count * (len(term_lower) ** 0.5)
    return min(total, 100.0)


def _recency_bonus(created_at_epoch: int) -> float:
    """Return a mild logarithmic recency bonus in the range [0, 20]."""
    age_secs = max(0, int(time.time()) - int(created_at_epoch))
    age_days = age_secs / 86400.0
    return max(0.0, 20.0 - math.log2(1.0 + age_days) * 3.0)


def _rank_rows(
    candidate_rows: list[sqlite3.Row],
    active_terms: list[str],
    *,
    skip_cwd_title: bool = False,
) -> list[tuple[int, sqlite3.Row]]:
    """Score and filter candidate rows, returning those with positive scores."""
    ranked: list[tuple[int, sqlite3.Row]] = []
    cwd_str = str(Path.cwd().resolve())

    lower_terms = [t.lower() for t in active_terms if t]
    exact_phrase = " ".join(lower_terms)
    has_cjk = any(_CJK_CHAR_RE.search(t) for t in lower_terms)

    cjk_bigrams: list[str] = []
    if has_cjk:
        for term in lower_terms:
            cjk_chars = _CJK_CHAR_RE.findall(term)
            for i in range(len(cjk_chars) - 1):
                bg = cjk_chars[i] + cjk_chars[i + 1]
                if bg not in cjk_bigrams:
                    cjk_bigrams.append(bg)

    for row in candidate_rows:
        if skip_cwd_title and row["title"] == cwd_str:
            continue
        if _is_current_repo_meta_result(row["title"], row["content"], row["file_path"]):
            continue

        title_lower = str(row["title"] or "").lower()
        content_lower = str(row["content"] or "").lower()
        fp_lower = str(row["file_path"] or "").lower()
        haystack = f"{title_lower}\n{content_lower}\n{fp_lower}"

        score: float = SOURCE_WEIGHT.get(str(row["source_type"]), 1)

        for term_lower in lower_terms:
            if term_lower in haystack:
                score += max(4, len(term_lower) * len(term_lower))
                score += _score_term_frequency(content_lower, [term_lower])
                if term_lower in title_lower:
                    score += max(4, len(term_lower) * len(term_lower)) * 2

        if exact_phrase and len(exact_phrase) >= 2 and exact_phrase in haystack:
            score += 50

        if cjk_bigrams:
            bigram_hits = sum(1 for bg in cjk_bigrams if bg in haystack)
            score += bigram_hits * 8

        score += _recency_bonus(int(row["created_at_epoch"] or 0))

        if _looks_like_path_only_content(row["title"], row["content"]):
            score -= 180
        score -= _search_noise_penalty(row["title"], row["content"], row["file_path"])

        if score > 0:
            ranked.append((int(score), row))
    return ranked


def _search_rows(query: str, limit: int = 10, literal: bool = False) -> list[dict[str, Any]]:
    """Execute a ranked search against the local session index."""
    from ._db import _check_fts5_available, _open_db, ensure_session_db

    max_results = max(1, min(limit, 100))
    db_path = ensure_session_db()

    cache_key = json.dumps([str(db_path), query, max_results, literal], ensure_ascii=False)

    if _SEARCH_RESULT_CACHE_TTL > 0:
        now_mono = time.monotonic()
        cached = _SEARCH_RESULT_CACHE.get(cache_key)
        if cached is not None and cached[0] > now_mono:
            return list(cached[1])

    from ._sync import _try_sync
    _try_sync()

    with _open_db(db_path) as conn:
        terms = [query.strip()] if literal else build_query_terms(query)
        literal_fallback = False

        # --- Vector hybrid search backend ---
        exp_backend = os.environ.get("CONTEXTGO_EXPERIMENTAL_SEARCH_BACKEND", "").strip().lower()
        if exp_backend == "vector":
            try:
                try:
                    from vector_index import (  # noqa: PLC0415
                        fetch_enriched_results,
                        get_vector_db_path,
                        hybrid_search_session,
                        vector_available,
                    )
                except ImportError:
                    from contextgo.vector_index import (  # type: ignore[import-not-found]  # noqa: PLC0415
                        fetch_enriched_results,
                        get_vector_db_path,
                        hybrid_search_session,
                        vector_available,
                    )

                if vector_available():
                    _vdb = get_vector_db_path(db_path)
                    ranked = hybrid_search_session(query, db_path, _vdb, limit=max_results)
                    if ranked:
                        results = fetch_enriched_results(ranked, db_path, query)
                        if results:
                            _cache_put_results(cache_key, results)
                            return results
            except Exception as exc:
                _logger.debug("_search_rows: vector search fallback: %s", exc)

        native_rows = _native_search_rows(query, limit=max_results)
        if native_rows:
            results = _enrich_native_rows(native_rows, conn, terms, max_results)
            _cache_put_results(cache_key, results)
            return results

        fts5_rows = _fts5_search_rows(conn, query, limit=max_results) if _check_fts5_available(conn) else []
        rows: list[sqlite3.Row] = fts5_rows if fts5_rows else _fetch_rows(conn, terms)
        if literal and not rows:
            expanded = build_query_terms(query)
            if expanded and expanded != terms:
                terms = expanded
                literal_fallback = True
                rows = _fetch_rows(conn, terms, row_limit=1000)

        ranked = _rank_rows(rows, terms, skip_cwd_title=literal_fallback)

        if literal and not ranked and rows:
            rows = _fetch_rows(conn, terms, row_limit=1000)
            ranked = _rank_rows(rows, terms, skip_cwd_title=literal_fallback)

        # Anchor-term fallback: find the 2 most-frequent terms and retry.
        if literal_fallback and not ranked and rows:
            term_freq: list[tuple[int, str]] = []
            for term in terms:
                term_lower = term.lower()
                freq = sum(
                    1 for row in rows if term_lower in f"{row['title']}\n{row['content']}\n{row['file_path']}".lower()
                )
                if freq > 0:
                    term_freq.append((freq, term))
            term_freq.sort(key=lambda item: (item[0], -len(item[1])))
            anchor_terms = [term for _, term in term_freq[:2]]
            if anchor_terms and anchor_terms != terms:
                terms = anchor_terms
                rows = _fetch_rows(conn, terms, row_limit=1000)
                ranked = _rank_rows(rows, terms, skip_cwd_title=literal_fallback)

        ranked.sort(key=lambda item: (item[0], item[1]["created_at_epoch"]), reverse=True)

        results = [
            {
                "source_type": row["source_type"],
                "session_id": row["session_id"],
                "title": row["title"],
                "file_path": row["file_path"],
                "created_at": row["created_at"],
                "created_at_epoch": row["created_at_epoch"],
                "snippet": _build_snippet(row["content"], terms),
            }
            for _, row in ranked[:max_results]
        ]

    _cache_put_results(cache_key, results)
    return results
