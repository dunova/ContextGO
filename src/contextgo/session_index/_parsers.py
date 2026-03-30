"""Session document model and file parsers for ContextGO session index."""

from __future__ import annotations

import json
import os
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ._noise import _WHITESPACE_RE, _is_noise_text


def _iso_to_epoch(value: str | None, fallback: int) -> int:
    """Parse an ISO 8601 datetime string to a Unix epoch integer.

    Returns *fallback* if *value* is empty or unparseable.
    """
    if not value:
        return fallback
    raw = str(value).strip()
    if not raw:
        return fallback
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except (ValueError, OverflowError):
        return fallback


def _collect_content_text(items: Any) -> list[str]:
    """Extract user/assistant text blocks from a JSON content array."""
    texts: list[str] = []
    if not isinstance(items, list):
        return texts
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type in {"input_text", "output_text", "text"}:
            text = str(item.get("text") or "").strip()
            if text:
                texts.append(text)
    return texts


def _truncate(texts: Iterable[str], max_chars: int | None = None) -> str:
    """Join *texts* into a single string, capped at *max_chars* total characters."""
    if max_chars is None:
        # Deferred import to avoid circular reference at module level.
        from . import MAX_CONTENT_CHARS
        max_chars = MAX_CONTENT_CHARS
    parts: list[str] = []
    total = 0
    for text in texts:
        clean = _WHITESPACE_RE.sub(" ", str(text or "")).strip()
        if not clean:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(clean) > remaining:
            parts.append(clean[:remaining])
            break
        parts.append(clean)
        total += len(clean) + 1
    return "\n".join(parts)


# Document Model


@dataclass
class SessionDocument:
    """In-memory representation of a single indexed session file."""

    file_path: str
    source_type: str
    session_id: str
    title: str
    content: str
    created_at: str
    created_at_epoch: int
    file_mtime: int
    file_size: int


# Document Parsers


def _finish_session_doc(
    path: Path,
    source_type: str,
    session_id: str,
    title: str,
    created_at: str,
    pieces: list[str],
    mtime: int,
    file_size: int | None = None,
) -> SessionDocument:
    """Build a SessionDocument from already-parsed fields.

    *file_size* may be supplied from a pre-fetched ``os.stat`` result to avoid
    an extra filesystem call; it is resolved via ``path.stat()`` when omitted.
    """
    content = _truncate(pieces)
    if not title:
        title = path.parent.as_posix()
    if not content:
        content = title
    return SessionDocument(
        file_path=str(path),
        source_type=source_type,
        session_id=session_id,
        title=title[:300],
        content=content,
        created_at=created_at or datetime.fromtimestamp(mtime).isoformat(),
        created_at_epoch=_iso_to_epoch(created_at, mtime),
        file_mtime=mtime,
        file_size=file_size if file_size is not None else path.stat().st_size,
    )


def _iter_jsonl_objects(path: Path) -> Generator[dict[str, Any], None, None]:
    """Yield parsed JSON objects from a JSONL file, skipping blank/invalid lines."""
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue


def _parse_codex_session(path: Path, file_stat: os.stat_result | None = None) -> SessionDocument | None:
    """Parse a Codex JSONL session file into a ``SessionDocument``.

    *file_stat* may be a pre-fetched ``os.stat_result`` to avoid a redundant
    filesystem call; the file is re-stat'd when omitted.
    """
    session_id = path.stem
    title = ""
    created_at = ""
    pieces: list[str] = []
    st = file_stat if file_stat is not None else path.stat()
    mtime = int(st.st_mtime)
    file_size = st.st_size
    try:
        for obj in _iter_jsonl_objects(path):
            kind = obj.get("type")
            if kind == "session_meta":
                payload = obj.get("payload") or {}
                session_id = str(payload.get("id") or session_id)
                title = str(payload.get("cwd") or title or "")
                created_at = str(payload.get("timestamp") or created_at or obj.get("timestamp") or "")
            elif kind == "event_msg":
                payload = obj.get("payload") or {}
                if payload.get("type") == "user_message":
                    message = str(payload.get("message") or "").strip()
                    if message and not _is_noise_text(message):
                        pieces.append(message)
            elif kind == "response_item":
                payload = obj.get("payload") or {}
                if payload.get("type") == "message" and payload.get("role") == "assistant":
                    for text in _collect_content_text(payload.get("content")):
                        if not _is_noise_text(text):
                            pieces.append(text)
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return _finish_session_doc(path, "codex_session", session_id, title, created_at, pieces, mtime, file_size)


def _parse_claude_session(path: Path, file_stat: os.stat_result | None = None) -> SessionDocument | None:
    """Parse a Claude JSONL session file into a ``SessionDocument``.

    *file_stat* may be a pre-fetched ``os.stat_result`` to avoid a redundant
    filesystem call; the file is re-stat'd when omitted.
    """
    session_id = path.stem
    title = ""
    created_at = ""
    pieces: list[str] = []
    st = file_stat if file_stat is not None else path.stat()
    mtime = int(st.st_mtime)
    file_size = st.st_size
    try:
        for obj in _iter_jsonl_objects(path):
            kind = obj.get("type")
            session_id = str(obj.get("sessionId") or session_id)
            if not title:
                title = str(obj.get("cwd") or title or "")
            if not created_at:
                created_at = str(obj.get("timestamp") or "")
            if kind == "user":
                message = obj.get("message") or {}
                raw_content = message.get("content")
                if isinstance(raw_content, str) and raw_content.strip() and not _is_noise_text(raw_content):
                    pieces.append(raw_content)
            elif kind == "assistant":
                message = obj.get("message") or {}
                for text in _collect_content_text(message.get("content")):
                    if not _is_noise_text(text):
                        pieces.append(text)
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return _finish_session_doc(path, "claude_session", session_id, title, created_at, pieces, mtime, file_size)


