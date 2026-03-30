"""Index synchronisation logic for ContextGO session index."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from context_config import env_int
    from source_adapters import adapter_dirty_epoch, discover_index_sources, sync_all_adapters
except ImportError:  # pragma: no cover
    from contextgo.context_config import env_int  # type: ignore[import-not-found]
    from contextgo.source_adapters import (  # type: ignore[import-not-found]
        adapter_dirty_epoch,
        discover_index_sources,
        sync_all_adapters,
    )

from ._db import (
    _SQL_COUNT_DOCS,
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
from ._parsers import _parse_source
from ._search import _normalize_file_path

_logger = logging.getLogger(__name__)

SYNC_MIN_INTERVAL_SEC: int = env_int("CONTEXTGO_SESSION_SYNC_MIN_INTERVAL_SEC", default=15, minimum=0)
EXPERIMENTAL_SYNC_BACKEND: str = os.environ.get("CONTEXTGO_EXPERIMENTAL_SYNC_BACKEND", "").strip().lower()
SOURCE_CACHE_TTL_SEC: int = env_int("CONTEXTGO_SOURCE_CACHE_TTL_SEC", default=10, minimum=0)

#: Bump this string to force a full re-index on next sync.
SESSION_INDEX_SCHEMA_VERSION = "2026-03-26-search-noise-v5"

#: Number of upsert rows per SQLite transaction batch during sync.
_BATCH_COMMIT_SIZE: int = env_int("CONTEXTGO_INDEX_BATCH_SIZE", default=100, minimum=10)

# In-process cache for source-file discovery results.
_SOURCE_CACHE: dict[str, Any] = {"expires_at": 0.0, "items": [], "home": None}


def _home() -> Path:
    """Return the current user's home directory."""
    return Path.home()


def _get_context_native() -> Any:
    """Lazily import and return the context_native module."""
    try:
        import context_native as _cn  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover
        from contextgo import context_native as _cn  # type: ignore[import-not-found]
    return _cn


def _iter_sources() -> list[tuple[str, Path]]:
    """Return cached ``(source_type, path)`` pairs for all discoverable sources."""
    now = time.monotonic()
    current_home = str(_home())
    if (
        SOURCE_CACHE_TTL_SEC > 0
        and _SOURCE_CACHE.get("expires_at", 0.0) > now
        and _SOURCE_CACHE.get("items")
        and _SOURCE_CACHE.get("home") == current_home
    ):
        return list(_SOURCE_CACHE["items"])

    native_backend = EXPERIMENTAL_SYNC_BACKEND
    if native_backend in {"rust", "go"}:
        try:
            _cn = _get_context_native()
            result = _cn.run_native_scan(
                backend=native_backend,
                threads=4,
                json_output=True,
                release=(native_backend == "rust"),
                timeout=180,
            )
            if result.returncode == 0:
                items: list[tuple[str, Path]] = _cn.inventory_items(result)
                if items:
                    _update_source_cache(items, now, current_home)
                    return items
        except (OSError, RuntimeError):
            pass

    home = Path(current_home)
    discovered = discover_index_sources(home)

    _update_source_cache(discovered, now, current_home)
    return discovered


def _update_source_cache(items: list[tuple[str, Path]], now: float, home: str) -> None:
    """Write discovery results into the in-process source cache."""
    if SOURCE_CACHE_TTL_SEC > 0:
        _SOURCE_CACHE["items"] = list(items)
        _SOURCE_CACHE["expires_at"] = now + SOURCE_CACHE_TTL_SEC
        _SOURCE_CACHE["home"] = home


def _try_sync(force: bool = False) -> dict[str, int]:
    """Best-effort sync that degrades gracefully in read-only environments."""
    db_path = get_session_db_path()
    check_path = db_path if db_path.exists() else db_path.parent
    if not os.access(check_path, os.W_OK):
        _logger.warning(
            "_try_sync: database path %s is not writable — skipping sync "
            "(read-only environment); search/health will use existing index",
            check_path,
        )
        return {}
    try:
        return sync_session_index(force=force)
    except Exception as exc:
        _logger.warning(
            "_try_sync: sync failed (%s) — continuing with existing index",
            exc,
        )
        return {}


