"""Standalone local session index for ContextGO.

Indexes Codex, Claude, and shell session files into a SQLite database and
provides ranked full-text search over their content.  All persistent state
lives under the storage root (default ``~/.contextgo``); no hardcoded paths.

Public API (stable):
    get_session_db_path() -> Path
    ensure_session_db() -> Path
    sync_session_index(force: bool = False) -> dict[str, int]
    build_query_terms(query: str) -> list[str]
    format_search_results(query, *, search_type, limit, literal) -> str
    health_payload() -> dict[str, Any]
    lookup_session_by_id(...) -> list[dict[str, Any]]
    SESSION_DB_PATH_ENV  -- env-var name for DB path override
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    from context_config import env_int
except ImportError:  # pragma: no cover
    from contextgo.context_config import env_int  # type: ignore[import-not-found]

# ── Configuration (module-level, needed by submodules) ─────────────────────

MAX_CONTENT_CHARS: int = env_int("CONTEXTGO_SESSION_MAX_CONTENT_CHARS", default=24000, minimum=4000)

# ── Re-exports from submodules (backward-compatible public API) ────────────

from ._noise import (  # noqa: E402
    CJK_STOPWORDS,
    NATIVE_NOISE_MARKERS,
    SEARCH_NOISE_MARKERS,
    STOPWORDS,
    _NOISE_TEXT_LOWER_MARKERS,
    _NOISE_TEXT_MARKERS,
    _WHITESPACE_RE,
    _ensure_noise_markers,
    _get_noise_config,
    _is_current_repo_meta_result,
    _is_noise_text,
    _load_noise_config,
    _looks_like_path_only_content,
    _noise_markers_initialized,
    _search_noise_penalty,
)
from ._parsers import (  # noqa: E402
    SessionDocument,
    _collect_content_text,
    _finish_session_doc,
    _iso_to_epoch,
    _iter_jsonl_objects,
    _make_flat_doc,
    _parse_claude_session,
    _parse_codex_session,
    _parse_generic_session_jsonl,
    _parse_history_jsonl,
    _parse_shell_history,
    _parse_source,
    _truncate,
)
from ._db import (  # noqa: E402
    SESSION_DB_PATH_ENV,
    _DDL_FTS_TRIGGERS,
    _DDL_INDEXES,
    _DDL_SESSION_DOCUMENTS,
    _DDL_SESSION_DOCUMENTS_FTS,
    _DDL_SESSION_META,
    _SQL_ALL_PATHS,
    _SQL_CHECK_CHANGED,
    _SQL_COUNT_DOCS,
    _SQL_DELETE_DOC,
    _SQL_MAX_EPOCH,
    _SQL_META_GET,
    _SQL_META_SET,
    _SQL_UPSERT_DOC,
    _check_fts5_available,
    _meta_get,
    _meta_set,
    _open_db,
    _retry_commit,
    _retry_sqlite,
    _retry_sqlite_many,
    ensure_session_db,
    get_session_db_path,
)
from ._sync import (  # noqa: E402
    _BATCH_COMMIT_SIZE,
    _SOURCE_CACHE,
    EXPERIMENTAL_SYNC_BACKEND,
    SESSION_INDEX_SCHEMA_VERSION,
    SOURCE_CACHE_TTL_SEC,
    SYNC_MIN_INTERVAL_SEC,
    _iter_sources,
    _try_sync,
    _update_source_cache,
    sync_session_index,
)
from ._search import (  # noqa: E402
    SOURCE_WEIGHT,
    _CJK_CHAR_RE,
    _SEARCH_CACHE_MAX_ENTRIES,
    _SEARCH_RESULT_CACHE,
    _SEARCH_RESULT_CACHE_TTL,
    _SNIPPET_MAX_CHARS,
    _build_snippet,
    _cache_put_results,
    _cjk_safe_boundary,
    _compact_snippet,
    _enrich_native_rows,
    _fetch_rows,
    _fetch_session_docs_by_paths,
    _fts5_search_rows,
    _highlight_query,
    _home,
    _native_search_rows,
    _normalize_file_path,
    _rank_rows,
    _recency_bonus,
    _score_term_frequency,
    _search_rows,
    build_query_terms,
)

# Re-export EXPERIMENTAL_SEARCH_BACKEND from the original module-level location.
EXPERIMENTAL_SEARCH_BACKEND: str = os.environ.get("CONTEXTGO_EXPERIMENTAL_SEARCH_BACKEND", "").strip().lower()

# ── Public API ─────────────────────────────────────────────────────────────

_VALID_SEARCH_TYPES = frozenset({"all", "codex", "claude", "shell", "event", "session", "turn", "content"})


def lookup_session_by_id(
    session_id_prefix: str,
    *,
    limit: int = 10,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Look up session documents by session_id prefix.

    Returns a list of dicts matching the ``_search_rows`` output contract.
    """
    db = Path(db_path) if db_path else ensure_session_db()
    with _open_db(db) as conn:
        rows = conn.execute(
            "SELECT source_type, session_id, title, file_path, "
            "created_at, created_at_epoch, content "
            "FROM session_documents WHERE LOWER(session_id) LIKE ? "
            "ORDER BY created_at_epoch DESC LIMIT ?",
            (session_id_prefix.lower() + "%", limit),
        ).fetchall()
    return [
        {
            "source_type": r["source_type"],
            "session_id": r["session_id"],
            "title": r["title"],
            "file_path": r["file_path"],
            "created_at": r["created_at"],
            "created_at_epoch": r["created_at_epoch"],
            "snippet": (r["content"] or "")[:240].strip(),
        }
        for r in rows
    ]