def _make_flat_doc(
    path: Path,
    source_type: str,
    texts: list[str],
    mtime: int,
    file_size: int | None = None,
) -> SessionDocument | None:
    """Build a flat ``SessionDocument`` from extracted text lines, or return ``None``.

    *file_size* may be supplied from a pre-fetched ``os.stat`` result to avoid
    an extra filesystem call; it is resolved via ``path.stat()`` when omitted.
    """
    content = _truncate(texts)
    if not content:
        return None
    return SessionDocument(
        file_path=str(path),
        source_type=source_type,
        session_id=path.stem,
        title=path.name,
        content=content,
        created_at=datetime.fromtimestamp(mtime).isoformat(),
        created_at_epoch=mtime,
        file_mtime=mtime,
        file_size=file_size if file_size is not None else path.stat().st_size,
    )


def _parse_history_jsonl(
    path: Path, source_type: str, file_stat: os.stat_result | None = None
) -> SessionDocument | None:
    """Parse a flat JSONL history file into a ``SessionDocument``.

    *file_stat* may be a pre-fetched ``os.stat_result`` to avoid a redundant
    filesystem call; the file is re-stat'd when omitted.
    """
    st = file_stat if file_stat is not None else path.stat()
    mtime = int(st.st_mtime)
    file_size = st.st_size
    texts: list[str] = []
    try:
        for obj in _iter_jsonl_objects(path):
            if not isinstance(obj, dict):
                continue
            for key in ("display", "text", "input", "prompt", "message"):
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    texts.append(value)
                    break
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return _make_flat_doc(path, source_type, texts, mtime, file_size)


def _parse_generic_session_jsonl(
    path: Path, source_type: str, file_stat: os.stat_result | None = None
) -> SessionDocument | None:
    """Parse a generic JSONL session transcript into a ``SessionDocument``.

    This is intentionally permissive so newly-supported tools can be indexed
    from normalized adapter output or native JSONL session files without
    needing a bespoke parser for every vendor-specific event envelope.
    """

    def _extract_texts(node: Any) -> list[str]:
        texts: list[str] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            if not isinstance(value, str):
                return
            text = value.strip()
            if not text or text in seen:
                return
            seen.add(text)
            texts.append(text)

        def walk(value: Any) -> None:
            if value is None:
                return
            if isinstance(value, str):
                add(value)
                return
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            node_type = str(value.get("type") or "").strip().lower()
            if node_type in {"text", "input_text", "output_text", "reasoning"}:
                add(value.get("text"))
            for key in ("text", "input", "prompt", "display", "message", "body", "summary", "title"):
                add(value.get(key))
            for key in ("content", "parts", "messages", "items", "payload", "data", "state", "response"):
                if key in value:
                    walk(value[key])

        walk(node)
        return texts

    st = file_stat if file_stat is not None else path.stat()
    mtime = int(st.st_mtime)
    file_size = st.st_size
    texts: list[str] = []
    session_id = path.stem
    title = path.name
    try:
        for obj in _iter_jsonl_objects(path):
            if not isinstance(obj, dict):
                continue
            raw_session_id = obj.get("session_id") or obj.get("sessionId") or obj.get("id")
            if isinstance(raw_session_id, str) and raw_session_id.strip():
                session_id = raw_session_id.strip()
            raw_title = obj.get("title")
            if isinstance(raw_title, str) and raw_title.strip():
                title = raw_title.strip()
            texts.extend(_extract_texts(obj))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    content = _truncate(texts)
    if not content:
        return None
    return SessionDocument(
        file_path=str(path),
        source_type=source_type,
        session_id=session_id,
        title=title,
        content=content,
        created_at=datetime.fromtimestamp(mtime).isoformat(),
        created_at_epoch=mtime,
        file_mtime=mtime,
        file_size=file_size,
    )


def _parse_shell_history(
    path: Path, source_type: str, file_stat: os.stat_result | None = None
) -> SessionDocument | None:
    """Parse a shell history file (zsh or bash) into a ``SessionDocument``.

    *file_stat* may be a pre-fetched ``os.stat_result`` to avoid a redundant
    filesystem call; the file is re-stat'd when omitted.
    """
    st = file_stat if file_stat is not None else path.stat()
    mtime = int(st.st_mtime)
    file_size = st.st_size
    texts: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(": "):
                    _, _, command = line.partition(";")
                    if command.strip():
                        texts.append(command.strip())
                else:
                    texts.append(line)
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return _make_flat_doc(path, source_type, texts, mtime, file_size)


def _parse_source(source_type: str, path: Path, file_stat: os.stat_result | None = None) -> SessionDocument | None:
    """Dispatch a source file to the appropriate parser.

    *file_stat* is forwarded to the individual parsers so they can reuse an
    already-fetched ``os.stat_result`` rather than re-stat'ing the file.
    """
    if source_type == "codex_session":
        return _parse_codex_session(path, file_stat)
    if source_type == "claude_session":
        return _parse_claude_session(path, file_stat)
    if source_type in {"opencode_session", "kilo_session", "openclaw_session"} and path.suffix == ".jsonl":
        return _parse_generic_session_jsonl(path, source_type, file_stat)
    if source_type.endswith("_history") and path.suffix == ".jsonl":
        return _parse_history_jsonl(path, source_type, file_stat)
    if source_type.startswith("shell_"):
        return _parse_shell_history(path, source_type, file_stat)
    return None