def sync_session_index(force: bool = False) -> dict[str, int]:
    """Scan source files and upsert changed documents (mtime+size based).

    Forces full re-index when the schema version changes or *force* is True.
    """
    _t_start = time.monotonic()
    db_path = ensure_session_db()
    added = updated = removed = scanned = 0
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    seen_paths: set[str] = set()

    with _open_db(db_path) as conn:
        current_version = _meta_get(conn, "schema_version")
        if current_version != SESSION_INDEX_SCHEMA_VERSION:
            _retry_sqlite(conn, "DELETE FROM session_documents")
            _meta_set(conn, "schema_version", SESSION_INDEX_SCHEMA_VERSION)
            _retry_commit(conn)
            force = True

        last_sync_raw = _meta_get(conn, "last_sync_epoch")
        try:
            last_sync_epoch = int(last_sync_raw or "0")
        except (ValueError, TypeError):
            last_sync_epoch = 0

        adapter_dirty = adapter_dirty_epoch(_home())
        if (
            not force
            and last_sync_epoch
            and (now_epoch - last_sync_epoch) < SYNC_MIN_INTERVAL_SEC
            and adapter_dirty < last_sync_epoch
        ):
            total = _retry_sqlite(conn, _SQL_COUNT_DOCS).fetchone()[0]
            _logger.debug(
                "sync_session_index skipped (last_sync %ds ago, threshold %ds)",
                now_epoch - last_sync_epoch,
                SYNC_MIN_INTERVAL_SEC,
            )
            return {
                "scanned": 0,
                "added": 0,
                "updated": 0,
                "removed": 0,
                "skipped_recent": 1,
                "last_sync_epoch": last_sync_epoch,
                "total_sessions": int(total or 0),
            }

        sync_all_adapters(_home())

        _t_scan_start = time.monotonic()
        upsert_batch: list[tuple[Any, ...]] = []
        queued_paths: set[str] = set()

        existing_meta: dict[str, tuple[int, int]] = {
            row[0]: (int(row[1]), int(row[2]))
            for row in _retry_sqlite(
                conn, "SELECT file_path, file_mtime, file_size FROM session_documents"
            ).fetchall()
        }

        def _flush_upsert_batch() -> None:
            if upsert_batch:
                _retry_sqlite_many(conn, _SQL_UPSERT_DOC, upsert_batch)
                _retry_commit(conn)
                _logger.debug("sync_session_index: flushed %d upsert rows", len(upsert_batch))
                upsert_batch.clear()

        for source_type, path in _iter_sources():
            scanned += 1
            canonical_path = _normalize_file_path(path)
            seen_paths.add(canonical_path)

            if canonical_path in queued_paths:
                continue

            try:
                stat = path.stat()
            except FileNotFoundError:
                continue

            cached = existing_meta.get(canonical_path)
            row = cached
            if cached and cached[0] == int(stat.st_mtime) and cached[1] == int(stat.st_size):
                continue

            doc = _parse_source(source_type, path, file_stat=stat)
            if not doc:
                continue

            upsert_batch.append(
                (
                    canonical_path,
                    doc.source_type,
                    doc.session_id,
                    doc.title,
                    doc.content,
                    doc.created_at,
                    doc.created_at_epoch,
                    doc.file_mtime,
                    doc.file_size,
                    now_epoch,
                )
            )
            queued_paths.add(canonical_path)
            updated += 1 if row else 0
            added += 0 if row else 1

            if len(upsert_batch) >= _BATCH_COMMIT_SIZE:
                _flush_upsert_batch()

        _flush_upsert_batch()

        _t_scan_elapsed = time.monotonic() - _t_scan_start
        _logger.debug(
            "sync_session_index: scanned %d sources in %.3fs (added=%d updated=%d)",
            scanned,
            _t_scan_elapsed,
            added,
            updated,
        )

        # Remove stale entries
        _t_remove_start = time.monotonic()
        conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _temp_seen_paths (path TEXT PRIMARY KEY)"
        )
        conn.execute("DELETE FROM _temp_seen_paths")
        seen_list = list(seen_paths)
        for i in range(0, len(seen_list), _BATCH_COMMIT_SIZE):
            chunk = seen_list[i : i + _BATCH_COMMIT_SIZE]
            conn.executemany(
                "INSERT OR IGNORE INTO _temp_seen_paths(path) VALUES (?)",
                ((p,) for p in chunk),
            )
        stale_count_row = conn.execute(
            "SELECT COUNT(*) FROM session_documents"
            " WHERE file_path NOT IN (SELECT path FROM _temp_seen_paths)"
        ).fetchone()
        removed = int(stale_count_row[0]) if stale_count_row else 0
        if removed:
            conn.execute(
                "DELETE FROM session_documents"
                " WHERE file_path NOT IN (SELECT path FROM _temp_seen_paths)"
            )
            _logger.debug("sync_session_index: deleted %d stale rows via temp table", removed)
        conn.execute("DROP TABLE IF EXISTS _temp_seen_paths")
        _retry_commit(conn)

        _meta_set(conn, "last_sync_epoch", str(now_epoch))

        if (added or updated or removed or force) and _check_fts5_available(conn):
            try:
                _retry_sqlite(conn, "INSERT INTO session_documents_fts(session_documents_fts) VALUES ('rebuild')")
                _logger.debug("sync_session_index: FTS5 index rebuilt")
            except sqlite3.OperationalError as exc:
                _logger.debug("FTS5 rebuild skipped: %s", exc)

        _retry_commit(conn)

        # Vector embedding
        exp_search = os.environ.get("CONTEXTGO_EXPERIMENTAL_SEARCH_BACKEND", "").strip().lower()
        if exp_search == "vector":
            try:
                try:
                    from vector_index import embed_pending_session_docs, get_vector_db_path, vector_available  # noqa: PLC0415, I001
                except ImportError:
                    from contextgo.vector_index import embed_pending_session_docs, get_vector_db_path, vector_available  # type: ignore[import-not-found]  # noqa: PLC0415, I001

                if vector_available():
                    _vdb = get_vector_db_path(db_path)
                    _vresult = embed_pending_session_docs(db_path, _vdb, force=force)
                    _logger.debug(
                        "sync_session_index: vector embed result: embedded=%d skipped=%d deleted=%d",
                        _vresult.get("embedded", 0),
                        _vresult.get("skipped", 0),
                        _vresult.get("deleted", 0),
                    )
            except Exception as exc:
                _logger.debug("sync_session_index: vector embedding skipped: %s", exc)

        total = _retry_sqlite(conn, _SQL_COUNT_DOCS).fetchone()[0]

        _t_remove_elapsed = time.monotonic() - _t_remove_start
        _logger.debug(
            "sync_session_index: removed %d stale entries in %.3fs",
            removed,
            _t_remove_elapsed,
        )

    _t_total = time.monotonic() - _t_start
    _logger.debug(
        "sync_session_index complete in %.3fs: total=%d scanned=%d added=%d updated=%d removed=%d",
        _t_total,
        int(total or 0),
        scanned,
        added,
        updated,
        removed,
    )
    return {
        "scanned": scanned,
        "added": added,
        "updated": updated,
        "removed": removed,
        "skipped_recent": 0,
        "last_sync_epoch": now_epoch,
        "total_sessions": int(total or 0),
    }
