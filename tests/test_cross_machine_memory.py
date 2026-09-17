#!/usr/bin/env python3
"""Regression tests for cross-machine / cross-platform memory portability.

These tests encode the failure modes that made ContextGO unusable across
machines before the "memory-first" schema (v6):

* a document's identity used to be its machine-local absolute path, so the same
  memory indexed on two machines produced two unrelated rows;
* any schema-version skew executed ``DELETE FROM session_documents``;
* a full scan pruned every row whose path did not exist locally — including
  every row imported from another machine;
* adapter mirrors were keyed by ``sha256(home)`` and wiped wholesale when a
  source tool was not detected.

Each test below pins one of those properties so it cannot regress.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import context_cli
import node_identity
import session_index
import source_adapters

SELF_NODE = "aaaa000011112222"
PEER_NODE = "bbbb333344445555"


def _insert_document(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    file_path: str,
    source_type: str = "claude_session",
    session_id: str = "s1",
    title: str = "t1",
    content: str = "content one",
    created_at_epoch: int = 1000,
    origin_host: str = SELF_NODE,
    origin_label: str = "self",
) -> None:
    conn.execute(
        "INSERT INTO session_documents("
        "doc_id, file_path, source_type, session_id, title, content, created_at,"
        "created_at_epoch, file_mtime, file_size, updated_at_epoch,"
        "origin_host, origin_os, origin_label, origin_path"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            doc_id,
            file_path,
            source_type,
            session_id,
            title,
            content,
            "2026-01-01T00:00:00+00:00",
            created_at_epoch,
            1,
            1,
            1,
            origin_host,
            "linux",
            origin_label,
            file_path,
        ),
    )


class _IsolatedNode(unittest.TestCase):
    """Base class providing an isolated storage root, home, and node identity.

    Both the storage root **and** the home directory are redirected, so discovery
    cannot pick up real session files from the developer's machine and make
    assertions depend on whatever happens to be installed.
    """

    node_id = SELF_NODE

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.storage = self.root / "contextgo"
        self.storage.mkdir(parents=True, exist_ok=True)
        self.home = self.root / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage / "index" / "session_index.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._env = mock.patch.dict(
            os.environ,
            {
                "CONTEXTGO_STORAGE_ROOT": str(self.storage),
                "CONTEXTGO_NODE_ID": self.node_id,
                session_index.SESSION_DB_PATH_ENV: str(self.db_path),
            },
            clear=False,
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        # Redirect home so source discovery finds an empty directory.
        self._home_patch = mock.patch.object(session_index, "_home", return_value=self.home)
        self._home_patch.start()
        self.addCleanup(self._home_patch.stop)
        self._adapter_home_patch = mock.patch.object(source_adapters, "_home", return_value=self.home)
        self._adapter_home_patch.start()
        self.addCleanup(self._adapter_home_patch.stop)

        node_identity._CACHE.clear()
        self.addCleanup(node_identity._CACHE.clear)


class DocumentIdentityTests(unittest.TestCase):
    """doc_id must be content-derived, never path-derived."""

    def test_doc_id_is_deterministic(self) -> None:
        args = ("claude_session", "s1", "title", "body", 1234)
        self.assertEqual(session_index.compute_doc_id(*args), session_index.compute_doc_id(*args))

    def test_doc_id_changes_with_content(self) -> None:
        base = session_index.compute_doc_id("claude_session", "s1", "t", "body-a", 1)
        other = session_index.compute_doc_id("claude_session", "s1", "t", "body-b", 1)
        self.assertNotEqual(base, other)

    def test_doc_id_is_independent_of_file_path(self) -> None:
        """The same memory must be one row regardless of where the file lives."""
        # compute_doc_id takes no path argument at all: this test documents that
        # the identity function cannot accidentally become path-sensitive.
        signature = session_index.compute_doc_id.__code__.co_varnames[
            : session_index.compute_doc_id.__code__.co_argcount
        ]
        self.assertNotIn("file_path", signature)
        self.assertNotIn("path", signature)


class NodeIdentityTests(_IsolatedNode):
    def test_node_id_is_stable_across_calls(self) -> None:
        self.assertEqual(node_identity.node_id(), node_identity.node_id())
        self.assertEqual(node_identity.node_id(), SELF_NODE)

    def test_node_file_is_persisted_outside_the_cache(self) -> None:
        """Without an explicit override, identity is written to node.json."""
        with mock.patch.dict(os.environ, {"CONTEXTGO_NODE_ID": ""}, clear=False):
            node_identity._CACHE.clear()
            generated = node_identity.node_id()
        path = self.storage / node_identity.NODE_FILE_NAME
        self.assertTrue(path.is_file(), "node identity must be persisted for later runs")
        self.assertEqual(len(generated), 16)
        self.assertTrue(all(ch in "0123456789abcdef" for ch in generated))

    def test_explicit_override_does_not_touch_disk(self) -> None:
        """CONTEXTGO_NODE_ID is honoured verbatim and stays ephemeral."""
        self.assertEqual(node_identity.node_id(), SELF_NODE)
        self.assertFalse((self.storage / node_identity.NODE_FILE_NAME).is_file())

    def test_node_id_is_not_derived_from_home(self) -> None:
        """A different home directory must not change the node identity."""
        first = node_identity.node_id()
        with mock.patch.object(node_identity, "user_home", return_value=Path("/home/somewhere-else")):
            node_identity._CACHE.clear()
            self.assertEqual(node_identity.node_id(), first)

    def test_origin_fields_shape(self) -> None:
        fields = node_identity.origin_fields()
        self.assertEqual(fields["origin_host"], SELF_NODE)
        self.assertIn("origin_os", fields)
        self.assertIn("origin_label", fields)


class LegacyMigrationTests(_IsolatedNode):
    """A v5 path-keyed database must be upgraded in place, without data loss."""

    def _build_legacy_db(self, rows: int = 5) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE session_documents (
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
        )
        conn.execute("CREATE TABLE session_index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO session_index_meta(key, value) VALUES ('schema_version', ?)",
            ("2026-03-26-search-noise-v5",),
        )
        for i in range(rows):
            conn.execute(
                "INSERT INTO session_documents(file_path, source_type, session_id, title, content,"
                " created_at, created_at_epoch, file_mtime, file_size, updated_at_epoch)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    f"/Users/dunova/.contextgo/raw/adapters/226c42ad0dce/deepseek_session/s{i}.jsonl",
                    "deepseek_session",
                    f"s{i}",
                    f"title {i}",
                    f"body {i}",
                    "2026-01-01T00:00:00+00:00",
                    1000 + i,
                    1,
                    1,
                    1,
                ),
            )
        conn.commit()
        conn.close()

    def test_migration_preserves_every_row(self) -> None:
        self._build_legacy_db(rows=5)
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM session_documents").fetchone()[0]
        conn.close()
        self.assertEqual(total, 5, "migration must never drop rows")

    def test_migration_assigns_unique_content_ids_and_provenance(self) -> None:
        self._build_legacy_db(rows=5)
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(session_documents)")}
        self.assertIn("doc_id", columns)
        self.assertIn("origin_host", columns)
        distinct = conn.execute("SELECT COUNT(DISTINCT doc_id) FROM session_documents").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM session_documents").fetchone()[0]
        origins = {row[0] for row in conn.execute("SELECT origin_host FROM session_documents")}
        leftover = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='session_documents_v5'").fetchone()[0]
        conn.close()
        self.assertEqual(distinct, total)
        self.assertEqual(origins, {SELF_NODE})
        self.assertEqual(leftover, 0, "the legacy table must be removed after migration")

    def test_migration_is_idempotent(self) -> None:
        self._build_legacy_db(rows=3)
        session_index.ensure_session_db()
        first = sqlite3.connect(self.db_path).execute("SELECT COUNT(*) FROM session_documents").fetchone()[0]
        session_index.ensure_session_db()
        session_index.ensure_session_db()
        second = sqlite3.connect(self.db_path).execute("SELECT COUNT(*) FROM session_documents").fetchone()[0]
        self.assertEqual(first, second)

    def test_schema_version_change_does_not_wipe_rows(self) -> None:
        """A version bump must reconcile, never reset."""
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        _insert_document(conn, doc_id="d1", file_path="/missing/one.jsonl")
        conn.execute(
            "INSERT INTO session_index_meta(key, value) VALUES ('schema_version', 'ancient-v1')"
            " ON CONFLICT(key) DO UPDATE SET value='ancient-v1'"
        )
        conn.commit()
        conn.close()

        result = session_index.sync_session_index(force=True)
        conn = sqlite3.connect(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM session_documents").fetchone()[0]
        version = conn.execute("SELECT value FROM session_index_meta WHERE key='schema_version'").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(total, 1, "schema bump must not delete existing memories")
        self.assertEqual(version, session_index.SESSION_INDEX_SCHEMA_VERSION)
        self.assertEqual(result.get("removed", 0), 0)


class ForeignMemorySafetyTests(_IsolatedNode):
    """Memories imported from another machine must never be pruned locally."""

    def _seed_foreign(self, count: int = 3) -> None:
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        for i in range(count):
            _insert_document(
                conn,
                doc_id=f"foreign-{i}",
                file_path=f"/Users/dunova/projects/session{i}.jsonl",
                session_id=f"peer-{i}",
                title=f"peer title {i}",
                content=f"peer body {i}",
                created_at_epoch=2000 + i,
                origin_host=PEER_NODE,
                origin_label="mac",
            )
        conn.commit()
        conn.close()
        # Required by the sync fast path.
        from context_runtime import storage_root  # noqa: PLC0415

        (storage_root() / "index").mkdir(parents=True, exist_ok=True)

    def test_foreign_rows_survive_forced_full_sync(self) -> None:
        self._seed_foreign(count=3)
        before = session_index.origin_breakdown()
        self.assertEqual(before["total"], 3)

        result = session_index.sync_session_index(force=True)

        after = session_index.origin_breakdown()
        self.assertEqual(
            after["total"],
            3,
            "imported memories were pruned by a local scan — this is the regression under test",
        )
        self.assertEqual(result.get("removed", 0), 0)
        self.assertFalse(any(entry["is_self"] for entry in after["origins"]))
        self.assertTrue(all(entry["origin_host"] == PEER_NODE for entry in after["origins"]))

    def test_foreign_rows_are_not_treated_as_local_files(self) -> None:
        """A foreign path must not participate in local changed-file detection."""
        self._seed_foreign(count=1)
        session_index.sync_session_index(force=True)
        after = session_index.origin_breakdown()
        # If the foreign row had been reconciled as a local file it would have
        # been skipped or overwritten; either way its origin would change.
        self.assertEqual([entry["origin_host"] for entry in after["origins"]], [PEER_NODE])

    def test_local_missing_file_is_retained_by_default(self) -> None:
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        _insert_document(conn, doc_id="local-1", file_path="/nonexistent/gone.jsonl")
        conn.commit()
        conn.close()

        result = session_index.sync_session_index(force=True)

        conn = sqlite3.connect(self.db_path)
        remaining = conn.execute("SELECT COUNT(*) FROM session_documents WHERE doc_id='local-1'").fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 1, "memory-first default must retain memories whose file vanished")
        self.assertEqual(result.get("removed", 0), 0)

    def test_local_missing_file_is_pruned_when_explicitly_enabled(self) -> None:
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        _insert_document(conn, doc_id="local-2", file_path="/nonexistent/gone2.jsonl")
        conn.commit()
        conn.close()

        with mock.patch.object(session_index, "PRUNE_LOCAL_MISSING", True):
            result = session_index.sync_session_index(force=True)

        conn = sqlite3.connect(self.db_path)
        remaining = conn.execute("SELECT COUNT(*) FROM session_documents WHERE doc_id='local-2'").fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 0)
        self.assertGreaterEqual(result.get("removed", 0), 1)


class AdapterMirrorTests(unittest.TestCase):
    """Adapter mirrors must be keyed by node identity, not by home path."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.storage = self.root / "contextgo"
        self.storage.mkdir(parents=True, exist_ok=True)
        self.home = self.root / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self._env = mock.patch.dict(
            os.environ,
            {"CONTEXTGO_STORAGE_ROOT": str(self.storage), "CONTEXTGO_NODE_ID": SELF_NODE},
            clear=False,
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        node_identity._CACHE.clear()
        self.addCleanup(node_identity._CACHE.clear)

    def test_adapter_root_is_node_keyed(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            root = source_adapters._adapter_root(self.home)
        self.assertEqual(root.name, f"node-{SELF_NODE}")
        self.assertEqual(root.parent.name, "adapters")

    def test_adapter_root_ignores_home_variations(self) -> None:
        """Changing the home path must not move the mirror namespace."""
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            first = source_adapters._adapter_root(self.home)
        other_home = (self.root / "home-elsewhere").resolve()
        other_home.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(source_adapters, "_home", return_value=other_home):
            second = source_adapters._adapter_root(other_home)
        self.assertEqual(first, second)

    def test_legacy_digest_directory_is_adopted(self) -> None:
        import hashlib  # noqa: PLC0415

        legacy_digest = hashlib.sha256(str(self.home).encode("utf-8")).hexdigest()[:12]
        legacy = self.storage / "raw" / "adapters" / legacy_digest
        (legacy / "deepseek_session").mkdir(parents=True)
        (legacy / ".schema_version").write_text(source_adapters.ADAPTER_SCHEMA_VERSION, encoding="utf-8")
        (legacy / "deepseek_session" / "kept.jsonl").write_text("{}", encoding="utf-8")

        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            root = source_adapters._adapter_root(self.home)

        self.assertEqual(root.name, f"node-{SELF_NODE}")
        self.assertTrue(
            (root / "deepseek_session" / "kept.jsonl").is_file(),
            "pre-upgrade mirrors must be adopted, not orphaned",
        )
        self.assertFalse(legacy.exists())

    def test_prune_stale_keeps_everything_when_no_sources_detected(self) -> None:
        """An empty keep-set means 'tool not installed', not 'all mirrors stale'."""
        adapter_dir = self.storage / "raw" / "adapters" / f"node-{SELF_NODE}" / "deepseek_session"
        adapter_dir.mkdir(parents=True)
        for name in ("a.jsonl", "b.jsonl", "c.jsonl"):
            (adapter_dir / name).write_text("{}", encoding="utf-8")

        removed = source_adapters._prune_stale(adapter_dir, set())

        self.assertEqual(removed, 0)
        self.assertEqual(sorted(p.name for p in adapter_dir.glob("*.jsonl")), ["a.jsonl", "b.jsonl", "c.jsonl"])

    def test_prune_stale_still_collects_genuinely_superseded_files(self) -> None:
        adapter_dir = self.storage / "raw" / "adapters" / f"node-{SELF_NODE}" / "deepseek_session"
        adapter_dir.mkdir(parents=True)
        keep = adapter_dir / "keep.jsonl"
        stale = adapter_dir / "stale.jsonl"
        keep.write_text("{}", encoding="utf-8")
        stale.write_text("{}", encoding="utf-8")

        removed = source_adapters._prune_stale(adapter_dir, {keep})

        self.assertEqual(removed, 1)
        self.assertTrue(keep.is_file())
        self.assertFalse(stale.exists())


class MemoryPackTests(_IsolatedNode):
    """The memory pack is the supported cross-machine channel."""

    def _seed(self, count: int = 2, origin: str = SELF_NODE) -> None:
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        for i in range(count):
            _insert_document(
                conn,
                doc_id=session_index.compute_doc_id("claude_session", f"s{i}", f"t{i}", f"body {i}", 1000 + i),
                file_path=f"/Users/dunova/session{i}.jsonl",
                session_id=f"s{i}",
                title=f"t{i}",
                content=f"body {i}",
                created_at_epoch=1000 + i,
                origin_host=origin,
                origin_label="mac" if origin != SELF_NODE else "self",
            )
        conn.commit()
        conn.close()

    def test_export_shape(self) -> None:
        self._seed(count=2)
        pack = session_index.export_memory_package()
        self.assertEqual(pack["format"], session_index.MEMORY_PACK_FORMAT)
        self.assertEqual(pack["schema_version"], session_index.MEMORY_PACK_SCHEMA_VERSION)
        self.assertEqual(pack["counts"]["documents"], 2)
        self.assertEqual(pack["node"]["node_id"], SELF_NODE)
        self.assertEqual(len(pack["documents"]), 2)
        # Provenance/timestamps travel; machine-local mtime/size do not.
        for doc in pack["documents"]:
            self.assertIn("origin_path", doc)
            self.assertIn("created_at_epoch", doc)
            self.assertNotIn("file_mtime", doc)

    def test_roundtrip_into_a_second_node(self) -> None:
        self._seed(count=2, origin=PEER_NODE)
        pack = session_index.export_memory_package()

        other = self.root / "contextgo-b"
        other.mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(
            os.environ,
            {
                "CONTEXTGO_STORAGE_ROOT": str(other),
                "CONTEXTGO_NODE_ID": "cccc999988887777",
                session_index.SESSION_DB_PATH_ENV: str(other / "index" / "session_index.db"),
            },
            clear=False,
        ):
            node_identity._CACHE.clear()
            result = session_index.import_memory_package(pack)
            self.assertEqual(result["inserted"], 2)
            self.assertEqual(result["skipped"], 0)
            breakdown = session_index.origin_breakdown()
            self.assertEqual(breakdown["total"], 2)
            self.assertTrue(all(entry["origin_host"] == PEER_NODE for entry in breakdown["origins"]))

            # Importing twice must be a no-op.
            again = session_index.import_memory_package(pack)
            self.assertEqual(again["inserted"], 0)
            self.assertEqual(again["skipped"], 2)

            # And the imported memories must survive this node's own scan.
            session_index.sync_session_index(force=True)
            self.assertEqual(session_index.origin_breakdown()["total"], 2)

    def test_import_recomputes_doc_id_from_content(self) -> None:
        """A tampered pack must not be able to inject a foreign identity."""
        pack = session_index.export_memory_package()
        pack["documents"] = [
            {
                "doc_id": "deadbeef" * 8,
                "source_type": "claude_session",
                "session_id": "x",
                "title": "t",
                "content": "real body",
                "created_at": "2026-01-01T00:00:00+00:00",
                "created_at_epoch": 42,
                "origin_host": PEER_NODE,
                "origin_os": "darwin",
                "origin_label": "mac",
                "origin_path": "/Users/dunova/x.jsonl",
            }
        ]
        result = session_index.import_memory_package(pack)
        self.assertEqual(result["inserted"], 1)

        expected = session_index.compute_doc_id("claude_session", "x", "t", "real body", 42)
        conn = sqlite3.connect(self.db_path)
        stored = conn.execute("SELECT doc_id FROM session_documents").fetchall()
        conn.close()
        self.assertEqual([row[0] for row in stored], [expected])

    def test_import_rejects_wrong_format(self) -> None:
        with self.assertRaises(ValueError):
            session_index.import_memory_package({"format": "something-else", "documents": []})

    def test_import_rejects_future_schema(self) -> None:
        with self.assertRaises(ValueError):
            session_index.import_memory_package(
                {
                    "format": session_index.MEMORY_PACK_FORMAT,
                    "schema_version": session_index.MEMORY_PACK_SCHEMA_VERSION + 1,
                    "documents": [],
                }
            )

    def test_import_counts_invalid_entries(self) -> None:
        pack = {
            "format": session_index.MEMORY_PACK_FORMAT,
            "schema_version": session_index.MEMORY_PACK_SCHEMA_VERSION,
            "node": {"node_id": PEER_NODE},
            "documents": [
                {"content": "   ", "source_type": "x", "session_id": "1", "title": "t"},
                "not-a-dict",
                {
                    "content": "good body",
                    "source_type": "x",
                    "session_id": "2",
                    "title": "t",
                    "created_at_epoch": 5,
                    "origin_host": PEER_NODE,
                },
            ],
        }
        result = session_index.import_memory_package(pack)
        self.assertEqual(result["invalid"], 2)
        self.assertEqual(result["inserted"], 1)

    def test_write_and_read_package_roundtrip(self) -> None:
        self._seed(count=1)
        pack = session_index.export_memory_package()
        target = self.root / "pack.memories.json"
        session_index.write_memory_package(target, pack)
        reloaded = session_index.read_memory_package(target)
        self.assertEqual(reloaded["documents"], pack["documents"])

    def test_gzip_package_roundtrip(self) -> None:
        self._seed(count=1)
        pack = session_index.export_memory_package()
        target = self.root / "pack.memories.json.gz"
        session_index.write_memory_package(target, pack)
        reloaded = session_index.read_memory_package(target)
        self.assertEqual(reloaded["counts"]["documents"], 1)


class HealthReportingTests(_IsolatedNode):
    def test_health_reports_origin_split(self) -> None:
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        _insert_document(conn, doc_id="mine", file_path="/tmp/mine.jsonl", origin_host=SELF_NODE)
        _insert_document(
            conn,
            doc_id="theirs",
            file_path="/Users/dunova/theirs.jsonl",
            origin_host=PEER_NODE,
            origin_label="mac",
        )
        conn.commit()
        conn.close()

        payload = session_index.health_payload()
        self.assertEqual(payload["node_id"], SELF_NODE)
        self.assertEqual(payload["local_sessions"], 1)
        self.assertEqual(payload["imported_sessions"], 1)
        self.assertEqual(payload["sessions_by_origin"][PEER_NODE], 1)

    def test_origin_breakdown_marks_self(self) -> None:
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        _insert_document(conn, doc_id="mine", file_path="/tmp/mine.jsonl", origin_host=SELF_NODE)
        conn.commit()
        conn.close()
        breakdown = session_index.origin_breakdown()
        self.assertTrue(all(entry["is_self"] for entry in breakdown["origins"]))


class LocalFileEvolutionTests(_IsolatedNode):
    """Editing a local file must replace its previous revision, not add one."""

    def _write_codex_session(self, body: str) -> Path:
        target = self.home / ".codex" / "sessions" / "2026" / "09" / "17" / "one.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    def test_edited_file_replaces_previous_revision(self) -> None:
        session_index.ensure_session_db()
        v1 = json.dumps(
            {
                "type": "session_meta",
                "payload": {"id": "evolve", "cwd": "/tmp/p", "timestamp": "2026-01-01T00:00:00Z"},
            }
        )
        path = self._write_codex_session(v1)

        first = session_index.sync_session_index(force=True)
        self.assertEqual(first["added"], 1)
        self.assertEqual(session_index.origin_breakdown()["total"], 1)

        # Grow the same file: a new content identity, but the same memory.
        import time  # noqa: PLC0415

        time.sleep(0.01)
        v2 = "\n".join(
            [
                v1,
                json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "more"}}),
            ]
        )
        path.write_text(v2, encoding="utf-8")

        second = session_index.sync_session_index(force=True)
        self.assertEqual(second["updated"], 1, "editing an existing file counts as an update")
        self.assertEqual(
            session_index.origin_breakdown()["total"],
            1,
            "the previous revision of the same file must not linger as a second memory",
        )

    def test_distinct_files_remain_distinct_memories(self) -> None:
        session_index.ensure_session_db()
        for name, sid in (("a.jsonl", "s-a"), ("b.jsonl", "s-b")):
            target = self.home / ".codex" / "sessions" / "2026" / "09" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"id": sid, "cwd": "/tmp/p", "timestamp": "2026-01-01T00:00:00Z"},
                    }
                ),
                encoding="utf-8",
            )
        session_index.sync_session_index(force=True)
        self.assertEqual(session_index.origin_breakdown()["total"], 2)


