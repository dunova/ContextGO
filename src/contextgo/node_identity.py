#!/usr/bin/env python3
"""Stable node identity for cross-machine memory portability.

Why this module exists
----------------------
ContextGO used to identify a machine by hashing its home directory
(``sha256(str(home))[:12]``) and identified a document by its absolute local
file path.  Both choices are *path-derived*, so they change the moment the same
logical machine is reached through a different home directory, operating
system, or user name — and they are meaningless on another machine entirely.

This module provides a **stable, path-independent node identity** that is
persisted once per ContextGO storage root and reused forever after:

    <storage_root>/node.json
    {
      "schema_version": 1,
      "node_id": "<16 hex chars>",     # stable, generated once, never path-derived
      "label": "<hostname>",           # human-readable, may change freely
      "created_at": "...",
      "platform": "linux|darwin|win32"
    }

``node_id`` is the value stored in the ``origin_host`` provenance column of
every indexed document.  It lets a machine answer the only question that
matters for pruning safety: *"did I write this row, or did it arrive from
somewhere else?"*  Rows that arrived from elsewhere are never deleted just
because a local file is missing.
"""

from __future__ import annotations

import os
import platform
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from context_runtime import atomic_write_json, ensure_private_dir, storage_root, user_home
except ImportError:  # pragma: no cover
    from .context_runtime import atomic_write_json, ensure_private_dir, storage_root, user_home

NODE_SCHEMA_VERSION = 1
NODE_FILE_NAME = "node.json"

__all__ = [
    "NODE_FILE_NAME",
    "NODE_SCHEMA_VERSION",
    "describe_node",
    "node_file_path",
    "node_id",
    "node_label",
    "origin_fields",
    "reset_node_identity",
]

# Process-level cache: node.json is read on every sync, but the value never
# changes within a process.  Keyed by resolved path so that tests using a
# temporary storage root do not collide with the real one.
_CACHE: dict[str, dict[str, Any]] = {}


def node_file_path() -> Path:
    """Return the path of the node identity file for the active storage root."""
    return storage_root() / NODE_FILE_NAME


def _platform_name() -> str:
    """Return a coarse, stable platform name (never a version string)."""
    system = (platform.system() or "").strip().lower()
    if system == "darwin":
        return "darwin"
    if system == "windows":
        return "win32"
    if system == "linux":
        return "linux"
    return system or "unknown"


def _label() -> str:
    """Return a human-readable label for this node (hostname, best effort)."""
    for getter in (socket.gethostname, platform.node):
        try:
            value = (getter() or "").strip()
        except OSError:
            continue
        if value:
            return value
    return "unknown-host"


def _read_node_file(path: Path) -> dict[str, Any] | None:
    """Read and validate an existing node identity file."""
    try:
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    node = str(raw.get("node_id", "")).strip()
    if not node:
        return None
    if any(ch not in "0123456789abcdef" for ch in node):
        return None
    return raw


def _backfill_label(path: Path, raw: dict[str, Any], current_label: str) -> None:
    """Persist a refreshed hostname label without touching ``node_id``.

    The label is cosmetic; refreshing it keeps ``contextgo node`` readable
    after a hostname change while guaranteeing the identity itself is stable.
    """
    if str(raw.get("label", "")) == current_label:
        return
    updated = dict(raw)
    updated["label"] = current_label
    updated["label_updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        atomic_write_json(path, updated)
    except OSError:
        pass


def _load_or_create() -> dict[str, Any]:
    """Return the node identity record, creating it on first use."""
    override = _env_override_node_id()
    if override is not None:
        # Deterministic identity for test runs and for deliberately adopting an
        # existing node id.  Never written to disk.
        return {
            "schema_version": NODE_SCHEMA_VERSION,
            "node_id": override,
            "label": _label(),
            "platform": _platform_name(),
            "created_at": "",
            "ephemeral": True,
        }

    path = node_file_path()
    key = str(path)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    current_label = _label()
    raw = _read_node_file(path)

    if raw is not None:
        _backfill_label(path, raw, current_label)
        raw["label"] = current_label
        _CACHE[key] = raw
        return raw

    record: dict[str, Any] = {
        "schema_version": NODE_SCHEMA_VERSION,
        "node_id": uuid.uuid4().hex[:16],
        "label": current_label,
        "platform": _platform_name(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        ensure_private_dir(path.parent)
        atomic_write_json(path, record)
    except OSError:
        # A read-only or ephemeral storage root must not break indexing: fall
        # back to an in-memory identity for this process.  Rows written under a
        # transient identity are still never pruned by other machines, because
        # prune only ever removes rows whose origin equals the *current* node.
        pass

    _CACHE[key] = record
    return record


def node_id() -> str:
    """Return this node's stable identifier (16 lowercase hex characters)."""
    return str(_load_or_create()["node_id"])


def node_label() -> str:
    """Return this node's human-readable label (the hostname, best effort)."""
    return str(_load_or_create().get("label") or "unknown-host")


def describe_node() -> dict[str, Any]:
    """Return a diagnostic description of this node's identity."""
    record = _load_or_create()
    return {
        "node_id": record["node_id"],
        "label": record.get("label", ""),
        "platform": record.get("platform", _platform_name()),
        "created_at": record.get("created_at", ""),
        "node_file": str(node_file_path()),
        "node_file_exists": node_file_path().is_file(),
        "home": str(user_home()),
    }


def origin_fields() -> dict[str, str]:
    """Return the provenance column values to stamp onto locally written rows."""
    return {
        "origin_host": node_id(),
        "origin_os": _platform_name(),
        "origin_label": node_label(),
    }


def reset_node_identity() -> dict[str, Any]:
    """Delete and regenerate this node's identity, returning the new record.

    Destructive and only meant for tests or for deliberately re-onboarding a
    machine.  Callers are responsible for warning the user: existing local rows
    carry the previous ``origin_host`` and will no longer be treated as
    locally-owned until they are re-indexed.
    """
    path = node_file_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    _CACHE.pop(str(path), None)
    return describe_node()


def _env_override_node_id() -> str | None:
    """Return ``CONTEXTGO_NODE_ID`` when set, for deterministic test runs."""
    value = os.environ.get("CONTEXTGO_NODE_ID", "").strip()
    if not value:
        return None
    if any(ch not in "0123456789abcdef" for ch in value):
        return None
    return value