def format_search_results(
    query: str,
    *,
    search_type: str = "all",
    limit: int = 10,
    literal: bool = False,
) -> str:
    """Format session search results as a human-readable multi-line string.

    *search_type* filters results by source type (e.g. ``"codex"``, ``"claude"``).
    ``"all"`` returns every source type.
    """
    effective_limit = limit * 5 if (search_type != "all" and search_type in _VALID_SEARCH_TYPES) else limit
    results = _search_rows(query, limit=effective_limit, literal=literal)
    if search_type != "all" and search_type in _VALID_SEARCH_TYPES:
        results = [r for r in results if r.get("source_type", "").startswith(search_type)]
    results = results[:limit]
    if not results:
        return "No matches found in local session index."

    lines = [f"Found {len(results)} sessions (local index):"]
    for idx, row in enumerate(results, 1):
        title = _highlight_query(row["title"], query)
        snippet = _highlight_query(_compact_snippet(row["snippet"]), query)
        lines.append(f"[{idx}] {row['created_at'][:10]} | {row['session_id']} | {row['source_type']}")
        lines.append(f"    {title}")
        lines.append(f"    File: {row['file_path']}")
        lines.append(f"    > {snippet}")
    return "\n".join(lines)


def health_payload() -> dict[str, Any]:
    """Return a health-check dict for the session index subsystem."""
    sync_info = _try_sync()
    db_path = ensure_session_db()
    with _open_db(db_path) as conn:
        total = _retry_sqlite(conn, _SQL_COUNT_DOCS).fetchone()[0]
        latest = _retry_sqlite(conn, _SQL_MAX_EPOCH).fetchone()[0]
    return {
        "session_index_db_exists": db_path.exists(),
        "session_index_db": str(db_path),
        "total_sessions": int(total or 0),
        "latest_epoch": int(latest or 0),
        "sync": sync_info,
    }


__all__ = [
    "SessionDocument",
    "build_query_terms",
    "ensure_session_db",
    "format_search_results",
    "get_session_db_path",
    "health_payload",
    "lookup_session_by_id",
    "sync_session_index",
]
