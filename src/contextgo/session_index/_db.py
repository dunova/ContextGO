"""Database layer for ContextGO session index (SQLite schema, connections, retry)."""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    from context_config import env_int, storage_root
    from sqlite_retry import retry_commit as _rc
    from sqlite_retry import retry_sqlite as _rs
    from sqlite_retry import retry_sqlite_many as _rsm
except ImportError:  # pragma: no cover
    from contextgo.context_config import env_int, storage_root  # type: ignore[import-not-found]
    from contextgo.sqlite_retry import retry_commit as _rc  # type: ignore[import-not-found]
    from contextgo.sqlite_retry import retry_sqlite as _rs
    from contextgo.sqlite_retry import retry_sqlite_many as _rsm

_logger = logging.getLogger(__name__)

#: Env-var name for overriding the default DB path.
SESSION_DB_PATH_ENV = "CONTEXTGO_SESSION_INDEX_DB_PATH"

#: Set to True once FTS5 availability has been confirmed in the current process.
#: None = not yet checked; True = available; False = unavailable.
_FTS5_AVAILABLE: bool | None = None


# SQL Constants

_DDL_SESSION_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS session_documents (
    file_path        TEXT PRIMARY KEY,
    source_type      TEXT NOT NULL,
    session_id       TEXT NOT NULL,
    title            TEXT NOT NULL,
    content          TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    created_at_epoch INTEGER NOT NULL,
    file_mtime       INTEGER NOT NULL,
    file_size        INTEGER NOT NULL,
    updated_at_epoch INTEGER NOT NULL
)
"""

_DDL_SESSION_META = """
CREATE TABLE IF NOT EXISTS session_index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_session_created    ON session_documents(created_at_epoch DESC)",
    "CREATE INDEX IF NOT EXISTS idx_session_source     ON session_documents(source_type, created_at_epoch DESC)",
    "CREATE INDEX IF NOT EXISTS idx_session_session_id ON session_documents(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_session_updated    ON session_documents(updated_at_epoch DESC)",
]

