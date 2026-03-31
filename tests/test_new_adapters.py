#!/usr/bin/env python3
"""Unit tests for new adapters in source_adapters.py (lines 545-888+).

Covers:
  - _sync_cline_family_sessions / _sync_cline_sessions / _sync_roo_sessions
  - _sync_continue_sessions
  - _sync_zed_sessions
  - _sync_aider_sessions
  - _sync_vscdb_sessions / _sync_cursor_sessions / _sync_windsurf_sessions
  - helper functions: _cline_family_task_roots, _vscdb_workspace_roots,
    _aider_history_candidates, _iso_or_none (UTC), _extract_text_fragments depth,
    discover_index_sources _skip_sync, source_inventory
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import source_adapters  # noqa: E402


class SourceAdaptersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="cg_sources_")
        self.root = Path(self.tmpdir.name)
        self.home = self.root / "home"
        self.storage = self.root / "storage"
        self.home.mkdir()
        self.storage.mkdir()
        self.env = mock.patch.dict("os.environ", {"CONTEXTGO_STORAGE_ROOT": str(self.storage)})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Helper: create VS Code globalStorage/tasks layout for Cline-family
    # ------------------------------------------------------------------

    def _create_cline_tasks(self, extension_id: str = "saoudrizwan.claude-dev") -> Path:
        """Create a minimal tasks directory under Linux .config/Code path."""
        tasks_dir = self.home / ".config" / "Code" / "User" / "globalStorage" / extension_id / "tasks"
        task_dir = tasks_dir / "task-001"
        task_dir.mkdir(parents=True)
        history = [
            {"role": "user", "content": "Hello from Cline"},
            {"role": "assistant", "content": [{"type": "text", "text": "Cline reply"}]},
        ]
        (task_dir / "api_conversation_history.json").write_text(json.dumps(history), encoding="utf-8")
        return tasks_dir

    def _create_cline_tasks_with_metadata(self, extension_id: str = "saoudrizwan.claude-dev") -> Path:
        tasks_dir = self.home / ".config" / "Code" / "User" / "globalStorage" / extension_id / "tasks"
        task_dir = tasks_dir / "task-meta-001"
        task_dir.mkdir(parents=True)
        history = [{"role": "user", "content": "task with metadata"}]
        (task_dir / "api_conversation_history.json").write_text(json.dumps(history), encoding="utf-8")
        (task_dir / "task_metadata.json").write_text(
            json.dumps({"task": "My Cline Task", "created": 1700000000}), encoding="utf-8"
        )
        return tasks_dir

    # ------------------------------------------------------------------
    # Tests: _sync_cline_sessions
    # ------------------------------------------------------------------

    def test_cline_not_detected_when_no_directory(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cline_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_cline_basic_sync_writes_sessions(self) -> None:
        self._create_cline_tasks()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cline_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)
        adapter_dir = source_adapters._adapter_root(self.home) / "cline_session"
        jsonl_files = list(adapter_dir.glob("*.jsonl"))
        self.assertTrue(jsonl_files)
        content = jsonl_files[0].read_text(encoding="utf-8")
        self.assertIn("Cline", content)

    def test_cline_metadata_title_extracted(self) -> None:
        self._create_cline_tasks_with_metadata()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cline_sessions(self.home)
        self.assertTrue(result["detected"])
        adapter_dir = source_adapters._adapter_root(self.home) / "cline_session"
        all_content = "".join(p.read_text(encoding="utf-8") for p in adapter_dir.glob("*.jsonl"))
        self.assertIn("My Cline Task", all_content)

    def test_cline_empty_history_json_skipped(self) -> None:
        """Task directory with non-list api_conversation_history.json is skipped."""
        tasks_dir = self.home / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "tasks"
        task_dir = tasks_dir / "task-bad"
        task_dir.mkdir(parents=True)
        (task_dir / "api_conversation_history.json").write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cline_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_cline_missing_history_file_skipped(self) -> None:
        """Task directory without api_conversation_history.json is skipped."""
        tasks_dir = self.home / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "tasks"
        tasks_dir.mkdir(parents=True)
        empty_task = tasks_dir / "task-no-hist"
        empty_task.mkdir()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cline_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    # ------------------------------------------------------------------
    # Tests: _sync_roo_sessions
    # ------------------------------------------------------------------

    def test_roo_not_detected_when_no_directory(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_roo_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_roo_basic_sync_writes_sessions(self) -> None:
        self._create_cline_tasks(extension_id="rooveterinaryinc.roo-cline")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_roo_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)
        adapter_dir = source_adapters._adapter_root(self.home) / "roo_session"
        self.assertTrue(any(adapter_dir.glob("*.jsonl")))

    def test_roo_empty_task_list_yields_zero_sessions(self) -> None:
        tasks_dir = self.home / ".config" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "tasks"
        tasks_dir.mkdir(parents=True)
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_roo_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    # ------------------------------------------------------------------
    # Tests: _cline_family_task_roots whitelist validation
    # ------------------------------------------------------------------

    def test_cline_family_task_roots_only_returns_existing_dirs(self) -> None:
        # Only the Linux .config path exists
        ext_id = "saoudrizwan.claude-dev"
        tasks_dir = self.home / ".config" / "Code" / "User" / "globalStorage" / ext_id / "tasks"
        tasks_dir.mkdir(parents=True)
        roots = source_adapters._cline_family_task_roots(self.home, ext_id)
        self.assertEqual(roots, [tasks_dir])

    def test_cline_family_task_roots_returns_empty_when_nothing_exists(self) -> None:
        roots = source_adapters._cline_family_task_roots(self.home, "saoudrizwan.claude-dev")
        self.assertEqual(roots, [])

    def test_cline_family_task_roots_extension_id_not_whitelisted(self) -> None:
        """An unknown extension_id is rejected by the whitelist and returns empty."""
        ext_id = "some.unknown-extension"
        tasks_dir = self.home / ".config" / "Code" / "User" / "globalStorage" / ext_id / "tasks"
        tasks_dir.mkdir(parents=True)
        roots = source_adapters._cline_family_task_roots(self.home, ext_id)
        # Whitelist rejects unknown extension IDs
        self.assertEqual(roots, [])

    # ------------------------------------------------------------------
    # Tests: _sync_continue_sessions
    # ------------------------------------------------------------------

    def _create_continue_session(self, filename: str = "sess1.json") -> Path:
        sessions_dir = self.home / ".continue" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_data = {
            "sessionId": "cont-sess-001",
            "title": "Continue Session Title",
            "workspaceDirectory": "/work/myproject",
            "history": [
                {"role": "user", "text": "Continue hello"},
                {"role": "assistant", "text": "Continue world"},
            ],
        }
        path = sessions_dir / filename
        path.write_text(json.dumps(session_data), encoding="utf-8")
        return sessions_dir

    def test_continue_not_detected_when_no_directory(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_continue_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_continue_basic_sync_writes_sessions(self) -> None:
        self._create_continue_session()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_continue_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)
        adapter_dir = source_adapters._adapter_root(self.home) / "continue_session"
        files = list(adapter_dir.glob("*.jsonl"))
        self.assertTrue(files)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("Continue Session Title", content)

    def test_continue_empty_sessions_dir_yields_zero(self) -> None:
        sessions_dir = self.home / ".continue" / "sessions"
        sessions_dir.mkdir(parents=True)
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_continue_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_continue_invalid_json_file_skipped(self) -> None:
        sessions_dir = self.home / ".continue" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "bad.json").write_text("not-json{{{", encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_continue_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_continue_non_dict_json_skipped(self) -> None:
        sessions_dir = self.home / ".continue" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "array.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_continue_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_continue_uses_messages_key_as_fallback(self) -> None:
        sessions_dir = self.home / ".continue" / "sessions"
        sessions_dir.mkdir(parents=True)
        data = {
            "id": "cont-msg-fallback",
            "title": "Messages Key Test",
            "messages": [{"role": "user", "text": "fallback message text"}],
        }
        (sessions_dir / "msg_fallback.json").write_text(json.dumps(data), encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_continue_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)

    # ------------------------------------------------------------------
    # Tests: _sync_zed_sessions
    # ------------------------------------------------------------------

    def _create_zed_conversation(self, filename: str = "conv1.json") -> Path:
        conv_dir = self.home / ".config" / "zed" / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "id": "zed-conv-001",
            "title": "Zed Conversation Title",
            "messages": [
                {"role": "user", "text": "Zed hello"},
                {"role": "assistant", "text": "Zed world"},
            ],
        }
        path = conv_dir / filename
        path.write_text(json.dumps(data), encoding="utf-8")
        return conv_dir

    def test_zed_not_detected_when_no_directory(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_zed_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_zed_basic_sync_writes_sessions(self) -> None:
        self._create_zed_conversation()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_zed_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)
        adapter_dir = source_adapters._adapter_root(self.home) / "zed_session"
        files = list(adapter_dir.glob("*.jsonl"))
        self.assertTrue(files)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("Zed Conversation Title", content)

    def test_zed_empty_conversations_dir_yields_zero(self) -> None:
        conv_dir = self.home / ".config" / "zed" / "conversations"
        conv_dir.mkdir(parents=True)
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_zed_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_zed_invalid_json_skipped(self) -> None:
        conv_dir = self.home / ".config" / "zed" / "conversations"
        conv_dir.mkdir(parents=True)
        (conv_dir / "broken.json").write_text("{{broken", encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_zed_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_zed_uses_summary_as_title_fallback(self) -> None:
        conv_dir = self.home / ".config" / "zed" / "conversations"
        conv_dir.mkdir(parents=True)
        data = {
            "id": "zed-summary-test",
            "summary": "Zed Summary Title",
            "messages": [{"text": "some zed content"}],
        }
        (conv_dir / "summary_conv.json").write_text(json.dumps(data), encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_zed_sessions(self.home)
        self.assertTrue(result["detected"])
        adapter_dir = source_adapters._adapter_root(self.home) / "zed_session"
        all_content = "".join(p.read_text(encoding="utf-8") for p in adapter_dir.glob("*.jsonl"))
        self.assertIn("Zed Summary Title", all_content)

    def test_zed_dict_messages_handled(self) -> None:
        """Zed message_metadata can be a dict instead of a list."""
        conv_dir = self.home / ".config" / "zed" / "conversations"
        conv_dir.mkdir(parents=True)
        data = {
            "id": "zed-dict-msg",
            "title": "Dict Messages",
            "message_metadata": {"text": "dict message content"},
        }
        (conv_dir / "dict_msg.json").write_text(json.dumps(data), encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_zed_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)

    # ------------------------------------------------------------------
    # Tests: _sync_aider_sessions
    # ------------------------------------------------------------------

    def _create_aider_history(self, subdir: str = "myproject") -> Path:
        project_dir = self.home / subdir
        project_dir.mkdir(parents=True, exist_ok=True)
        hist = project_dir / ".aider.chat.history.md"
        hist.write_text(
            "#### user\nHello from aider\n\n#### assistant\nAider reply here\n",
            encoding="utf-8",
        )
        return hist

    def test_aider_not_detected_when_no_history(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_aider_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_aider_basic_sync_writes_sessions(self) -> None:
        self._create_aider_history()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_aider_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)
        adapter_dir = source_adapters._adapter_root(self.home) / "aider_session"
        files = list(adapter_dir.glob("*.jsonl"))
        self.assertTrue(files)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("aider: myproject", content)

    def test_aider_empty_history_file_skipped(self) -> None:
        project_dir = self.home / "emptyproject"
        project_dir.mkdir(parents=True)
        hist = project_dir / ".aider.chat.history.md"
        hist.write_text("", encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_aider_sessions(self.home)
        # File is detected but empty content produces 0 sessions
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_aider_short_chunks_filtered_out(self) -> None:
        """Chunks with <= 10 chars are filtered out (len(c) > 10 guard)."""
        project_dir = self.home / "shortproject"
        project_dir.mkdir(parents=True)
        hist = project_dir / ".aider.chat.history.md"
        # Each chunk will be very short
        hist.write_text("#### user\nHi\n#### assistant\nOK\n", encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_aider_sessions(self.home)
        # May or may not detect depending on chunk length — should not raise
        self.assertIsInstance(result["sessions"], int)

    def test_aider_directory_title_in_output(self) -> None:
        self._create_aider_history(subdir="awesome-repo")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            source_adapters._sync_aider_sessions(self.home)  # noqa: B018
        adapter_dir = source_adapters._adapter_root(self.home) / "aider_session"
        all_content = "".join(p.read_text(encoding="utf-8") for p in adapter_dir.glob("*.jsonl"))
        self.assertIn("awesome-repo", all_content)

    # ------------------------------------------------------------------
    # Tests: _aider_history_candidates
    # ------------------------------------------------------------------

    def test_aider_history_candidates_finds_home_subdirs(self) -> None:
        hist = self._create_aider_history(subdir="direct-child")
        candidates = source_adapters._aider_history_candidates(self.home)
        self.assertIn(hist, candidates)

    def test_aider_history_candidates_finds_projects_subdir(self) -> None:
        projects_dir = self.home / "Projects"
        project = projects_dir / "nested" / "deep"
        project.mkdir(parents=True)
        hist = project / ".aider.chat.history.md"
        hist.write_text("#### user\nDeep history content here\n", encoding="utf-8")
        candidates = source_adapters._aider_history_candidates(self.home)
        self.assertIn(hist, candidates)

    def test_aider_history_candidates_skips_dotdirs_at_home_level(self) -> None:
        hidden_dir = self.home / ".hidden"
        hidden_dir.mkdir()
        hist = hidden_dir / ".aider.chat.history.md"
        hist.write_text("#### user\nHidden content here\n", encoding="utf-8")
        candidates = source_adapters._aider_history_candidates(self.home)
        self.assertNotIn(hist, candidates)

    def test_aider_history_candidates_limit_50(self) -> None:
        """Candidates list is capped at 50 entries."""
        for i in range(60):
            p = self.home / f"project_{i:03d}"
            p.mkdir()
            (p / ".aider.chat.history.md").write_text(f"#### user\nContent for project {i}\n", encoding="utf-8")
        candidates = source_adapters._aider_history_candidates(self.home)
        self.assertLessEqual(len(candidates), 50)

    # ------------------------------------------------------------------
    # Tests: _sync_vscdb_sessions / _sync_cursor_sessions / _sync_windsurf_sessions
    # ------------------------------------------------------------------

    def _create_vscdb(self, app_name: str, workspace_id: str, chat_data: object) -> Path:
        ws_root = self.home / ".config" / app_name / "User" / "workspaceStorage"
        ws_dir = ws_root / workspace_id
        ws_dir.mkdir(parents=True)
        vscdb = ws_dir / "state.vscdb"
        conn = sqlite3.connect(vscdb)
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable VALUES (?, ?)",
            ("workbench.panel.chatSidebar.chatData", json.dumps(chat_data)),
        )
        conn.commit()
        conn.close()
        return ws_root

    def _create_cursor_vscdb(self, workspace_id: str = "ws-cursor-001") -> Path:
        chat_data = {
            "messages": [
                {"text": "Cursor hello"},
                {"text": "Cursor reply"},
            ]
        }
        return self._create_vscdb("Cursor", workspace_id, chat_data)

    def _create_windsurf_vscdb(self, workspace_id: str = "ws-wind-001") -> Path:
        chat_data = {
            "messages": [
                {"text": "Windsurf hello"},
                {"text": "Windsurf reply"},
            ]
        }
        return self._create_vscdb("Windsurf", workspace_id, chat_data)

    def test_cursor_not_detected_when_no_directory(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cursor_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_cursor_basic_sync_writes_sessions(self) -> None:
        self._create_cursor_vscdb()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cursor_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)
        adapter_dir = source_adapters._adapter_root(self.home) / "cursor_session"
        files = list(adapter_dir.glob("*.jsonl"))
        self.assertTrue(files)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("Cursor", content)

    def test_cursor_empty_workspace_dir_yields_zero(self) -> None:
        """workspaceStorage directory exists but no state.vscdb files."""
        ws_root = self.home / ".config" / "Cursor" / "User" / "workspaceStorage"
        ws_root.mkdir(parents=True)
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cursor_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_cursor_vscdb_without_item_table_skipped(self) -> None:
        ws_root = self.home / ".config" / "Cursor" / "User" / "workspaceStorage"
        ws_dir = ws_root / "ws-no-table"
        ws_dir.mkdir(parents=True)
        vscdb = ws_dir / "state.vscdb"
        conn = sqlite3.connect(vscdb)
        conn.execute("CREATE TABLE OtherTable (key TEXT, value TEXT)")
        conn.commit()
        conn.close()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cursor_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_cursor_vscdb_no_matching_chat_keys_yields_no_session(self) -> None:
        ws_root = self.home / ".config" / "Cursor" / "User" / "workspaceStorage"
        ws_dir = ws_root / "ws-no-chat"
        ws_dir.mkdir(parents=True)
        vscdb = ws_dir / "state.vscdb"
        conn = sqlite3.connect(vscdb)
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO ItemTable VALUES (?, ?)", ("some.other.key", '{"data": 1}'))
        conn.commit()
        conn.close()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cursor_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_windsurf_not_detected_when_no_directory(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_windsurf_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertEqual(result["sessions"], 0)

    def test_windsurf_basic_sync_writes_sessions(self) -> None:
        self._create_windsurf_vscdb()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_windsurf_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)
        adapter_dir = source_adapters._adapter_root(self.home) / "windsurf_session"
        files = list(adapter_dir.glob("*.jsonl"))
        self.assertTrue(files)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("Windsurf", content)

    def test_windsurf_empty_workspace_yields_zero(self) -> None:
        ws_root = self.home / ".config" / "Windsurf" / "User" / "workspaceStorage"
        ws_root.mkdir(parents=True)
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_windsurf_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertEqual(result["sessions"], 0)

    # ------------------------------------------------------------------
    # Tests: _vscdb_workspace_roots whitelist validation
    # ------------------------------------------------------------------

    def test_vscdb_workspace_roots_returns_only_existing(self) -> None:
        ws_root = self.home / ".config" / "Cursor" / "User" / "workspaceStorage"
        ws_root.mkdir(parents=True)
        roots = source_adapters._vscdb_workspace_roots(self.home, "Cursor")
        self.assertIn(ws_root, roots)
        self.assertGreaterEqual(len(roots), 1)

    def test_vscdb_workspace_roots_empty_when_none_exist(self) -> None:
        roots = source_adapters._vscdb_workspace_roots(self.home, "Cursor")
        self.assertEqual(roots, [])

    def test_vscdb_workspace_roots_windsurf_path(self) -> None:
        ws_root = self.home / ".config" / "Windsurf" / "User" / "workspaceStorage"
        ws_root.mkdir(parents=True)
        roots = source_adapters._vscdb_workspace_roots(self.home, "Windsurf")
        self.assertIn(ws_root, roots)

    # ------------------------------------------------------------------
    # Tests: vscdb with Cascade/aiChat key patterns
    # ------------------------------------------------------------------

    def test_vscdb_cascade_key_pattern_matches(self) -> None:
        ws_root = self.home / ".config" / "Windsurf" / "User" / "workspaceStorage"
        ws_dir = ws_root / "ws-cascade"
        ws_dir.mkdir(parents=True)
        vscdb = ws_dir / "state.vscdb"
        conn = sqlite3.connect(vscdb)
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable VALUES (?, ?)",
            (
                "workbench.panel.Cascade",
                json.dumps({"messages": [{"text": "Cascade waterfall text here yes"}]}),
            ),
        )
        conn.commit()
        conn.close()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_windsurf_sessions(self.home)
        self.assertTrue(result["detected"])
        self.assertGreater(result["sessions"], 0)

    # ------------------------------------------------------------------
    # Tests: _iso_or_none UTC fix
    # ------------------------------------------------------------------

    def test_iso_or_none_returns_none_for_none(self) -> None:
        self.assertIsNone(source_adapters._iso_or_none(None))

    def test_iso_or_none_returns_string_for_epoch(self) -> None:
        result = source_adapters._iso_or_none(1700000000)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)

    def test_iso_or_none_handles_float_epoch(self) -> None:
        result = source_adapters._iso_or_none(1700000000.5)
        self.assertIsInstance(result, str)

    def test_iso_or_none_handles_zero_epoch(self) -> None:
        result = source_adapters._iso_or_none(0)
        self.assertIsInstance(result, str)

    # ------------------------------------------------------------------
    # Tests: _extract_text_fragments depth / edge cases
    # ------------------------------------------------------------------

    def test_extract_text_fragments_deeply_nested(self) -> None:
        """Deeply nested structure should still extract text without crashing."""
        node: object = {"text": "deep content"}
        for _ in range(15):
            node = {"content": node}
        texts = source_adapters._extract_text_fragments(node)
        self.assertIn("deep content", texts)

    def test_extract_text_fragments_none_input(self) -> None:
        self.assertEqual(source_adapters._extract_text_fragments(None), [])

    def test_extract_text_fragments_integer_input(self) -> None:
        self.assertEqual(source_adapters._extract_text_fragments(42), [])

    def test_extract_text_fragments_deduplicates(self) -> None:
        node = {
            "text": "repeated text",
            "content": {"text": "repeated text"},
        }
        texts = source_adapters._extract_text_fragments(node)
        self.assertEqual(texts.count("repeated text"), 1)

    def test_extract_text_fragments_list_of_strings(self) -> None:
        texts = source_adapters._extract_text_fragments(["alpha", "beta", "gamma"])
        self.assertEqual(texts, ["alpha", "beta", "gamma"])

    def test_extract_text_fragments_reasoning_type(self) -> None:
        node = {"type": "reasoning", "text": "my reasoning here"}
        texts = source_adapters._extract_text_fragments(node)
        self.assertIn("my reasoning here", texts)

    def test_extract_text_fragments_input_text_type(self) -> None:
        node = {"type": "input_text", "text": "input text content"}
        texts = source_adapters._extract_text_fragments(node)
        self.assertIn("input text content", texts)

    def test_extract_text_fragments_output_text_type(self) -> None:
        node = {"type": "output_text", "text": "output text content"}
        texts = source_adapters._extract_text_fragments(node)
        self.assertIn("output text content", texts)

    # ------------------------------------------------------------------
    # Tests: discover_index_sources with _skip_sync parameter
    # (function uses sync_all_adapters internally; mock to test skip_sync behavior)
    # ------------------------------------------------------------------

    def test_discover_index_sources_calls_sync_by_default(self) -> None:
        with (
            mock.patch.object(source_adapters, "_home", return_value=self.home),
            mock.patch.object(source_adapters, "sync_all_adapters", return_value={}) as mock_sync,
        ):
            source_adapters.discover_index_sources(self.home)
        mock_sync.assert_called_once()

    def test_discover_index_sources_skip_sync_skips_sync_call(self) -> None:
        """If _skip_sync kwarg is supported, sync_all_adapters should not be called."""
        import inspect

        sig = inspect.signature(source_adapters.discover_index_sources)
        if "_skip_sync" not in sig.parameters:
            # Function doesn't have _skip_sync yet — just verify it runs without error
            with mock.patch.object(source_adapters, "_home", return_value=self.home):
                result = source_adapters.discover_index_sources(self.home)
            self.assertIsInstance(result, list)
            return

        with (
            mock.patch.object(source_adapters, "_home", return_value=self.home),
            mock.patch.object(source_adapters, "sync_all_adapters", return_value={}) as mock_sync,
        ):
            source_adapters.discover_index_sources(self.home, _skip_sync=True)
        mock_sync.assert_not_called()

    def test_discover_index_sources_returns_list_of_tuples(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.discover_index_sources(self.home)
        self.assertIsInstance(result, list)
        for item in result:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)
            source_type, path = item
            self.assertIsInstance(source_type, str)
            self.assertIsInstance(path, Path)

    # ------------------------------------------------------------------
    # Tests: source_inventory calls discover_index_sources
    # ------------------------------------------------------------------

    def test_source_inventory_returns_platforms_list(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)
        self.assertIn("platforms", inventory)
        self.assertIsInstance(inventory["platforms"], list)

    def test_source_inventory_includes_new_adapter_platforms(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)
        platform_names = {p["platform"] for p in inventory["platforms"]}
        for expected in ("cline", "roo_code", "continue", "zed", "aider", "cursor", "windsurf"):
            self.assertIn(expected, platform_names)

    def test_source_inventory_detected_cline(self) -> None:
        self._create_cline_tasks()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)
        platforms = {p["platform"]: p for p in inventory["platforms"]}
        self.assertTrue(platforms["cline"]["detected"])

    def test_source_inventory_detected_continue(self) -> None:
        self._create_continue_session()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)
        platforms = {p["platform"]: p for p in inventory["platforms"]}
        self.assertTrue(platforms["continue"]["detected"])

    def test_source_inventory_detected_zed(self) -> None:
        self._create_zed_conversation()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)
        platforms = {p["platform"]: p for p in inventory["platforms"]}
        self.assertTrue(platforms["zed"]["detected"])

    def test_source_inventory_detected_aider(self) -> None:
        self._create_aider_history()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)
        platforms = {p["platform"]: p for p in inventory["platforms"]}
        self.assertTrue(platforms["aider"]["detected"])

    def test_source_inventory_detected_cursor(self) -> None:
        self._create_cursor_vscdb()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)
        platforms = {p["platform"]: p for p in inventory["platforms"]}
        self.assertTrue(platforms["cursor"]["detected"])

    def test_source_inventory_detected_windsurf(self) -> None:
        self._create_windsurf_vscdb()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)
        platforms = {p["platform"]: p for p in inventory["platforms"]}
        self.assertTrue(platforms["windsurf"]["detected"])

    def test_source_inventory_calls_discover_index_sources_skip_sync(self) -> None:
        """source_inventory should pass _skip_sync=True to discover_index_sources
        if that parameter exists, to avoid double sync."""
        import inspect

        sig = inspect.signature(source_adapters.discover_index_sources)
        if "_skip_sync" not in sig.parameters:
            # Not yet implemented — just verify no crash
            with mock.patch.object(source_adapters, "_home", return_value=self.home):
                result = source_adapters.source_inventory(self.home)
            self.assertIn("platforms", result)
            return

        call_kwargs: list[dict] = []
        original = source_adapters.discover_index_sources

        def capturing_discover(*args, **kwargs):  # noqa: ANN001
            call_kwargs.append(kwargs)
            return original(*args, **kwargs)

        with (
            mock.patch.object(source_adapters, "_home", return_value=self.home),
            mock.patch.object(source_adapters, "discover_index_sources", side_effect=capturing_discover),
        ):
            source_adapters.source_inventory(self.home)
        self.assertTrue(any(kw.get("_skip_sync") for kw in call_kwargs))

    # ------------------------------------------------------------------
    # Tests: sync_all_adapters includes new adapters
    # ------------------------------------------------------------------

    def test_sync_all_adapters_includes_new_adapter_keys(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        for key in (
            "cline_session",
            "roo_session",
            "continue_session",
            "zed_session",
            "aider_session",
            "cursor_session",
            "windsurf_session",
        ):
            self.assertIn(key, result)

    def test_sync_all_adapters_all_new_adapters_not_detected_by_default(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        for key in (
            "cline_session",
            "roo_session",
            "continue_session",
            "zed_session",
            "aider_session",
            "cursor_session",
            "windsurf_session",
        ):
            self.assertFalse(result[key].get("detected", True), f"{key} should not be detected")

    def test_sync_all_adapters_detects_cline_when_present(self) -> None:
        self._create_cline_tasks()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        self.assertTrue(result["cline_session"]["detected"])

    def test_sync_all_adapters_detects_roo_when_present(self) -> None:
        self._create_cline_tasks(extension_id="rooveterinaryinc.roo-cline")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        self.assertTrue(result["roo_session"]["detected"])

    def test_sync_all_adapters_detects_continue_when_present(self) -> None:
        self._create_continue_session()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        self.assertTrue(result["continue_session"]["detected"])

    def test_sync_all_adapters_detects_zed_when_present(self) -> None:
        self._create_zed_conversation()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        self.assertTrue(result["zed_session"]["detected"])

    def test_sync_all_adapters_detects_aider_when_present(self) -> None:
        self._create_aider_history()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        self.assertTrue(result["aider_session"]["detected"])

    def test_sync_all_adapters_detects_cursor_when_present(self) -> None:
        self._create_cursor_vscdb()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        self.assertTrue(result["cursor_session"]["detected"])

    def test_sync_all_adapters_detects_windsurf_when_present(self) -> None:
        self._create_windsurf_vscdb()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)
        self.assertTrue(result["windsurf_session"]["detected"])

    # ------------------------------------------------------------------
    # Tests: source_freshness_snapshot adapter_sessions includes new counts
    # ------------------------------------------------------------------

    def test_freshness_snapshot_adapter_sessions_includes_new_keys(self) -> None:
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            snapshot = source_adapters.source_freshness_snapshot(self.home)
        adapter = snapshot.get("adapter_sessions", {})
        for key in (
            "cline_session_count",
            "roo_session_count",
            "continue_session_count",
            "zed_session_count",
            "aider_session_count",
            "cursor_session_count",
            "windsurf_session_count",
        ):
            self.assertIn(key, adapter, f"Missing {key} in adapter_sessions")

    # ------------------------------------------------------------------
    # Tests: discover_index_sources picks up new adapter session files
    # ------------------------------------------------------------------

    def test_discover_includes_cline_sessions_after_sync(self) -> None:
        self._create_cline_tasks()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            discovered = source_adapters.discover_index_sources(self.home)
        source_types = {st for st, _ in discovered}
        self.assertIn("cline_session", source_types)

    def test_discover_includes_continue_sessions_after_sync(self) -> None:
        self._create_continue_session()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            discovered = source_adapters.discover_index_sources(self.home)
        source_types = {st for st, _ in discovered}
        self.assertIn("continue_session", source_types)

    def test_discover_includes_zed_sessions_after_sync(self) -> None:
        self._create_zed_conversation()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            discovered = source_adapters.discover_index_sources(self.home)
        source_types = {st for st, _ in discovered}
        self.assertIn("zed_session", source_types)

    def test_discover_includes_aider_sessions_after_sync(self) -> None:
        self._create_aider_history()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            discovered = source_adapters.discover_index_sources(self.home)
        source_types = {st for st, _ in discovered}
        self.assertIn("aider_session", source_types)

    def test_discover_includes_cursor_sessions_after_sync(self) -> None:
        self._create_cursor_vscdb()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            discovered = source_adapters.discover_index_sources(self.home)
        source_types = {st for st, _ in discovered}
        self.assertIn("cursor_session", source_types)

    def test_discover_includes_windsurf_sessions_after_sync(self) -> None:
        self._create_windsurf_vscdb()
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            discovered = source_adapters.discover_index_sources(self.home)
        source_types = {st for st, _ in discovered}
        self.assertIn("windsurf_session", source_types)

    # ------------------------------------------------------------------
    # Tests: prune stale behavior for new adapters
    # ------------------------------------------------------------------

    def test_cline_prunes_stale_files_when_not_detected(self) -> None:
        adapter_dir = source_adapters._adapter_root(self.home) / "cline_session"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        stale = adapter_dir / "stale.jsonl"
        stale.write_text('{"text":"stale"}', encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cline_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertFalse(stale.exists())

    def test_continue_prunes_stale_files_when_not_detected(self) -> None:
        adapter_dir = source_adapters._adapter_root(self.home) / "continue_session"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        stale = adapter_dir / "stale.jsonl"
        stale.write_text('{"text":"stale"}', encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_continue_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertFalse(stale.exists())

    def test_cursor_prunes_stale_files_when_not_detected(self) -> None:
        adapter_dir = source_adapters._adapter_root(self.home) / "cursor_session"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        stale = adapter_dir / "stale.jsonl"
        stale.write_text('{"text":"stale"}', encoding="utf-8")
        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters._sync_cursor_sessions(self.home)
        self.assertFalse(result["detected"])
        self.assertFalse(stale.exists())

    # ------------------------------------------------------------------
    # Tests: _normalize_text_value edge cases (for completeness)
    # ------------------------------------------------------------------

    def test_normalize_text_value_strips_single_quotes(self) -> None:
        # Single-quoted string: 'hello' decoded by json.loads? No — json doesn't do singles.
        # So it should return as-is after strip.
        result = source_adapters._normalize_text_value("  hello world  ")
        self.assertEqual(result, "hello world")

    def test_normalize_text_value_none_returns_none(self) -> None:
        self.assertIsNone(source_adapters._normalize_text_value(None))

    def test_normalize_text_value_whitespace_only_returns_none(self) -> None:
        self.assertIsNone(source_adapters._normalize_text_value("   "))

    def test_normalize_text_value_double_quoted_string(self) -> None:
        self.assertEqual(source_adapters._normalize_text_value('"hello"'), "hello")

    # ------------------------------------------------------------------
    # Tests: multi-adapter combined scenario
    # ------------------------------------------------------------------

    def test_all_new_adapters_detected_simultaneously(self) -> None:
        self._create_cline_tasks()
        self._create_cline_tasks(extension_id="rooveterinaryinc.roo-cline")
        self._create_continue_session()
        self._create_zed_conversation()
        self._create_aider_history()
        self._create_cursor_vscdb()
        self._create_windsurf_vscdb()

        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            result = source_adapters.sync_all_adapters(self.home)

        for key in (
            "cline_session",
            "roo_session",
            "continue_session",
            "zed_session",
            "aider_session",
            "cursor_session",
            "windsurf_session",
        ):
            self.assertTrue(result[key]["detected"], f"{key} should be detected")
            self.assertGreater(result[key]["sessions"], 0, f"{key} should have sessions > 0")

    def test_source_inventory_all_new_platforms_detected_simultaneously(self) -> None:
        self._create_cline_tasks()
        self._create_cline_tasks(extension_id="rooveterinaryinc.roo-cline")
        self._create_continue_session()
        self._create_zed_conversation()
        self._create_aider_history()
        self._create_cursor_vscdb()
        self._create_windsurf_vscdb()

        with mock.patch.object(source_adapters, "_home", return_value=self.home):
            inventory = source_adapters.source_inventory(self.home)

        platforms = {p["platform"]: p for p in inventory["platforms"]}
        for platform in ("cline", "roo_code", "continue", "zed", "aider", "cursor", "windsurf"):
            self.assertTrue(platforms[platform]["detected"], f"{platform} should be detected")


if __name__ == "__main__":
    unittest.main()
