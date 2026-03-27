#!/usr/bin/env python3
"""Unit tests for session_index module."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_index


class SessionIndexTests(unittest.TestCase):
    def test_build_query_terms_extracts_anchor(self) -> None:
        terms = session_index.build_query_terms("继续搜索 GitHub 和 X 研究 notebookLM 的终端调用方案")
        lowered = {t.lower() for t in terms}
        self.assertIn("github", lowered)
        self.assertIn("notebooklm", lowered)
        self.assertIn("终端调用", terms)
        self.assertIn("调用方案", terms)

    def test_sync_and_search_local_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_root = root / ".codex" / "sessions" / "2026" / "03" / "25"
            codex_root.mkdir(parents=True)
            session_file = codex_root / "sample.jsonl"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "sample-session",
                                    "cwd": "/tmp/notebooklm-project",
                                    "timestamp": "2026-03-25T00:00:00Z",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {"type": "user_message", "message": "research NotebookLM integration"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            db_path = root / "session_index.db"
            with (
                mock.patch.object(session_index, "_home", return_value=root),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
            ):
                payload = session_index.health_payload()
                self.assertTrue(payload["session_index_db_exists"])
                self.assertGreaterEqual(payload["total_sessions"], 1)
                text = session_index.format_search_results("NotebookLM", limit=5)
                self.assertIn("sample-session", text)
                self.assertIn("NotebookLM", text)

    def test_sync_and_search_archived_codex_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archived_root = root / ".codex" / "archived_sessions"
            archived_root.mkdir(parents=True)
            session_file = archived_root / "archived.jsonl"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "archived-session",
                                    "cwd": "/tmp/old-project",
                                    "timestamp": "2026-03-06T00:00:00Z",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {
                                    "type": "user_message",
                                    "message": "先做 onecontext 预热，再继续 NotebookLM 方案调研",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "response_item",
                                "payload": {
                                    "type": "message",
                                    "role": "assistant",
                                    "content": [{"type": "output_text", "text": "NotebookLM 的真实历史结论已经确认。"}],
                                },
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            db_path = root / "session_index.db"
            with (
                mock.patch.object(session_index, "_home", return_value=root),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
            ):
                session_index.sync_session_index(force=True)
                text = session_index.format_search_results("NotebookLM", limit=5)
                self.assertIn("archived-session", text)
                self.assertIn("NotebookLM", text)

    def test_recent_sync_skips_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_root = root / ".codex" / "sessions" / "2026" / "03" / "25"
            codex_root.mkdir(parents=True)
            (codex_root / "sample.jsonl").write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "sample-session",
                            "cwd": "/tmp/project",
                            "timestamp": "2026-03-25T00:00:00Z",
                        },
                    }
                ),
                encoding="utf-8",
            )
            db_path = root / "session_index.db"
            with (
                mock.patch.object(session_index, "_home", return_value=root),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
            ):
                first = session_index.sync_session_index(force=True)
                second = session_index.sync_session_index(force=False)
                self.assertGreaterEqual(first["scanned"], 1)
                self.assertEqual(second["skipped_recent"], 1)

    def test_sync_handles_missing_cached_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "session_index.db"
            missing_path = root / "missing.jsonl"
            with (
                mock.patch.object(session_index, "_home", return_value=root),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
                mock.patch.object(session_index, "_iter_sources", return_value=[("codex_session", missing_path)]),
            ):
                stats = session_index.sync_session_index(force=True)
                self.assertGreaterEqual(stats["scanned"], 1)
                self.assertEqual(stats["added"], 0)

    def test_native_search_rows_when_enabled(self) -> None:
        mock_result = mock.Mock()
        mock_result.returncode = 0
        with (
            mock.patch.object(session_index, "EXPERIMENTAL_SEARCH_BACKEND", "go"),
            mock.patch.object(
                session_index.context_native,
                "run_native_scan",
                return_value=mock_result,
            ) as mock_run,
            mock.patch.object(
                session_index.context_native,
                "extract_matches",
                return_value=[
                    {
                        "source": "codex_session",
                        "session_id": "abc",
                        "path": "/tmp/a.jsonl",
                        "snippet": "NotebookLM match",
                    }
                ],
            ),
        ):
            rows = session_index._native_search_rows("NotebookLM", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_id"], "abc")
        mock_run.assert_called_once()

    def test_native_search_rows_filters_agents_noise(self) -> None:
        mock_result = mock.Mock()
        mock_result.returncode = 0
        with (
            mock.patch.object(session_index, "EXPERIMENTAL_SEARCH_BACKEND", "go"),
            mock.patch.object(session_index.context_native, "run_native_scan", return_value=mock_result),
            mock.patch.object(
                session_index.context_native,
                "extract_matches",
                return_value=[
                    {
                        "source": "codex_session",
                        "session_id": "noise",
                        "path": "/tmp/noise.jsonl",
                        "snippet": "# AGENTS.md instructions for /tmp NotebookLM",
                    },
                    {
                        "source": "codex_session",
                        "session_id": "clean",
                        "path": "/tmp/clean.jsonl",
                        "snippet": "NotebookLM integration decision",
                    },
                ],
            ),
        ):
            rows = session_index._native_search_rows("NotebookLM", limit=5)
        self.assertEqual([row["session_id"] for row in rows], ["clean"])

    def test_iter_sources_can_use_native_inventory(self) -> None:
        mock_result = mock.Mock()
        mock_result.returncode = 0
        with (
            mock.patch.object(session_index, "EXPERIMENTAL_SYNC_BACKEND", "go"),
            mock.patch.object(session_index.context_native, "run_native_scan", return_value=mock_result) as mock_run,
            mock.patch.object(
                session_index.context_native,
                "inventory_items",
                return_value=[("codex_session", Path("/tmp/native.jsonl"))],
            ),
        ):
            items = session_index._iter_sources()
        self.assertEqual(items, [("codex_session", Path("/tmp/native.jsonl"))])
        mock_run.assert_called_once()

    def test_fetch_session_docs_by_paths_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "session_index.db"
            canonical = session_index._normalize_file_path(Path("/tmp/dedup.jsonl"))
            with mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False):
                session_index.ensure_session_db()
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        """
                        INSERT INTO session_documents(
                            file_path, source_type, session_id, title, content,
                            created_at, created_at_epoch, file_mtime, file_size, updated_at_epoch
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical,
                            "codex_session",
                            "dedup",
                            "Dedup Session",
                            "Dedup NotebookLM content",
                            "2026-03-25T00:00:00Z",
                            1700000000,
                            123,
                            456,
                            1700000000,
                        ),
                    )
                    conn.commit()
                    conn.row_factory = sqlite3.Row
                    docs = session_index._fetch_session_docs_by_paths(conn, ["/tmp/dedup.jsonl", "/tmp/dedup.jsonl"])
                    self.assertIn(canonical, docs)
                    self.assertEqual(docs[canonical]["session_id"], "dedup")
                finally:
                    conn.close()

    def test_enrich_native_rows_uses_index_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "session_index.db"
            canonical = session_index._normalize_file_path(Path("/tmp/native.jsonl"))
            with mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False):
                session_index.ensure_session_db()
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        """
                        INSERT INTO session_documents(
                            file_path, source_type, session_id, title, content,
                            created_at, created_at_epoch, file_mtime, file_size, updated_at_epoch
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical,
                            "codex_session",
                            "native-sample",
                            "Native Session Title",
                            "NotebookLM idea and decisions for the project",
                            "2026-03-25T00:00:00Z",
                            1700000000,
                            123,
                            456,
                            1700000000,
                        ),
                    )
                    conn.commit()
                    conn.row_factory = sqlite3.Row
                    rows = [{"file_path": canonical, "snippet": "fallback snippet", "source_type": "native_session"}]
                    enriched = session_index._enrich_native_rows(rows, conn, ["NotebookLM"], limit=5)
                    self.assertEqual(enriched[0]["session_id"], "native-sample")
                    self.assertIn("NotebookLM", enriched[0]["snippet"])
                finally:
                    conn.close()

    def test_sync_session_index_canonicalizes_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "session_index.db"
            fake_dir = Path(tmpdir) / "src"
            fake_dir.mkdir(parents=True, exist_ok=True)
            real_file = fake_dir / "sample.jsonl"
            real_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "canonical-session",
                                    "cwd": "/tmp/canonical",
                                    "timestamp": "2026-03-25T00:00:00Z",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {"type": "user_message", "message": "canonical NotebookLM content"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            alias = fake_dir / "alias.jsonl"
            alias.symlink_to(real_file)
            with mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False):
                original_iter = session_index._iter_sources
                try:
                    session_index._iter_sources = lambda: [
                        ("codex_session", alias),
                        ("codex_session", real_file),
                    ]
                    stats = session_index.sync_session_index(force=True)
                finally:
                    session_index._iter_sources = original_iter
            self.assertEqual(stats["added"], 1)
            self.assertEqual(stats["updated"], 0)
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute("SELECT file_path FROM session_documents").fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][0], str(real_file.resolve()))
            finally:
                conn.close()

    def test_search_noise_penalty_demotes_prompt_like_content(self) -> None:
        noisy = session_index._search_noise_penalty(
            "skills-repo",
            "Current Skill Name: notebooklm\nCurrent Description:\nQuery AND UPLOAD to Google NotebookLM",
            "/tmp/skills/file.jsonl",
        )
        clean = session_index._search_noise_penalty(
            "product-notes",
            "NotebookLM integration decision for local runtime",
            "/tmp/contextgo/notes.jsonl",
        )
        self.assertGreater(noisy, clean)

    def test_current_repo_meta_result_is_excluded(self) -> None:
        repo = str(Path("/workspace/ContextGO").resolve())
        with mock.patch("pathlib.Path.cwd", return_value=Path(repo)):
            self.assertTrue(
                session_index._is_current_repo_meta_result(
                    repo,
                    "已收到任务。写集仅限 scripts/session_index.py。建议验证命令：python3 scripts/context_cli.py search NotebookLM",
                    "/tmp/session.jsonl",
                )
            )
            self.assertTrue(
                session_index._is_current_repo_meta_result(
                    repo,
                    "职责只限测试，不要改文件。测试集使用 artifacts/testsets/dataset_2026-03-25.json。",
                    "/tmp/session.jsonl",
                )
            )
            self.assertTrue(
                session_index._is_current_repo_meta_result(
                    repo,
                    "仓库：/workspace/ContextGO。你负责 `benchmarks/**`。改动文件: benchmarks/run.py",
                    "/tmp/session.jsonl",
                )
            )
            self.assertFalse(
                session_index._is_current_repo_meta_result(
                    "/tmp/other",
                    "NotebookLM product decision note",
                    "/tmp/session.jsonl",
                )
            )

    def test_build_snippet_prefers_conclusion_window(self) -> None:
        text = (
            "NotebookLM 过程说明，先做预热。 这里还是过程段。 最终交付：NotebookLM 的真实结论已经确认，并已完成验证。"
        )
        snippet = session_index._build_snippet(text, ["NotebookLM"])
        self.assertIn("最终交付", snippet)

    def test_build_snippet_prefers_summary_marker_without_term_hit(self) -> None:
        text = "/workspace/ContextGO 一些过程说明。 变更概览：统一默认安装目录与服务标签。 后面还有更多细节。"
        snippet = session_index._build_snippet(text, ["2026-03-25"])
        self.assertIn("变更概览", snippet)

    def test_format_search_results_compacts_long_snippet(self) -> None:
        with mock.patch.object(
            session_index,
            "_search_rows",
            return_value=[
                {
                    "source_type": "codex_session",
                    "session_id": "s1",
                    "title": "/tmp/project",
                    "file_path": "/tmp/file.jsonl",
                    "created_at": "2026-03-26T00:00:00Z",
                    "snippet": "A" * 300,
                }
            ],
        ):
            text = session_index.format_search_results("x", limit=1)
        self.assertIn("A" * 50, text)
        self.assertIn("…", text)
        self.assertLess(len(text.split("> ", 1)[1]), 140)

    def test_path_only_content_is_demoted(self) -> None:
        self.assertTrue(
            session_index._looks_like_path_only_content(
                "/workspace/ContextGO",
                "/workspace/ContextGO",
            )
        )
        self.assertFalse(
            session_index._looks_like_path_only_content(
                "/workspace/ContextGO",
                "变更概览：统一默认安装目录。",
            )
        )

    def test_literal_long_query_falls_back_to_anchor_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archived_root = root / ".codex" / "archived_sessions"
            archived_root.mkdir(parents=True)
            session_file = archived_root / "archived.jsonl"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "long-query-session",
                                    "cwd": "/tmp/github-research",
                                    "timestamp": "2026-03-06T00:00:00Z",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {
                                    "type": "user_message",
                                    "message": "继续搜索 GitHub 和 X，研究 notebookLM 的终端调用方案",
                                },
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            db_path = root / "session_index.db"
            query = "继续搜索 GitHub 和 X 研究 notebookLM 的终端调用方案"
            with (
                mock.patch.object(session_index, "_home", return_value=root),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
            ):
                session_index.sync_session_index(force=True)
                rows = session_index._search_rows(query, limit=5, literal=True)
            self.assertEqual(rows[0]["session_id"], "long-query-session")

    def test_literal_long_query_fallback_skips_current_repo_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archived_root = root / ".codex" / "archived_sessions"
            session_root = root / ".codex" / "sessions" / "2026" / "03" / "26"
            archived_root.mkdir(parents=True)
            session_root.mkdir(parents=True)
            (session_root / "current.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "current-session",
                                    "cwd": "/workspace/ContextGO",
                                    "timestamp": "2026-03-26T00:00:00Z",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {
                                    "type": "user_message",
                                    "message": "仓库：/workspace/ContextGO。你负责 GitHub notebookLM 测试。",
                                },
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            (archived_root / "archived.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "archived-session",
                                    "cwd": "/tmp/github-research",
                                    "timestamp": "2026-03-06T00:00:00Z",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {
                                    "type": "user_message",
                                    "message": "继续搜索 GitHub 和 X，研究 notebookLM 的终端调用方案",
                                },
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            db_path = root / "session_index.db"
            query = "继续搜索 GitHub 和 X 研究 notebookLM 的终端调用方案"
            with (
                mock.patch.object(session_index, "_home", return_value=root),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
                mock.patch("pathlib.Path.cwd", return_value=Path("/workspace/ContextGO")),
            ):
                session_index.sync_session_index(force=True)
                rows = session_index._search_rows(query, limit=5, literal=True)
            self.assertEqual(rows[0]["session_id"], "archived-session")


class SessionIndexParserTests(unittest.TestCase):
    """Tests for individual parser functions."""

    # ------------------------------------------------------------------
    # _iso_to_epoch
    # ------------------------------------------------------------------

    def test_iso_to_epoch_valid_utc(self) -> None:
        epoch = session_index._iso_to_epoch("2026-03-25T00:00:00Z", 0)
        self.assertGreater(epoch, 0)

    def test_iso_to_epoch_none_returns_fallback(self) -> None:
        self.assertEqual(session_index._iso_to_epoch(None, 999), 999)

    def test_iso_to_epoch_empty_string_returns_fallback(self) -> None:
        self.assertEqual(session_index._iso_to_epoch("", 42), 42)

    def test_iso_to_epoch_whitespace_returns_fallback(self) -> None:
        self.assertEqual(session_index._iso_to_epoch("   ", 7), 7)

    def test_iso_to_epoch_invalid_returns_fallback(self) -> None:
        self.assertEqual(session_index._iso_to_epoch("not-a-date", 100), 100)

    # ------------------------------------------------------------------
    # _collect_content_text
    # ------------------------------------------------------------------

    def test_collect_content_text_non_list_returns_empty(self) -> None:
        self.assertEqual(session_index._collect_content_text("not a list"), [])

    def test_collect_content_text_non_dict_item_skipped(self) -> None:
        self.assertEqual(session_index._collect_content_text(["string", 42, None]), [])

    def test_collect_content_text_extracts_text_types(self) -> None:
        items = [
            {"type": "input_text", "text": "hello"},
            {"type": "output_text", "text": "world"},
            {"type": "text", "text": "!"},
            {"type": "ignored_type", "text": "skip me"},
        ]
        result = session_index._collect_content_text(items)
        self.assertEqual(result, ["hello", "world", "!"])

    def test_collect_content_text_skips_empty_text(self) -> None:
        items = [{"type": "text", "text": "  "}, {"type": "text", "text": "hi"}]
        result = session_index._collect_content_text(items)
        self.assertEqual(result, ["hi"])

    # ------------------------------------------------------------------
    # _truncate
    # ------------------------------------------------------------------

    def test_truncate_respects_max_chars(self) -> None:
        # Each "x"*50 + separator accounts for ~51 chars; at max_chars=100 the second piece is clipped.
        texts = ["x" * 50, "y" * 50, "z" * 50]
        result = session_index._truncate(texts, max_chars=100)
        self.assertLessEqual(len(result), 100)

    def test_truncate_skips_remaining_zero(self) -> None:
        # A single text longer than max_chars gets truncated.
        result = session_index._truncate(["a" * 200], max_chars=10)
        self.assertEqual(len(result), 10)

    def test_truncate_empty_texts_returns_empty(self) -> None:
        self.assertEqual(session_index._truncate([]), "")

    # ------------------------------------------------------------------
    # _normalize_file_path OSError fallback
    # ------------------------------------------------------------------

    def test_normalize_file_path_resolve_oserror_fallback(self) -> None:
        with mock.patch.object(Path, "resolve", side_effect=OSError("mock resolve error")):
            p = Path("/some/path/file.jsonl")
            result = session_index._normalize_file_path(p)
        self.assertEqual(result, str(p))

    # ------------------------------------------------------------------
    # build_query_terms – date path
    # ------------------------------------------------------------------

    def test_build_query_terms_date_format(self) -> None:
        terms = session_index.build_query_terms("2026/03/25")
        # Should produce normalised date strings
        self.assertTrue(any("2026" in t for t in terms))

    def test_build_query_terms_empty_returns_empty(self) -> None:
        self.assertEqual(session_index.build_query_terms(""), [])

    def test_build_query_terms_stopwords_filtered(self) -> None:
        # Individual stopwords should be filtered; each token must be >= 2 chars and a stopword
        # "the" is a stopword, "search" is a stopword, "please" is a stopword
        terms = session_index.build_query_terms("the search please")
        for term in terms:
            self.assertNotIn(term.lower(), session_index.STOPWORDS)

    def test_build_query_terms_path_token(self) -> None:
        terms = session_index.build_query_terms("/workspace/ContextGO/scripts/session_index.py")
        lowered = [t.lower() for t in terms]
        # Path token basename should appear
        self.assertTrue(any("session_index" in t for t in lowered))

    # ------------------------------------------------------------------
    # _parse_claude_session
    # ------------------------------------------------------------------

    def test_parse_claude_session_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "claude_session.jsonl"
            p.write_text(
                "\n".join([
                    json.dumps({
                        "type": "user",
                        "sessionId": "claude-abc",
                        "cwd": "/tmp/claude-project",
                        "timestamp": "2026-03-25T10:00:00Z",
                        "message": {"content": "research claude integration"},
                    }),
                    json.dumps({
                        "type": "assistant",
                        "message": {
                            "content": [{"type": "text", "text": "Here is the answer."}]
                        },
                    }),
                ]),
                encoding="utf-8",
            )
            doc = session_index._parse_claude_session(p)
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertEqual(doc.session_id, "claude-abc")
        self.assertIn("claude-project", doc.title)

    def test_parse_claude_session_assistant_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "claude_assistant.jsonl"
            p.write_text(
                json.dumps({
                    "type": "assistant",
                    "sessionId": "assist-session",
                    "message": {
                        "content": [{"type": "output_text", "text": "important context about project"}]
                    },
                }),
                encoding="utf-8",
            )
            doc = session_index._parse_claude_session(p)
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertIn("important context", doc.content)

    # ------------------------------------------------------------------
    # _parse_history_jsonl
    # ------------------------------------------------------------------

    def test_parse_history_jsonl_display_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "history.jsonl"
            p.write_text(
                "\n".join([
                    json.dumps({"display": "ls -la"}),
                    json.dumps({"text": "git status"}),
                    json.dumps({"input": "python3 test.py"}),
                ]),
                encoding="utf-8",
            )
            doc = session_index._parse_history_jsonl(p, "codex_history")
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertIn("ls -la", doc.content)

    def test_parse_history_jsonl_empty_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "empty_history.jsonl"
            p.write_text("", encoding="utf-8")
            doc = session_index._parse_history_jsonl(p, "codex_history")
        self.assertIsNone(doc)

    # ------------------------------------------------------------------
    # _parse_shell_history
    # ------------------------------------------------------------------

    def test_parse_shell_history_plain_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / ".zsh_history"
            p.write_text("git status\npython3 test.py\n", encoding="utf-8")
            doc = session_index._parse_shell_history(p, "shell_zsh")
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertIn("git status", doc.content)

    def test_parse_shell_history_zsh_extended_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / ".zsh_history"
            p.write_text(": 1700000000:0;git push origin main\n", encoding="utf-8")
            doc = session_index._parse_shell_history(p, "shell_zsh")
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertIn("git push origin main", doc.content)

    def test_parse_shell_history_empty_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / ".bash_history"
            p.write_text("", encoding="utf-8")
            doc = session_index._parse_shell_history(p, "shell_bash")
        self.assertIsNone(doc)

    # ------------------------------------------------------------------
    # _parse_source dispatch
    # ------------------------------------------------------------------

    def test_parse_source_unknown_returns_none(self) -> None:
        result = session_index._parse_source("unknown_type", Path("/tmp/some_file.txt"))
        self.assertIsNone(result)

    def test_parse_source_dispatches_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / ".bash_history"
            p.write_text("echo hello\n", encoding="utf-8")
            doc = session_index._parse_source("shell_bash", p)
        self.assertIsNotNone(doc)

    def test_parse_source_dispatches_history_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "history.jsonl"
            p.write_text(json.dumps({"display": "my command"}), encoding="utf-8")
            doc = session_index._parse_source("codex_history", p)
        self.assertIsNotNone(doc)

    # ------------------------------------------------------------------
    # sync_session_index – removed stale entries
    # ------------------------------------------------------------------

    def test_sync_removes_stale_index_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "session_index.db"
            # Use a fake path that we control via _iter_sources mock
            fake_file = root / "stale.jsonl"
            fake_file.write_text(
                json.dumps({
                    "type": "session_meta",
                    "payload": {
                        "id": "stale-session",
                        "cwd": "/tmp/old",
                        "timestamp": "2026-01-01T00:00:00Z",
                    },
                }),
                encoding="utf-8",
            )
            with (
                mock.patch.object(session_index, "_home", return_value=root),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
            ):
                # First sync: inject the fake file via _iter_sources
                with mock.patch.object(
                    session_index, "_iter_sources",
                    return_value=[("codex_session", fake_file)],
                ):
                    stats1 = session_index.sync_session_index(force=True)
                self.assertEqual(stats1["added"], 1)
                # Second sync: _iter_sources returns empty so stale entry is removed
                with mock.patch.object(session_index, "_iter_sources", return_value=[]):
                    stats2 = session_index.sync_session_index(force=True)
                self.assertEqual(stats2["removed"], 1)

    # ------------------------------------------------------------------
    # sync_session_index – update existing entry
    # ------------------------------------------------------------------

    def test_sync_updates_changed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_root = root / ".codex" / "sessions"
            codex_root.mkdir(parents=True)
            session_file = codex_root / "update.jsonl"
            session_file.write_text(
                json.dumps({
                    "type": "session_meta",
                    "payload": {
                        "id": "update-session",
                        "cwd": "/tmp/project",
                        "timestamp": "2026-01-01T00:00:00Z",
                    },
                }),
                encoding="utf-8",
            )
            db_path = root / "session_index.db"
            with (
                mock.patch.object(session_index, "_home", return_value=root),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
            ):
                stats1 = session_index.sync_session_index(force=True)
                self.assertEqual(stats1["added"], 1)
                # Change the file content to simulate an update.
                session_file.write_text(
                    "\n".join([
                        json.dumps({
                            "type": "session_meta",
                            "payload": {
                                "id": "update-session",
                                "cwd": "/tmp/project-v2",
                                "timestamp": "2026-01-02T00:00:00Z",
                            },
                        }),
                        json.dumps({
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "new content added"},
                        }),
                    ]),
                    encoding="utf-8",
                )
                stats2 = session_index.sync_session_index(force=True)
                self.assertEqual(stats2["updated"], 1)

    # ------------------------------------------------------------------
    # _is_noise_text
    # ------------------------------------------------------------------

    def test_is_noise_text_empty_returns_true(self) -> None:
        self.assertTrue(session_index._is_noise_text(""))

    def test_is_noise_text_normal_text_returns_false(self) -> None:
        self.assertFalse(session_index._is_noise_text("research NotebookLM integration"))

    def test_is_noise_text_skill_md_triple_returns_true(self) -> None:
        self.assertTrue(session_index._is_noise_text("SKILL.md SKILL.md SKILL.md repeated"))

    def test_is_noise_text_warmed_sampling_returns_true(self) -> None:
        self.assertTrue(session_index._is_noise_text("已预热 样本定位 done"))

    def test_is_noise_text_native_meta_returns_true(self) -> None:
        self.assertTrue(session_index._is_noise_text("主链不再是瓶颈 native 搜索结果质量 ok"))

    # ------------------------------------------------------------------
    # _search_noise_penalty – additional paths
    # ------------------------------------------------------------------

    def test_search_noise_penalty_guardian_truncated(self) -> None:
        penalty = session_index._search_noise_penalty("guardian_truncated content here", "", "")
        self.assertGreater(penalty, 0)

    def test_search_noise_penalty_chunk_id(self) -> None:
        penalty = session_index._search_noise_penalty("chunk id: 1234 wall time: 5ms", "", "")
        self.assertGreater(penalty, 0)

    def test_search_noise_penalty_ls_output(self) -> None:
        penalty = session_index._search_noise_penalty("drwxr-xr-x 2 user group\ntotal 12", "", "")
        self.assertGreater(penalty, 0)

    def test_search_noise_penalty_meta_terms_combo(self) -> None:
        penalty = session_index._search_noise_penalty(
            "notebooklm search session_index native-scan all together", "", ""
        )
        self.assertGreater(penalty, 0)

    # ------------------------------------------------------------------
    # _update_source_cache
    # ------------------------------------------------------------------

    def test_update_source_cache_stores_items(self) -> None:
        original = dict(session_index._SOURCE_CACHE)
        try:
            items = [("codex_session", Path("/tmp/test.jsonl"))]
            session_index._update_source_cache(items, 1000.0, "/home/test")
            if session_index.SOURCE_CACHE_TTL_SEC > 0:
                self.assertEqual(session_index._SOURCE_CACHE["items"], items)
                self.assertEqual(session_index._SOURCE_CACHE["home"], "/home/test")
        finally:
            session_index._SOURCE_CACHE.update(original)

    # ------------------------------------------------------------------
    # _make_flat_doc returns None when no content
    # ------------------------------------------------------------------

    def test_make_flat_doc_no_texts_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "empty.jsonl"
            p.write_text("", encoding="utf-8")
            result = session_index._make_flat_doc(p, "codex_history", [], int(p.stat().st_mtime))
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # _finish_session_doc – no title uses parent posix path
    # ------------------------------------------------------------------

    def test_finish_session_doc_no_title_uses_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "sub" / "session.jsonl"
            p.parent.mkdir(parents=True)
            p.write_text("hello", encoding="utf-8")
            mtime = int(p.stat().st_mtime)
            doc = session_index._finish_session_doc(p, "codex_session", "sid", "", "2026-03-25T00:00:00Z", ["content"], mtime)
        self.assertIn("sub", doc.title)

    def test_finish_session_doc_no_content_uses_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "session.jsonl"
            p.write_text("hello", encoding="utf-8")
            mtime = int(p.stat().st_mtime)
            doc = session_index._finish_session_doc(p, "codex_session", "sid", "my title", "2026-03-25T00:00:00Z", [], mtime)
        self.assertEqual(doc.content, "my title")

    # ------------------------------------------------------------------
    # get_session_db_path – no override uses storage root
    # ------------------------------------------------------------------

    def test_get_session_db_path_no_override(self) -> None:
        with mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: ""}, clear=False):
            path = session_index.get_session_db_path()
        self.assertTrue(str(path).endswith("session_index.db"))

    # ------------------------------------------------------------------
    # format_search_results – no matches path
    # ------------------------------------------------------------------

    def test_format_search_results_no_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "empty.db"
            with (
                mock.patch.object(session_index, "_home", return_value=Path(tmpdir)),
                mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False),
            ):
                text = session_index.format_search_results("xyzzy_no_match_ever", limit=5)
        self.assertIn("No matches", text)

    # ------------------------------------------------------------------
    # _iter_jsonl_objects – invalid JSON is skipped
    # ------------------------------------------------------------------

    def test_iter_jsonl_objects_skips_invalid_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "mixed.jsonl"
            p.write_text('{"valid": 1}\nnot json\n{"valid": 2}\n', encoding="utf-8")
            objects = list(session_index._iter_jsonl_objects(p))
        self.assertEqual(len(objects), 2)
        self.assertEqual(objects[0]["valid"], 1)
        self.assertEqual(objects[1]["valid"], 2)

    # ------------------------------------------------------------------
    # _meta_get and _meta_set
    # ------------------------------------------------------------------

    def test_meta_get_missing_key_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "meta_test.db"
            with mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False):
                session_index.ensure_session_db()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                result = session_index._meta_get(conn, "nonexistent_key")
                self.assertIsNone(result)
            finally:
                conn.close()

    def test_meta_set_and_get_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "meta_test2.db"
            with mock.patch.dict(os.environ, {session_index.SESSION_DB_PATH_ENV: str(db_path)}, clear=False):
                session_index.ensure_session_db()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                session_index._meta_set(conn, "test_key", "test_value")
                conn.commit()
                result = session_index._meta_get(conn, "test_key")
                self.assertEqual(result, "test_value")
            finally:
                conn.close()


class MemoryIndexTests(unittest.TestCase):
    """Tests for memory_index module functionality."""

    def setUp(self) -> None:
        # Import memory_index in setUp to avoid import-time side effects
        import memory_index
        self.memory_index = memory_index

    def _make_db_env(self, tmpdir: str) -> dict[str, str]:
        return {"MEMORY_INDEX_DB_PATH": str(Path(tmpdir) / "memory_index.db")}

    def test_strip_private_blocks_removes_block(self) -> None:
        text = "public <private>secret stuff</private> end"
        result = self.memory_index.strip_private_blocks(text)
        self.assertNotIn("secret", result)
        self.assertIn("public", result)

    def test_strip_private_blocks_empty_returns_empty(self) -> None:
        self.assertEqual(self.memory_index.strip_private_blocks(""), "")

    def test_strip_private_blocks_stray_tags_removed(self) -> None:
        text = "before </private> after"
        result = self.memory_index.strip_private_blocks(text)
        self.assertNotIn("</private>", result)

    def test_to_epoch_valid_iso(self) -> None:
        epoch = self.memory_index._to_epoch("2026-03-25T00:00:00", 0)
        self.assertGreater(epoch, 0)

    def test_to_epoch_empty_returns_fallback(self) -> None:
        self.assertEqual(self.memory_index._to_epoch("", 999), 999)

    def test_to_epoch_invalid_returns_fallback(self) -> None:
        self.assertEqual(self.memory_index._to_epoch("not-a-date", 42), 42)

    def test_ensure_index_db_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory_index.db"
            with mock.patch.dict(os.environ, {"MEMORY_INDEX_DB_PATH": str(db_path)}, clear=False):
                result = self.memory_index.ensure_index_db()
            self.assertTrue(result.exists())
            self.assertEqual(str(result), str(db_path))

    def test_index_stats_returns_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                stats = self.memory_index.index_stats()
        self.assertIn("db_path", stats)
        self.assertIn("total_observations", stats)
        self.assertIn("latest_epoch", stats)
        self.assertEqual(stats["total_observations"], 0)
        self.assertEqual(stats["latest_epoch"], 0)

    def test_search_index_empty_returns_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                results = self.memory_index.search_index("test query")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    def test_search_index_with_source_type_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                results = self.memory_index.search_index("test", source_type="history")
        self.assertIsInstance(results, list)

    def test_search_index_with_date_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                results = self.memory_index.search_index("test", date_start_epoch=1000000, date_end_epoch=9999999999)
        self.assertIsInstance(results, list)

    def test_get_observations_by_ids_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                results = self.memory_index.get_observations_by_ids([])
        self.assertEqual(results, [])

    def test_timeline_index_missing_anchor_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                results = self.memory_index.timeline_index(99999)
        self.assertEqual(results, [])

    def test_get_index_db_path_override(self) -> None:
        custom = "/tmp/custom_memory.db"
        with mock.patch.dict(os.environ, {"MEMORY_INDEX_DB_PATH": custom}, clear=False):
            path = self.memory_index.get_index_db_path()
        self.assertEqual(str(path), custom)

    def test_import_observations_invalid_type_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                with self.assertRaises(ValueError):
                    self.memory_index.import_observations_payload(
                        {"observations": "not a list"}, sync_from_storage=False
                    )

    def test_import_and_search_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                payload = {
                    "observations": [
                        {
                            "source_type": "import",
                            "session_id": "test-session",
                            "title": "Test Observation",
                            "content": "This is a test memory about NotebookLM integration",
                            "tags": ["test", "memory"],
                            "file_path": "import://test",
                            "created_at": "2026-03-25T00:00:00",
                            "created_at_epoch": 1742860800,
                        }
                    ]
                }
                result = self.memory_index.import_observations_payload(payload, sync_from_storage=False)
                self.assertEqual(result["inserted"], 1)
                self.assertEqual(result["skipped"], 0)
                # Search should find it
                found = self.memory_index.search_index("NotebookLM")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["title"], "Test Observation")

    def test_import_skips_empty_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                payload = {
                    "observations": [
                        {"source_type": "import", "session_id": "s1", "title": "empty", "content": ""},
                        {"source_type": "import", "session_id": "s2", "title": "also empty", "content": "   "},
                    ]
                }
                result = self.memory_index.import_observations_payload(payload, sync_from_storage=False)
                self.assertEqual(result["inserted"], 0)
                self.assertEqual(result["skipped"], 2)

    def test_import_skips_duplicate_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                obs = {
                    "source_type": "import",
                    "session_id": "dup-session",
                    "title": "Dup Obs",
                    "content": "unique content for duplicate test",
                    "created_at_epoch": 1742860800,
                }
                payload = {"observations": [obs]}
                r1 = self.memory_index.import_observations_payload(payload, sync_from_storage=False)
                r2 = self.memory_index.import_observations_payload(payload, sync_from_storage=False)
                self.assertEqual(r1["inserted"], 1)
                self.assertEqual(r2["inserted"], 0)
                self.assertEqual(r2["skipped"], 1)

    def test_import_sanitizes_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                obs = {
                    "source_type": "import",
                    "session_id": "path-test",
                    "title": "Path Test",
                    "content": "valid content about project",
                    "file_path": "/home/user/secret/path.md",
                    "created_at_epoch": 1742860800,
                }
                result = self.memory_index.import_observations_payload(
                    {"observations": [obs]}, sync_from_storage=False
                )
                self.assertEqual(result["inserted"], 1)
                found = self.memory_index.search_index("valid content")
                self.assertEqual(found[0]["file_path"], "import://local-path-redacted")

    def test_export_observations_payload_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Must also mock sync_index_from_storage to avoid scanning real dirs
            with (
                mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False),
                mock.patch.object(
                    self.memory_index, "sync_index_from_storage",
                    return_value={"scanned": 0, "added": 0, "updated": 0, "removed": 0}
                ),
            ):
                payload = self.memory_index.export_observations_payload()
        self.assertIn("exported_at", payload)
        self.assertIn("observations", payload)
        self.assertIn("sync", payload)
        self.assertIn("total_observations", payload)

    def test_normalize_import_observation_tilde_path_redacted(self) -> None:
        raw = {
            "source_type": "import",
            "session_id": "s1",
            "title": "tilde test",
            "content": "some content here",
            "file_path": "~/secret/path.md",
            "created_at_epoch": 1742860800,
        }
        result = self.memory_index._normalize_import_observation(raw)
        self.assertEqual(result["file_path"], "import://local-path-redacted")

    def test_normalize_import_observation_generates_fingerprint(self) -> None:
        raw = {
            "source_type": "import",
            "session_id": "s1",
            "title": "fp test",
            "content": "content for fingerprint generation",
        }
        result = self.memory_index._normalize_import_observation(raw)
        self.assertTrue(len(result["fingerprint"]) > 0)

    def test_normalize_import_observation_list_tags(self) -> None:
        raw = {
            "source_type": "import",
            "session_id": "s1",
            "title": "tag test",
            "content": "content",
            "tags": ["python", "testing"],
        }
        result = self.memory_index._normalize_import_observation(raw)
        tags = json.loads(result["tags_json"])
        self.assertIn("python", tags)
        self.assertIn("testing", tags)

    def test_parse_markdown_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "note.md"
            p.write_text(
                "# My Note\ntags: python, testing\ndate: 2026-03-25T10:00:00\n## content\nThis is the body.",
                encoding="utf-8",
            )
            obs = self.memory_index._parse_markdown(p)
        self.assertIsNotNone(obs)
        assert obs is not None
        self.assertEqual(obs.title, "My Note")
        self.assertIn("body", obs.content)

    def test_parse_markdown_empty_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "empty.md"
            p.write_text("", encoding="utf-8")
            obs = self.memory_index._parse_markdown(p)
        self.assertIsNone(obs)

    def test_parse_markdown_oserror_returns_none(self) -> None:
        p = Path("/nonexistent/path/file.md")
        obs = self.memory_index._parse_markdown(p)
        self.assertIsNone(obs)

    def test_parse_markdown_private_content_stripped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "private.md"
            p.write_text(
                "# Secret Note\n## content\nPublic info. <private>secret token sk-abc123</private> more public.",
                encoding="utf-8",
            )
            obs = self.memory_index._parse_markdown(p)
        self.assertIsNotNone(obs)
        assert obs is not None
        self.assertNotIn("secret token", obs.content)
        self.assertIn("Public info", obs.content)

    def test_parse_markdown_conversation_source_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conv_dir = Path(tmpdir) / "conversations"
            conv_dir.mkdir()
            p = conv_dir / "conv_note.md"
            p.write_text("# Conv Note\n## content\nConversation content.", encoding="utf-8")
            obs = self.memory_index._parse_markdown(p)
        self.assertIsNotNone(obs)
        assert obs is not None
        self.assertEqual(obs.source_type, "conversation")

    def test_obs_where_clause_empty_query(self) -> None:
        clause, args = self.memory_index._obs_where_clause("", "all")
        self.assertEqual(clause, "")
        self.assertEqual(args, [])

    def test_obs_where_clause_with_query_and_source(self) -> None:
        clause, args = self.memory_index._obs_where_clause("python", "history")
        self.assertIn("LIKE", clause)
        self.assertIn("source_type", clause)
        self.assertTrue(len(args) >= 4)

    def test_get_observations_by_ids_returns_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                # Insert an observation first
                payload = {
                    "observations": [{
                        "source_type": "import",
                        "session_id": "id-test",
                        "title": "ID Fetch Test",
                        "content": "content for id fetch test",
                        "created_at_epoch": 1742860800,
                    }]
                }
                self.memory_index.import_observations_payload(payload, sync_from_storage=False)
                all_results = self.memory_index.search_index("id fetch test")
                self.assertEqual(len(all_results), 1)
                obs_id = all_results[0]["id"]
                by_id = self.memory_index.get_observations_by_ids([obs_id])
                self.assertEqual(len(by_id), 1)
                self.assertEqual(by_id[0]["title"], "ID Fetch Test")

    def test_timeline_index_with_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, self._make_db_env(tmpdir), clear=False):
                # Insert multiple observations
                for i in range(5):
                    payload = {
                        "observations": [{
                            "source_type": "import",
                            "session_id": f"timeline-{i}",
                            "title": f"Timeline Obs {i}",
                            "content": f"content for timeline test {i}",
                            "created_at_epoch": 1742860800 + i * 100,
                        }]
                    }
                    self.memory_index.import_observations_payload(payload, sync_from_storage=False)
                all_results = self.memory_index.search_index("timeline test")
                self.assertGreaterEqual(len(all_results), 3)
                # Use middle item as anchor
                anchor_id = all_results[len(all_results) // 2]["id"]
                timeline = self.memory_index.timeline_index(anchor_id, depth_before=2, depth_after=2)
                self.assertIsInstance(timeline, list)
                self.assertGreater(len(timeline), 0)


if __name__ == "__main__":
    unittest.main()