_DDL_SESSION_DOCUMENTS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS session_documents_fts
USING fts5(title, content, file_path, content=session_documents, content_rowid=rowid, tokenize='unicode61 remove_diacritics 1')
"""

_DDL_FTS_TRIGGERS = [
    """
    CREATE TRIGGER IF NOT EXISTS session_documents_fts_ai
    AFTER INSERT ON session_documents BEGIN
        INSERT INTO session_documents_fts(rowid, title, content, file_path)
        VALUES (new.rowid, new.title, new.content, new.file_path);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS session_documents_fts_ad
    AFTER DELETE ON session_documents BEGIN
        INSERT INTO session_documents_fts(session_documents_fts, rowid, title, content, file_path)
        VALUES ('delete', old.rowid, old.title, old.content, old.file_path);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS session_documents_fts_au
    AFTER UPDATE ON session_documents BEGIN
        INSERT INTO session_documents_fts(session_documents_fts, rowid, title, content, file_path)
        VALUES ('delete', old.rowid, old.title, old.content, old.file_path);
        INSERT INTO session_documents_fts(rowid, title, content, file_path)
        VALUES (new.rowid, new.title, new.content, new.file_path);
    END
    """,
]

_SQL_META_GET = "SELECT value FROM session_index_meta WHERE key = ?"
_SQL_META_SET = """
    INSERT INTO session_index_meta(key, value) VALUES(?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value
"""
_SQL_CHECK_CHANGED = "SELECT file_mtime, file_size FROM session_documents WHERE file_path = ?"
_SQL_UPSERT_DOC = """
    INSERT INTO session_documents(
        file_path, source_type, session_id, title, content,
        created_at, created_at_epoch, file_mtime, file_size, updated_at_epoch
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(file_path) DO UPDATE SET
        source_type      = excluded.source_type,
        session_id       = excluded.session_id,
        title            = excluded.title,
        content          = excluded.content,
        created_at       = excluded.created_at,
        created_at_epoch = excluded.created_at_epoch,
        file_mtime       = excluded.file_mtime,
        file_size        = excluded.file_size,
        updated_at_epoch = excluded.updated_at_epoch
"""
_SQL_DELETE_DOC = "DELETE FROM session_documents WHERE file_path = ?"
_SQL_ALL_PATHS = "SELECT file_path FROM session_documents"
_SQL_COUNT_DOCS = "SELECT COUNT(*) FROM session_documents"
_SQL_MAX_EPOCH = "SELECT MAX(created_at_epoch) FROM session_documents"


# Database helpers


def get_session_db_path() -> Path:
    """Return the session index DB path (env override or storage root)."""
    override = os.environ.get(SESSION_DB_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return storage_root() / "index" / "session_index.db"


def ensure_session_db() -> Path:
    """Create the session index database and schema if absent; return the path."""
    db_path = get_session_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _db_is_new = not db_path.exists()
    with _open_db(db_path) as conn:
        if _db_is_new:
            with contextlib.suppress(OSError):
                os.chmod(db_path, 0o600)
        _retry_sqlite(conn, _DDL_SESSION_DOCUMENTS)
        for ddl in _DDL_INDEXES:
            _retry_sqlite(conn, ddl)
        _retry_sqlite(conn, _DDL_SESSION_META)
        if _check_fts5_available(conn):
            try:
                _retry_sqlite(conn, _DDL_SESSION_DOCUMENTS_FTS)
                for trigger_ddl in _DDL_FTS_TRIGGERS:
                    _retry_sqlite(conn, trigger_ddl)
                _retry_sqlite(conn, "INSERT INTO session_documents_fts(session_documents_fts) VALUES ('rebuild')")
            except sqlite3.OperationalError as exc:
                _logger.debug("FTS5 setup skipped: %s", exc)
        _retry_commit(conn)
    return db_path


@contextmanager
def _open_db(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a SQLite connection with WAL mode and ensure it is closed on exit."""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-32000")
        conn.execute("PRAGMA mmap_size=536870912")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA page_size=4096")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        yield conn
    finally:
        if conn is not None:
            conn.close()


# SQLite retry helpers (delegated to shared sqlite_retry module)


def _retry_sqlite(
    conn: sqlite3.Connection,
    sql: str,
    params: Any = None,
    max_retries: int = 3,
) -> sqlite3.Cursor:
    """Execute *sql* on *conn* with retry-on-busy logic."""
    return _rs(conn, sql, params, max_retries, _logger=_logger)


def _retry_sqlite_many(
    conn: sqlite3.Connection,
    sql: str,
    params_seq: Any,
    max_retries: int = 3,
) -> sqlite3.Cursor:
    """Like :func:`_retry_sqlite` but calls ``executemany`` instead of ``execute``."""
    return _rsm(conn, sql, params_seq, max_retries, _logger=_logger)


def _retry_commit(conn: sqlite3.Connection, max_retries: int = 3) -> None:
    """Commit *conn* with retry-on-busy logic."""
    _rc(conn, max_retries, _logger=_logger)


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    """Retrieve a value from the ``session_index_meta`` table, or ``None``."""
    row = _retry_sqlite(conn, _SQL_META_GET, (key,)).fetchone()
    return str(row[0]) if row else None


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a key/value pair into the ``session_index_meta`` table."""
    _retry_sqlite(conn, _SQL_META_SET, (key, value))


def _check_fts5_available(conn: sqlite3.Connection) -> bool:
    """Return True if the current SQLite build supports FTS5."""
    global _FTS5_AVAILABLE  # noqa: PLW0603
    if _FTS5_AVAILABLE is not None:
        return _FTS5_AVAILABLE
    try:
        conn.execute("SELECT fts5(?)", ("test",))
        _FTS5_AVAILABLE = True
    except sqlite3.OperationalError:
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp._fts5_probe USING fts5(x)")
            conn.execute("DROP TABLE IF EXISTS temp._fts5_probe")
            _FTS5_AVAILABLE = True
        except sqlite3.OperationalError:
            _FTS5_AVAILABLE = False
    return bool(_FTS5_AVAILABLE)