class NodeIdentityInternalsTests(unittest.TestCase):
    """Cover the identity file lifecycle, including failure and refresh paths."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.storage = self.root / "contextgo"
        self.storage.mkdir(parents=True, exist_ok=True)
        self._env = mock.patch.dict(
            os.environ,
            {"CONTEXTGO_STORAGE_ROOT": str(self.storage), "CONTEXTGO_NODE_ID": ""},
            clear=False,
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        node_identity._CACHE.clear()
        self.addCleanup(node_identity._CACHE.clear)

    def test_platform_name_maps_known_systems(self) -> None:
        for system, expected in (("Darwin", "darwin"), ("Windows", "win32"), ("Linux", "linux")):
            with mock.patch.object(node_identity.platform, "system", return_value=system):
                self.assertEqual(node_identity._platform_name(), expected)

    def test_platform_name_passes_through_unknown_system(self) -> None:
        with mock.patch.object(node_identity.platform, "system", return_value="Plan9"):
            self.assertEqual(node_identity._platform_name(), "plan9")

    def test_platform_name_defaults_to_unknown(self) -> None:
        with mock.patch.object(node_identity.platform, "system", return_value="   "):
            self.assertEqual(node_identity._platform_name(), "unknown")

    def test_label_falls_back_to_platform_node(self) -> None:
        with (
            mock.patch.object(node_identity.socket, "gethostname", side_effect=OSError("boom")),
            mock.patch.object(node_identity.platform, "node", return_value="fallback-host"),
        ):
            self.assertEqual(node_identity._label(), "fallback-host")

    def test_label_defaults_when_everything_is_empty(self) -> None:
        with (
            mock.patch.object(node_identity.socket, "gethostname", return_value="  "),
            mock.patch.object(node_identity.platform, "node", return_value=""),
        ):
            self.assertEqual(node_identity._label(), "unknown-host")

    def test_invalid_node_file_is_replaced(self) -> None:
        path = self.storage / node_identity.NODE_FILE_NAME
        for bad in ('{"node_id": ""}', '{"node_id": "NOT-HEX"}', "[]", "not-json"):
            path.write_text(bad, encoding="utf-8")
            node_identity._CACHE.clear()
            self.assertIsNone(node_identity._read_node_file(path))
            # A fresh identity must be generated and be valid.
            generated = node_identity.node_id()
            self.assertEqual(len(generated), 16)

    def test_label_is_refreshed_without_changing_node_id(self) -> None:
        original = node_identity.node_id()
        with mock.patch.object(node_identity, "_label", return_value="renamed-host"):
            node_identity._CACHE.clear()
            self.assertEqual(node_identity.node_label(), "renamed-host")
            self.assertEqual(node_identity.node_id(), original)

        payload = json.loads((self.storage / node_identity.NODE_FILE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(payload["node_id"], original)
        self.assertEqual(payload["label"], "renamed-host")
        self.assertIn("label_updated_at", payload)

    def test_reset_node_identity_regenerates(self) -> None:
        first = node_identity.node_id()
        record = node_identity.reset_node_identity()
        self.assertNotEqual(record["node_id"], first)
        self.assertEqual(node_identity.node_id(), record["node_id"])

    def test_reset_on_missing_file_is_safe(self) -> None:
        (self.storage / node_identity.NODE_FILE_NAME).unlink(missing_ok=True)
        node_identity._CACHE.clear()
        self.assertTrue(node_identity.reset_node_identity()["node_id"])

    def test_invalid_override_is_ignored(self) -> None:
        with mock.patch.dict(os.environ, {"CONTEXTGO_NODE_ID": "ZZZZ"}, clear=False):
            self.assertIsNone(node_identity._env_override_node_id())
            # Falls back to a generated, persisted identity.
            self.assertEqual(len(node_identity.node_id()), 16)

    def test_read_only_storage_still_yields_an_identity(self) -> None:
        broken = mock.patch.object(node_identity, "atomic_write_json", side_effect=OSError("read-only"))
        with broken:
            node_identity._CACHE.clear()
            self.assertEqual(len(node_identity.node_id()), 16)

    def test_describe_node_reports_file_existence(self) -> None:
        node_identity.node_id()
        described = node_identity.describe_node()
        self.assertTrue(described["node_file_exists"])
        self.assertTrue(described["home"])
        self.assertIn(described["platform"], ("linux", "darwin", "win32"))


class MemoryPackFilterTests(_IsolatedNode):
    def _seed_mixed(self) -> None:
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        _insert_document(
            conn,
            doc_id="local-a",
            file_path="/tmp/a.jsonl",
            source_type="codex_session",
            origin_host=SELF_NODE,
        )
        _insert_document(
            conn,
            doc_id="peer-b",
            file_path="/Users/dunova/b.jsonl",
            source_type="claude_session",
            origin_host=PEER_NODE,
            origin_label="mac",
        )
        conn.commit()
        conn.close()

    def test_local_only_export_excludes_imported_memories(self) -> None:
        self._seed_mixed()
        pack = session_index.export_memory_package(include_foreign=False)
        self.assertEqual(pack["counts"]["documents"], 1)
        self.assertEqual(pack["documents"][0]["doc_id"], "local-a")

    def test_source_type_filter(self) -> None:
        self._seed_mixed()
        pack = session_index.export_memory_package(source_type="claude_session")
        self.assertEqual(pack["counts"]["documents"], 1)
        self.assertEqual(pack["documents"][0]["origin_host"], PEER_NODE)

    def test_limit_is_applied(self) -> None:
        self._seed_mixed()
        pack = session_index.export_memory_package(limit=1)
        self.assertEqual(len(pack["documents"]), 1)

    def test_read_missing_package_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            session_index.read_memory_package(self.root / "absent.json")

    def test_read_malformed_package_raises(self) -> None:
        bad = self.root / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            session_index.read_memory_package(bad)

    def test_read_non_object_package_raises(self) -> None:
        bad = self.root / "list.json"
        bad.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(ValueError):
            session_index.read_memory_package(bad)

    def test_import_without_provenance_is_attributed_to_exporter(self) -> None:
        payload = {
            "format": session_index.MEMORY_PACK_FORMAT,
            "schema_version": session_index.MEMORY_PACK_SCHEMA_VERSION,
            "node": {"node_id": PEER_NODE},
            "documents": [
                {
                    "content": "no provenance body",
                    "source_type": "x",
                    "session_id": "1",
                    "title": "t",
                    "created_at_epoch": 7,
                }
            ],
        }
        result = session_index.import_memory_package(payload)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(session_index.origin_breakdown()["origins"][0]["origin_host"], PEER_NODE)

    def test_import_rejects_non_object_payload(self) -> None:
        with self.assertRaises(ValueError):
            session_index.import_memory_package(["nope"])  # type: ignore[arg-type]

    def test_import_rejects_bad_schema_version_type(self) -> None:
        with self.assertRaises(ValueError):
            session_index.import_memory_package(
                {
                    "format": session_index.MEMORY_PACK_FORMAT,
                    "schema_version": "one",
                    "documents": [],
                }
            )

    def test_import_rejects_non_list_documents(self) -> None:
        with self.assertRaises(ValueError):
            session_index.import_memory_package(
                {
                    "format": session_index.MEMORY_PACK_FORMAT,
                    "schema_version": 1,
                    "documents": {"nope": True},
                }
            )

    def test_import_tolerates_unparseable_epoch(self) -> None:
        payload = {
            "format": session_index.MEMORY_PACK_FORMAT,
            "schema_version": 1,
            "node": {"node_id": PEER_NODE},
            "documents": [
                {
                    "content": "body with bad epoch",
                    "source_type": "x",
                    "session_id": "1",
                    "title": "t",
                    "created_at_epoch": "not-a-number",
                }
            ],
        }
        result = session_index.import_memory_package(payload)
        self.assertEqual(result["inserted"], 1)


class CliHandlerTests(_IsolatedNode):
    """Exercise the actual CLI handlers, not just parser registration.

    ``_get_session_index`` / ``_get_node_identity`` are bound explicitly rather
    than relying on module state.  ``tests/test_vector_index.py`` reloads the
    ``context_cli`` module, which can leave mocked getters behind for whichever
    test file happens to run next; binding here makes these tests order-independent.
    """

    def setUp(self) -> None:
        super().setUp()
        self._si_patch = mock.patch.object(context_cli, "_get_session_index", return_value=session_index)
        self._si_patch.start()
        self.addCleanup(self._si_patch.stop)
        self._node_patch = mock.patch.object(context_cli, "_get_node_identity", return_value=node_identity)
        self._node_patch.start()
        self.addCleanup(self._node_patch.stop)

    def test_cmd_node_text_and_json(self) -> None:
        session_index.ensure_session_db()
        conn = sqlite3.connect(self.db_path)
        _insert_document(conn, doc_id="d1", file_path="/tmp/d1.jsonl", origin_host=SELF_NODE)
        conn.commit()
        conn.close()

        args = type("A", (), {"json": False})()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(context_cli.cmd_node(args), 0)
        out = buffer.getvalue()
        self.assertIn("node_id", out)
        self.assertIn(SELF_NODE, out)

        args_json = type("A", (), {"json": True})()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(context_cli.cmd_node(args_json), 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["node"]["node_id"], SELF_NODE)
        self.assertEqual(payload["sessions"]["total"], 1)

    def test_cmd_memory_pack_export_and_import(self) -> None:
        session_index.ensure_session_db()
        # Use the content-derived identity so a re-import is genuinely a no-op.
        doc_id = session_index.compute_doc_id("claude_session", "s1", "t1", "content one", 1000)
        conn = sqlite3.connect(self.db_path)
        _insert_document(conn, doc_id=doc_id, file_path="/tmp/pack.jsonl", origin_host=SELF_NODE)
        conn.commit()
        conn.close()

        out_file = self.root / "pack.memories.json"
        export_args = type(
            "A",
            (),
            {
                "pack_action": "export",
                "out": str(out_file),
                "stdout": False,
                "limit": 10,
                "local_only": False,
                "source_type": "all",
            },
        )()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(context_cli.cmd_memory_pack(export_args), 0)
        self.assertTrue(out_file.is_file())
        self.assertIn("documents=1", buffer.getvalue())

        # Re-importing into the same node is a no-op.
        import_args = type("A", (), {"pack_action": "import", "input": str(out_file)})()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(context_cli.cmd_memory_pack(import_args), 0)
        self.assertIn("skipped=1", buffer.getvalue())

    def test_cmd_memory_pack_export_to_stdout(self) -> None:
        session_index.ensure_session_db()
        args = type(
            "A",
            (),
            {
                "pack_action": "export",
                "out": None,
                "stdout": True,
                "limit": 10,
                "local_only": True,
                "source_type": "all",
            },
        )()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(context_cli.cmd_memory_pack(args), 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["format"], session_index.MEMORY_PACK_FORMAT)

    def test_cmd_memory_pack_import_missing_file(self) -> None:
        args = type("A", (), {"pack_action": "import", "input": str(self.root / "nope.json")})()
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            self.assertEqual(context_cli.cmd_memory_pack(args), 2)
        self.assertIn("找不到", buffer.getvalue())

    def test_cmd_memory_pack_import_invalid_file(self) -> None:
        bad = self.root / "bad.json"
        bad.write_text('{"format": "wrong"}', encoding="utf-8")
        args = type("A", (), {"pack_action": "import", "input": str(bad)})()
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            self.assertEqual(context_cli.cmd_memory_pack(args), 2)
        self.assertIn("Error", buffer.getvalue())

    def test_cmd_memory_pack_unknown_action(self) -> None:
        args = type("A", (), {"pack_action": "wat"})()
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            self.assertEqual(context_cli.cmd_memory_pack(args), 2)
        self.assertIn("Usage", buffer.getvalue())


class CliSurfaceTests(unittest.TestCase):
    """The new commands must be registered and reachable."""

    def test_node_and_memory_pack_are_registered(self) -> None:
        parser = context_cli.build_parser()
        actions = set()
        for action in parser._subparsers._group_actions:  # noqa: SLF001 - introspecting argparse
            actions.update(action.choices.keys())
        self.assertIn("node", actions)
        self.assertIn("memory-pack", actions)

    def test_commands_table_has_handlers(self) -> None:
        self.assertIn("node", context_cli.COMMANDS)
        self.assertIn("memory-pack", context_cli.COMMANDS)


if __name__ == "__main__":
    unittest.main()
