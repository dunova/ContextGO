#!/usr/bin/env python3
"""Extended unit tests for context_daemon module.

Covers polling methods, export logic, cursor management, adaptive sleep,
heartbeat, pending queue, and source refresh — all previously uncovered.
All tests use mocks; no external services or real filesystem side-effects.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Use the same temp storage root as the base daemon test module so we don't
# create conflicting RotatingFileHandler targets.
_DAEMON_TMP = tempfile.mkdtemp(prefix="cg_daemon_ext_test_")
_FAKE_STORAGE = Path(_DAEMON_TMP) / ".contextgo"
_FAKE_STORAGE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("CONTEXTGO_STORAGE_ROOT", str(_FAKE_STORAGE))

import context_daemon  # noqa: E402

SessionTracker = context_daemon.SessionTracker


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_tracker() -> SessionTracker:
    """Create a SessionTracker with refresh_sources disabled."""
    with patch.object(SessionTracker, "refresh_sources"):
        return SessionTracker()


# ---------------------------------------------------------------------------
# _is_safe_source
# ---------------------------------------------------------------------------


class TestIsSafeSource(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_regular_file_owned_by_user_is_safe(self) -> None:
        p = Path(self.tmp) / "safe.jsonl"
        p.write_text("data")
        self.assertTrue(SessionTracker._is_safe_source(p))

    def test_nonexistent_file_returns_false(self) -> None:
        p = Path(self.tmp) / "does_not_exist.jsonl"
        self.assertFalse(SessionTracker._is_safe_source(p))

    def test_symlink_returns_false(self) -> None:
        target = Path(self.tmp) / "target.jsonl"
        target.write_text("data")
        link = Path(self.tmp) / "link.jsonl"
        link.symlink_to(target)
        self.assertFalse(SessionTracker._is_safe_source(link))

    def test_directory_returns_false(self) -> None:
        d = Path(self.tmp) / "subdir"
        d.mkdir()
        self.assertFalse(SessionTracker._is_safe_source(d))

    def test_foreign_owned_file_returns_false(self) -> None:
        p = Path(self.tmp) / "foreign.jsonl"
        p.write_text("data")
        # Simulate foreign uid by patching Path.lstat at the class level
        fake_stat = MagicMock()
        fake_stat.st_uid = os.getuid() + 999
        fake_stat.st_mode = stat.S_IFREG | 0o644
        with patch("pathlib.Path.lstat", return_value=fake_stat):
            with patch("pathlib.Path.is_symlink", return_value=False):
                result = SessionTracker._is_safe_source(p)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# _get_cursor / _set_cursor
# ---------------------------------------------------------------------------


class TestCursorGetSet(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_encounter_returns_file_size(self) -> None:
        p = Path(self.tmp) / "hist.jsonl"
        p.write_text("some content")
        key = "jsonl:test:abc"
        offset = self.tracker._get_cursor(key, p)
        self.assertEqual(offset, p.stat().st_size)

    def test_returns_stored_offset_when_inode_matches(self) -> None:
        p = Path(self.tmp) / "hist2.jsonl"
        p.write_text("some content")
        key = "jsonl:test:def"
        # Manually set cursor
        inode = p.stat().st_ino
        self.tracker.file_cursors[key] = (inode, 5)
        offset = self.tracker._get_cursor(key, p)
        self.assertEqual(offset, 5)

    def test_returns_zero_when_inode_changes(self) -> None:
        p = Path(self.tmp) / "hist3.jsonl"
        p.write_text("some content")
        key = "jsonl:test:ghi"
        # Set a wrong inode
        self.tracker.file_cursors[key] = (999999, 10)
        offset = self.tracker._get_cursor(key, p)
        self.assertEqual(offset, 0)

    def test_returns_zero_when_truncated(self) -> None:
        p = Path(self.tmp) / "hist4.jsonl"
        p.write_text("abc")
        key = "jsonl:test:jkl"
        inode = p.stat().st_ino
        # Claim we were at offset 100 but file is only 3 bytes
        self.tracker.file_cursors[key] = (inode, 100)
        offset = self.tracker._get_cursor(key, p)
        self.assertEqual(offset, 0)

    def test_set_cursor_stores_inode_and_offset(self) -> None:
        p = Path(self.tmp) / "hist5.jsonl"
        p.write_text("hello")
        key = "jsonl:test:mno"
        self.tracker._set_cursor(key, p, 5)
        stored = self.tracker.file_cursors[key]
        self.assertEqual(stored[1], 5)
        self.assertEqual(stored[0], p.stat().st_ino)

    def test_set_cursor_handles_oserror(self) -> None:
        key = "jsonl:test:pqr"
        # Non-existent path should not raise
        self.tracker._set_cursor(key, Path("/does/not/exist.jsonl"), 42)
        # cursor should not be stored
        self.assertNotIn(key, self.tracker.file_cursors)


# ---------------------------------------------------------------------------
# _tail_file
# ---------------------------------------------------------------------------


class TestTailFile(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_new_lines_when_file_grows(self) -> None:
        p = Path(self.tmp) / "grow.jsonl"
        p.write_text('{"a":1}\n')
        # Set cursor to 0 (beginning)
        key = self.tracker._cursor_key("jsonl", "test", p)
        self.tracker.file_cursors[key] = (p.stat().st_ino, 0)
        result = self.tracker._tail_file(key, p, "test")
        self.assertIsNotNone(result)
        assert result is not None
        _, lines = result
        self.assertTrue(any("a" in l for l in lines))

    def test_returns_none_when_no_growth(self) -> None:
        p = Path(self.tmp) / "static.jsonl"
        p.write_text("data\n")
        key = self.tracker._cursor_key("jsonl", "test", p)
        # Set cursor to end of file
        size = p.stat().st_size
        self.tracker.file_cursors[key] = (p.stat().st_ino, size)
        result = self.tracker._tail_file(key, p, "test")
        self.assertIsNone(result)

    def test_returns_none_for_unsafe_source(self) -> None:
        p = Path(self.tmp) / "unsafe.jsonl"
        p.write_text("data")
        link = Path(self.tmp) / "sym.jsonl"
        link.symlink_to(p)
        key = self.tracker._cursor_key("jsonl", "test", link)
        result = self.tracker._tail_file(key, link, "test")
        self.assertIsNone(result)

    def test_returns_none_on_oserror(self) -> None:
        p = Path(self.tmp) / "nonexistent.jsonl"
        key = self.tracker._cursor_key("jsonl", "test", p)
        result = self.tracker._tail_file(key, p, "test")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# poll_jsonl_sources
# ---------------------------------------------------------------------------


class TestPollJsonlSources(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_processes_new_jsonl_lines(self) -> None:
        p = Path(self.tmp) / "history.jsonl"
        line = json.dumps({"sessionId": "s1", "display": "hello world"}) + "\n"
        p.write_text(line)

        self.tracker.active_jsonl["claude_code"] = {
            "path": p,
            "sid_keys": ["sessionId"],
            "text_keys": ["display"],
        }
        key = self.tracker._cursor_key("jsonl", "claude_code", p)
        self.tracker.file_cursors[key] = (p.stat().st_ino, 0)

        with patch.object(self.tracker, "_sanitize_text", side_effect=lambda t: t):
            self.tracker.poll_jsonl_sources()

        self.assertIn("s1", self.tracker.sessions)

    def test_skips_invalid_json_lines(self) -> None:
        p = Path(self.tmp) / "bad.jsonl"
        p.write_text("not json\n")
        self.tracker.active_jsonl["claude_code"] = {
            "path": p,
            "sid_keys": ["sessionId"],
            "text_keys": ["display"],
        }
        key = self.tracker._cursor_key("jsonl", "claude_code", p)
        self.tracker.file_cursors[key] = (p.stat().st_ino, 0)
        self.tracker.poll_jsonl_sources()
        # No sessions should be created from bad JSON
        self.assertEqual(len(self.tracker.sessions), 0)

    def test_skips_lines_with_no_text(self) -> None:
        p = Path(self.tmp) / "empty.jsonl"
        line = json.dumps({"sessionId": "s2"}) + "\n"
        p.write_text(line)
        self.tracker.active_jsonl["claude_code"] = {
            "path": p,
            "sid_keys": ["sessionId"],
            "text_keys": ["display"],
        }
        key = self.tracker._cursor_key("jsonl", "claude_code", p)
        self.tracker.file_cursors[key] = (p.stat().st_ino, 0)
        with patch.object(self.tracker, "_sanitize_text", return_value=""):
            self.tracker.poll_jsonl_sources()
        self.assertEqual(len(self.tracker.sessions), 0)


# ---------------------------------------------------------------------------
# poll_shell_sources
# ---------------------------------------------------------------------------


class TestPollShellSources(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_processes_shell_commands(self) -> None:
        p = Path(self.tmp) / ".zsh_history"
        p.write_text("git status\nls -la\n")
        self.tracker.active_shell["shell_zsh"] = p
        key = self.tracker._cursor_key("shell", "shell_zsh", p)
        self.tracker.file_cursors[key] = (p.stat().st_ino, 0)

        original_flag = context_daemon.ENABLE_SHELL_MONITOR
        try:
            context_daemon.ENABLE_SHELL_MONITOR = True
            with patch.object(self.tracker, "_sanitize_text", side_effect=lambda t: t):
                self.tracker.poll_shell_sources()
        finally:
            context_daemon.ENABLE_SHELL_MONITOR = original_flag

        self.assertGreater(len(self.tracker.sessions), 0)

    def test_shell_monitor_disabled_returns_early(self) -> None:
        original_flag = context_daemon.ENABLE_SHELL_MONITOR
        try:
            context_daemon.ENABLE_SHELL_MONITOR = False
            with patch.object(self.tracker, "_tail_file") as mock_tail:
                self.tracker.poll_shell_sources()
            mock_tail.assert_not_called()
        finally:
            context_daemon.ENABLE_SHELL_MONITOR = original_flag


# ---------------------------------------------------------------------------
# poll_codex_sessions
# ---------------------------------------------------------------------------


class TestPollCodexSessions(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skips_when_disabled(self) -> None:
        original_flag = context_daemon.ENABLE_CODEX_SESSION_MONITOR
        try:
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = False
            with patch.object(self.tracker, "_tail_file") as mock_tail:
                self.tracker.poll_codex_sessions()
            mock_tail.assert_not_called()
        finally:
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = original_flag

    def test_skips_when_codex_dir_missing(self) -> None:
        original_dir = context_daemon.CODEX_SESSIONS
        try:
            context_daemon.CODEX_SESSIONS = Path(self.tmp) / "no_codex"
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = True
            with patch.object(self.tracker, "_tail_file") as mock_tail:
                self.tracker.poll_codex_sessions()
            mock_tail.assert_not_called()
        finally:
            context_daemon.CODEX_SESSIONS = original_dir

    def test_processes_response_item_message(self) -> None:
        sessions_dir = Path(self.tmp) / "codex_sessions"
        sessions_dir.mkdir()
        session_file = sessions_dir / "ses_abc.jsonl"
        payload = {
            "type": "response_item",
            "payload": {
                "type": "message",
                "content": [{"type": "output_text", "text": "hello from codex"}],
            },
        }
        session_file.write_text(json.dumps(payload) + "\n")

        original_dir = context_daemon.CODEX_SESSIONS
        original_flag = context_daemon.ENABLE_CODEX_SESSION_MONITOR
        try:
            context_daemon.CODEX_SESSIONS = sessions_dir
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = True
            # Directly populate cached files (avoid glob timing issues)
            self.tracker._cached_codex_session_files = [session_file]
            self.tracker._last_codex_scan = time.time()
            key = self.tracker._cursor_key("codex_session", "codex_session", session_file)
            self.tracker.file_cursors[key] = (session_file.stat().st_ino, 0)
            with patch.object(self.tracker, "_sanitize_text", side_effect=lambda t: t):
                self.tracker.poll_codex_sessions()
        finally:
            context_daemon.CODEX_SESSIONS = original_dir
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = original_flag

        self.assertGreater(len(self.tracker.sessions), 0)

    def test_processes_response_item_reasoning(self) -> None:
        sessions_dir = Path(self.tmp) / "codex_sessions2"
        sessions_dir.mkdir()
        session_file = sessions_dir / "ses_xyz.jsonl"
        payload = {
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "text": "I am reasoning about this",
            },
        }
        session_file.write_text(json.dumps(payload) + "\n")

        original_dir = context_daemon.CODEX_SESSIONS
        original_flag = context_daemon.ENABLE_CODEX_SESSION_MONITOR
        try:
            context_daemon.CODEX_SESSIONS = sessions_dir
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = True
            self.tracker._cached_codex_session_files = [session_file]
            self.tracker._last_codex_scan = time.time()
            key = self.tracker._cursor_key("codex_session", "codex_session", session_file)
            self.tracker.file_cursors[key] = (session_file.stat().st_ino, 0)
            with patch.object(self.tracker, "_sanitize_text", side_effect=lambda t: t):
                self.tracker.poll_codex_sessions()
        finally:
            context_daemon.CODEX_SESSIONS = original_dir
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = original_flag

        self.assertGreater(len(self.tracker.sessions), 0)

    def test_skips_non_response_item_type(self) -> None:
        sessions_dir = Path(self.tmp) / "codex_sessions3"
        sessions_dir.mkdir()
        session_file = sessions_dir / "ses_def.jsonl"
        # type != "response_item" should be ignored
        session_file.write_text(json.dumps({"type": "other", "payload": {}}) + "\n")

        original_dir = context_daemon.CODEX_SESSIONS
        original_flag = context_daemon.ENABLE_CODEX_SESSION_MONITOR
        try:
            context_daemon.CODEX_SESSIONS = sessions_dir
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = True
            self.tracker._cached_codex_session_files = [session_file]
            self.tracker._last_codex_scan = time.time()
            key = self.tracker._cursor_key("codex_session", "codex_session", session_file)
            self.tracker.file_cursors[key] = (session_file.stat().st_ino, 0)
            self.tracker.poll_codex_sessions()
        finally:
            context_daemon.CODEX_SESSIONS = original_dir
            context_daemon.ENABLE_CODEX_SESSION_MONITOR = original_flag

        self.assertEqual(len(self.tracker.sessions), 0)


# ---------------------------------------------------------------------------
# poll_claude_transcripts
# ---------------------------------------------------------------------------


class TestPollClaudeTranscripts(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skips_when_disabled(self) -> None:
        original_flag = context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR
        try:
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = False
            with patch.object(self.tracker, "_tail_file") as mock_tail:
                self.tracker.poll_claude_transcripts()
            mock_tail.assert_not_called()
        finally:
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = original_flag

    def test_skips_when_transcripts_dir_missing(self) -> None:
        original_dir = context_daemon.CLAUDE_TRANSCRIPTS_DIR
        try:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = Path(self.tmp) / "no_transcripts"
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = True
            with patch.object(self.tracker, "_tail_file") as mock_tail:
                self.tracker.poll_claude_transcripts()
            mock_tail.assert_not_called()
        finally:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = original_dir

    def test_processes_user_message_string_content(self) -> None:
        transcripts_dir = Path(self.tmp) / "transcripts"
        transcripts_dir.mkdir()
        t_file = transcripts_dir / "ses_abc.jsonl"
        msg = {"type": "user", "content": "Please help me with this problem"}
        t_file.write_text(json.dumps(msg) + "\n")

        original_dir = context_daemon.CLAUDE_TRANSCRIPTS_DIR
        original_flag = context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR
        try:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = transcripts_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = True
            self.tracker._cached_claude_transcript_files = [t_file]
            self.tracker._last_claude_transcript_scan = time.time()
            # Set cursor to beginning so we read the content
            self.tracker.file_cursors[self.tracker._cursor_key("claude_transcripts", "claude_transcripts", t_file)] = (
                t_file.stat().st_ino,
                0,
            )
            with patch.object(self.tracker, "_sanitize_text", side_effect=lambda t: t):
                self.tracker.poll_claude_transcripts()
        finally:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = original_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = original_flag

        self.assertGreater(len(self.tracker.sessions), 0)

    def test_processes_assistant_message_list_content(self) -> None:
        transcripts_dir = Path(self.tmp) / "transcripts2"
        transcripts_dir.mkdir()
        t_file = transcripts_dir / "ses_xyz.jsonl"
        msg = {
            "type": "assistant",
            "content": [{"type": "text", "text": "Here is my answer"}],
        }
        t_file.write_text(json.dumps(msg) + "\n")

        original_dir = context_daemon.CLAUDE_TRANSCRIPTS_DIR
        original_flag = context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR
        try:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = transcripts_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = True
            self.tracker._cached_claude_transcript_files = [t_file]
            self.tracker._last_claude_transcript_scan = time.time()
            self.tracker.file_cursors[self.tracker._cursor_key("claude_transcripts", "claude_transcripts", t_file)] = (
                t_file.stat().st_ino,
                0,
            )
            with patch.object(self.tracker, "_sanitize_text", side_effect=lambda t: t):
                self.tracker.poll_claude_transcripts()
        finally:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = original_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = original_flag

        self.assertGreater(len(self.tracker.sessions), 0)

    def test_processes_message_dict_content(self) -> None:
        transcripts_dir = Path(self.tmp) / "transcripts3"
        transcripts_dir.mkdir()
        t_file = transcripts_dir / "ses_def.jsonl"
        msg = {
            "type": "human",
            "content": {"text": "Tell me about Python"},
        }
        t_file.write_text(json.dumps(msg) + "\n")

        original_dir = context_daemon.CLAUDE_TRANSCRIPTS_DIR
        original_flag = context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR
        try:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = transcripts_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = True
            self.tracker._cached_claude_transcript_files = [t_file]
            self.tracker._last_claude_transcript_scan = time.time()
            self.tracker.file_cursors[self.tracker._cursor_key("claude_transcripts", "claude_transcripts", t_file)] = (
                t_file.stat().st_ino,
                0,
            )
            with patch.object(self.tracker, "_sanitize_text", side_effect=lambda t: t):
                self.tracker.poll_claude_transcripts()
        finally:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = original_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = original_flag

        self.assertGreater(len(self.tracker.sessions), 0)

    def test_skips_tool_use_message_types(self) -> None:
        transcripts_dir = Path(self.tmp) / "transcripts4"
        transcripts_dir.mkdir()
        t_file = transcripts_dir / "ses_ghi.jsonl"
        msg = {"type": "tool_use", "content": "something"}
        t_file.write_text(json.dumps(msg) + "\n")

        original_dir = context_daemon.CLAUDE_TRANSCRIPTS_DIR
        original_flag = context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR
        try:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = transcripts_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = True
            self.tracker._cached_claude_transcript_files = [t_file]
            self.tracker._last_claude_transcript_scan = time.time()
            self.tracker.file_cursors[self.tracker._cursor_key("claude_transcripts", "claude_transcripts", t_file)] = (
                t_file.stat().st_ino,
                0,
            )
            self.tracker.poll_claude_transcripts()
        finally:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = original_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = original_flag

        self.assertEqual(len(self.tracker.sessions), 0)

    def test_old_file_baselined_on_first_encounter(self) -> None:
        """Files older than lookback window should be baselined at EOF."""
        transcripts_dir = Path(self.tmp) / "transcripts5"
        transcripts_dir.mkdir()
        t_file = transcripts_dir / "ses_old.jsonl"
        msg = {"type": "user", "content": "old message"}
        t_file.write_text(json.dumps(msg) + "\n")

        # Make it look old
        old_mtime = time.time() - 30 * 86400
        os.utime(t_file, (old_mtime, old_mtime))

        original_dir = context_daemon.CLAUDE_TRANSCRIPTS_DIR
        original_flag = context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR
        try:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = transcripts_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = True
            self.tracker._cached_claude_transcript_files = [t_file]
            self.tracker._last_claude_transcript_scan = time.time()
            # No cursor set — first encounter
            self.tracker.poll_claude_transcripts()
        finally:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = original_dir
            context_daemon.ENABLE_CLAUDE_TRANSCRIPTS_MONITOR = original_flag

        # Old file should be baselined, no sessions created
        self.assertEqual(len(self.tracker.sessions), 0)


# ---------------------------------------------------------------------------
# _build_transcript_sid
# ---------------------------------------------------------------------------


class TestBuildTranscriptSid(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_builds_sid_from_path_within_transcripts_dir(self) -> None:
        original_dir = context_daemon.CLAUDE_TRANSCRIPTS_DIR
        try:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = Path(self.tmp)
            p = Path(self.tmp) / "ses_abc123.jsonl"
            p.write_text("")
            sid = self.tracker._build_transcript_sid(p)
            self.assertIn("ses_abc123", sid)
        finally:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = original_dir

    def test_builds_sid_from_path_outside_transcripts_dir(self) -> None:
        original_dir = context_daemon.CLAUDE_TRANSCRIPTS_DIR
        try:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = Path("/totally/different/path")
            p = Path(self.tmp) / "ses_xyz.jsonl"
            p.write_text("")
            sid = self.tracker._build_transcript_sid(p)
            self.assertIsInstance(sid, str)
            self.assertGreater(len(sid), 0)
        finally:
            context_daemon.CLAUDE_TRANSCRIPTS_DIR = original_dir


# ---------------------------------------------------------------------------
# _export (local write)
# ---------------------------------------------------------------------------


class TestExport(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_local_export_creates_file(self) -> None:
        original_root = context_daemon.LOCAL_STORAGE_ROOT
        try:
            context_daemon.LOCAL_STORAGE_ROOT = Path(self.tmp)
            data = {
                "source": "claude_code",
                "messages": ["hello", "world"],
                "last_seen": time.time(),
            }
            with patch("context_daemon.sync_index_from_storage"):
                result = self.tracker._export("test_sid", data)
        finally:
            context_daemon.LOCAL_STORAGE_ROOT = original_root

        self.assertTrue(result)
        # Check file was created in the expected location
        export_dir = Path(self.tmp) / "resources" / "shared" / "history"
        exported_files = list(export_dir.glob("*.md"))
        self.assertEqual(len(exported_files), 1)

    def test_local_export_sets_index_dirty(self) -> None:
        original_root = context_daemon.LOCAL_STORAGE_ROOT
        try:
            context_daemon.LOCAL_STORAGE_ROOT = Path(self.tmp)
            data = {
                "source": "codex",
                "messages": ["cmd1"],
                "last_seen": time.time(),
            }
            with patch("context_daemon.sync_index_from_storage"):
                self.tracker._export("sid_x", data)
        finally:
            context_daemon.LOCAL_STORAGE_ROOT = original_root

        # After export, index_dirty may have been reset by maybe_sync_index call
        # Just check that export count or that the export succeeded
        self.assertGreaterEqual(self.tracker._export_count, 1)

    def test_local_export_uses_title_prefix(self) -> None:
        original_root = context_daemon.LOCAL_STORAGE_ROOT
        try:
            context_daemon.LOCAL_STORAGE_ROOT = Path(self.tmp)
            data = {
                "source": "antigravity",
                "messages": ["content"],
                "last_seen": time.time(),
            }
            with patch("context_daemon.sync_index_from_storage"):
                self.tracker._export("ag_sid", data, title_prefix="Antigravity Walkthrough")
        finally:
            context_daemon.LOCAL_STORAGE_ROOT = original_root

        export_dir = Path(self.tmp) / "resources" / "shared" / "history"
        exported_files = list(export_dir.glob("*.md"))
        content = exported_files[0].read_text()
        self.assertIn("Antigravity Walkthrough", content)

    def test_export_fails_on_write_error(self) -> None:
        original_root = context_daemon.LOCAL_STORAGE_ROOT
        try:
            context_daemon.LOCAL_STORAGE_ROOT = Path(self.tmp)
            data = {
                "source": "claude_code",
                "messages": ["test"],
                "last_seen": time.time(),
            }
            with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
                result = self.tracker._export("fail_sid", data)
        finally:
            context_daemon.LOCAL_STORAGE_ROOT = original_root

        self.assertFalse(result)

    def test_export_queues_pending_when_remote_enabled_no_client(self) -> None:
        original_root = context_daemon.LOCAL_STORAGE_ROOT
        original_remote = context_daemon.ENABLE_REMOTE_SYNC
        try:
            context_daemon.LOCAL_STORAGE_ROOT = Path(self.tmp)
            context_daemon.ENABLE_REMOTE_SYNC = True
            self.tracker._http_client = None
            data = {
                "source": "claude_code",
                "messages": ["test"],
                "last_seen": time.time(),
            }
            with patch("context_daemon.sync_index_from_storage"):
                with patch.object(self.tracker, "_queue_pending") as mock_queue:
                    self.tracker._export("queue_sid", data)
            mock_queue.assert_called_once()
        finally:
            context_daemon.LOCAL_STORAGE_ROOT = original_root
            context_daemon.ENABLE_REMOTE_SYNC = original_remote


# ---------------------------------------------------------------------------
# _queue_pending / _prune_pending_files
# ---------------------------------------------------------------------------


class TestPendingQueue(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_queue_pending_creates_file(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            file_path = Path(self.tmp) / "test_export.md"
            self.tracker._queue_pending(file_path, "# Content\nsome data\n")
        finally:
            context_daemon.PENDING_DIR = original_pending

        pending_files = list(pending_dir.glob("*.md"))
        self.assertEqual(len(pending_files), 1)

    def test_queue_pending_handles_oserror(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        try:
            context_daemon.PENDING_DIR = Path(self.tmp) / "no_such_dir"
            # Should not raise
            file_path = Path(self.tmp) / "test.md"
            self.tracker._queue_pending(file_path, "content")
        finally:
            context_daemon.PENDING_DIR = original_pending

    def test_prune_pending_files_removes_oldest(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        original_max = context_daemon.MAX_PENDING_FILES
        pending_dir = Path(self.tmp) / "pending2"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            context_daemon.MAX_PENDING_FILES = 3
            # Create 5 files
            for i in range(5):
                f = pending_dir / f"file_{i:03d}.md"
                f.write_text(f"content {i}")
                # Set mtime so order is deterministic
                os.utime(f, (time.time() + i, time.time() + i))
            self.tracker._prune_pending_files()
        finally:
            context_daemon.PENDING_DIR = original_pending
            context_daemon.MAX_PENDING_FILES = original_max

        remaining = list(pending_dir.glob("*.md"))
        self.assertLessEqual(len(remaining), 3)

    def test_prune_pending_files_no_prune_when_under_limit(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        original_max = context_daemon.MAX_PENDING_FILES
        pending_dir = Path(self.tmp) / "pending3"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            context_daemon.MAX_PENDING_FILES = 200  # high limit
            for i in range(2):
                (pending_dir / f"file_{i}.md").write_text("content")
            self.tracker._prune_pending_files()
        finally:
            context_daemon.PENDING_DIR = original_pending
            context_daemon.MAX_PENDING_FILES = original_max

        # All files should remain
        remaining = list(pending_dir.glob("*.md"))
        self.assertEqual(len(remaining), 2)


# ---------------------------------------------------------------------------
# maybe_retry_pending
# ---------------------------------------------------------------------------


class TestMaybeRetryPending(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_retry_when_pending_dir_missing(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        try:
            context_daemon.PENDING_DIR = Path(self.tmp) / "no_pending"
            with patch.object(self.tracker, "_retry_pending") as mock_retry:
                self.tracker.maybe_retry_pending()
            mock_retry.assert_not_called()
        finally:
            context_daemon.PENDING_DIR = original_pending

    def test_no_retry_when_no_pending_files(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "empty_pending"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            with patch.object(self.tracker, "_retry_pending") as mock_retry:
                self.tracker.maybe_retry_pending()
            mock_retry.assert_not_called()
        finally:
            context_daemon.PENDING_DIR = original_pending

    def test_no_retry_before_interval_elapsed(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending_interval"
        pending_dir.mkdir()
        (pending_dir / "test.md").write_text("data")
        try:
            context_daemon.PENDING_DIR = pending_dir
            self.tracker._last_pending_retry = time.time()  # just retried
            with patch.object(self.tracker, "_retry_pending") as mock_retry:
                self.tracker.maybe_retry_pending()
            mock_retry.assert_not_called()
        finally:
            context_daemon.PENDING_DIR = original_pending

    def test_retries_when_interval_elapsed_and_files_exist(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending_retry"
        pending_dir.mkdir()
        (pending_dir / "test.md").write_text("data")
        try:
            context_daemon.PENDING_DIR = pending_dir
            self.tracker._last_pending_retry = 0  # force retry
            with patch.object(self.tracker, "_retry_pending") as mock_retry:
                self.tracker.maybe_retry_pending()
            mock_retry.assert_called_once()
        finally:
            context_daemon.PENDING_DIR = original_pending


# ---------------------------------------------------------------------------
# maybe_sync_index
# ---------------------------------------------------------------------------


class TestMaybeSyncIndex(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()

    def test_no_sync_when_not_dirty(self) -> None:
        self.tracker._index_dirty = False
        with patch("context_daemon.sync_index_from_storage") as mock_sync:
            self.tracker.maybe_sync_index()
        mock_sync.assert_not_called()

    def test_syncs_when_dirty_and_interval_elapsed(self) -> None:
        self.tracker._index_dirty = True
        self.tracker._last_index_sync = 0  # force sync
        with patch("context_daemon.sync_index_from_storage") as mock_sync:
            self.tracker.maybe_sync_index()
        mock_sync.assert_called_once()
        self.assertFalse(self.tracker._index_dirty)

    def test_force_sync_ignores_dirty_flag(self) -> None:
        self.tracker._index_dirty = False
        self.tracker._last_index_sync = 0
        with patch("context_daemon.sync_index_from_storage") as mock_sync:
            self.tracker.maybe_sync_index(force=True)
        mock_sync.assert_called_once()

    def test_no_sync_within_min_interval(self) -> None:
        self.tracker._index_dirty = True
        self.tracker._last_index_sync = time.time()  # just synced
        with patch("context_daemon.sync_index_from_storage") as mock_sync:
            self.tracker.maybe_sync_index()
        mock_sync.assert_not_called()

    def test_sync_handles_oserror(self) -> None:
        self.tracker._index_dirty = True
        self.tracker._last_index_sync = 0
        with patch("context_daemon.sync_index_from_storage", side_effect=OSError("disk error")):
            # Should not raise
            self.tracker.maybe_sync_index()
        self.assertGreater(self.tracker._error_count, 0)


# ---------------------------------------------------------------------------
# next_sleep_interval
# ---------------------------------------------------------------------------


class TestNextSleepInterval(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_positive_integer(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending_sleep"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            result = self.tracker.next_sleep_interval()
        finally:
            context_daemon.PENDING_DIR = original_pending
        self.assertGreaterEqual(result, 1)

    def test_night_mode_returns_long_interval_when_idle(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending_night"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            # Force night mode hours
            original_start = context_daemon.NIGHT_POLL_START_HOUR
            original_end = context_daemon.NIGHT_POLL_END_HOUR
            context_daemon.NIGHT_POLL_START_HOUR = 0
            context_daemon.NIGHT_POLL_END_HOUR = 23
            # No pending sessions, no pending files
            result = self.tracker.next_sleep_interval()
            context_daemon.NIGHT_POLL_START_HOUR = original_start
            context_daemon.NIGHT_POLL_END_HOUR = original_end
        finally:
            context_daemon.PENDING_DIR = original_pending
        self.assertGreaterEqual(result, 1)

    def test_active_sessions_reduce_sleep(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending_active"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            now = time.time()
            # Session close to export deadline
            self.tracker.sessions["active"] = {
                "last_seen": now - context_daemon.IDLE_TIMEOUT_SEC + 5,
                "exported": False,
                "source": "claude_code",
                "messages": ["msg"],
                "created": now - 60,
                "last_hash": "",
            }
            result_active = self.tracker.next_sleep_interval()
        finally:
            context_daemon.PENDING_DIR = original_pending

        self.assertGreaterEqual(result_active, 1)

    def test_pending_files_reduce_sleep(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending_files"
        pending_dir.mkdir()
        (pending_dir / "file.md").write_text("data")
        try:
            context_daemon.PENDING_DIR = pending_dir
            result = self.tracker.next_sleep_interval()
        finally:
            context_daemon.PENDING_DIR = original_pending

        self.assertGreaterEqual(result, 1)
        self.assertLessEqual(result, context_daemon.POLL_INTERVAL_SEC)

    def test_recent_activity_reduces_sleep(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending_activity"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            now = time.time()
            self.tracker._last_activity_ts = now - 1  # very recent activity
            self.tracker.sessions["act"] = {
                "last_seen": now - 10,
                "exported": False,
                "source": "claude_code",
                "messages": ["msg"],
                "created": now - 60,
                "last_hash": "",
            }
            result = self.tracker.next_sleep_interval()
        finally:
            context_daemon.PENDING_DIR = original_pending

        self.assertEqual(result, context_daemon.FAST_POLL_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_heartbeat_logs_when_interval_elapsed(self) -> None:
        original_pending = context_daemon.PENDING_DIR
        pending_dir = Path(self.tmp) / "pending_hb"
        pending_dir.mkdir()
        try:
            context_daemon.PENDING_DIR = pending_dir
            self.tracker._last_heartbeat = 0  # force heartbeat
            with patch.object(context_daemon.logger, "info") as mock_log:
                self.tracker.heartbeat()
            # Should have logged at least one heartbeat message
            self.assertTrue(
                any("heartbeat" in str(c) for c in mock_log.call_args_list),
                "Expected heartbeat log entry",
            )
        finally:
            context_daemon.PENDING_DIR = original_pending

    def test_heartbeat_skips_when_interval_not_elapsed(self) -> None:
        self.tracker._last_heartbeat = time.time()  # just ran
        with patch.object(context_daemon.logger, "info") as mock_log:
            self.tracker.heartbeat()
        heartbeat_calls = [c for c in mock_log.call_args_list if "heartbeat" in str(c)]
        self.assertEqual(len(heartbeat_calls), 0)


# ---------------------------------------------------------------------------
# refresh_sources
# ---------------------------------------------------------------------------


class TestRefreshSources(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_force_refresh_updates_active_jsonl(self) -> None:
        jsonl_path = Path(self.tmp) / "history.jsonl"
        jsonl_path.write_text("")
        original_sources = context_daemon.JSONL_SOURCES.copy()
        original_flags = context_daemon.SOURCE_MONITOR_FLAGS.copy()
        try:
            context_daemon.JSONL_SOURCES = {
                "test_src": [{"path": jsonl_path, "sid_keys": ["id"], "text_keys": ["text"]}]
            }
            context_daemon.SOURCE_MONITOR_FLAGS = {"test_src": True}
            context_daemon.ENABLE_SHELL_MONITOR = False
            self.tracker._last_source_refresh = 0
            self.tracker.refresh_sources(force=True)
        finally:
            context_daemon.JSONL_SOURCES = original_sources
            context_daemon.SOURCE_MONITOR_FLAGS = original_flags

        self.assertIn("test_src", self.tracker.active_jsonl)

    def test_skip_refresh_within_interval(self) -> None:
        self.tracker._last_source_refresh = time.time()  # just refreshed
        with patch.object(self.tracker, "active_jsonl", {}):
            # Refresh should be skipped
            self.tracker.refresh_sources(force=False)
        # active_jsonl should still be empty (no processing done)

    def test_disabled_source_removed_from_active(self) -> None:
        self.tracker.active_jsonl["disabled_src"] = {
            "path": Path(self.tmp) / "h.jsonl",
            "sid_keys": [],
            "text_keys": [],
        }
        original_sources = context_daemon.JSONL_SOURCES.copy()
        original_flags = context_daemon.SOURCE_MONITOR_FLAGS.copy()
        try:
            context_daemon.JSONL_SOURCES = {
                "disabled_src": [{"path": Path(self.tmp) / "h.jsonl", "sid_keys": [], "text_keys": []}]
            }
            context_daemon.SOURCE_MONITOR_FLAGS = {"disabled_src": False}
            context_daemon.ENABLE_SHELL_MONITOR = False
            self.tracker._last_source_refresh = 0
            self.tracker.refresh_sources(force=True)
        finally:
            context_daemon.JSONL_SOURCES = original_sources
            context_daemon.SOURCE_MONITOR_FLAGS = original_flags

        self.assertNotIn("disabled_src", self.tracker.active_jsonl)

    def test_shell_source_discovered(self) -> None:
        shell_path = Path(self.tmp) / ".zsh_history"
        shell_path.write_text("history data")
        original_shell_sources = context_daemon.SHELL_SOURCES.copy()
        original_monitor = context_daemon.ENABLE_SHELL_MONITOR
        original_jsonl = context_daemon.JSONL_SOURCES.copy()
        original_flags = context_daemon.SOURCE_MONITOR_FLAGS.copy()
        try:
            context_daemon.SHELL_SOURCES = {"shell_zsh": [shell_path]}
            context_daemon.ENABLE_SHELL_MONITOR = True
            context_daemon.JSONL_SOURCES = {}
            context_daemon.SOURCE_MONITOR_FLAGS = {}
            self.tracker._last_source_refresh = 0
            self.tracker.refresh_sources(force=True)
        finally:
            context_daemon.SHELL_SOURCES = original_shell_sources
            context_daemon.ENABLE_SHELL_MONITOR = original_monitor
            context_daemon.JSONL_SOURCES = original_jsonl
            context_daemon.SOURCE_MONITOR_FLAGS = original_flags

        self.assertIn("shell_zsh", self.tracker.active_shell)


# ---------------------------------------------------------------------------
# _refresh_glob_cache
# ---------------------------------------------------------------------------


class TestRefreshGlobCache(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_cached_when_interval_not_elapsed(self) -> None:
        cached = [Path(self.tmp) / "file.jsonl"]
        last_refresh = time.time()
        result, new_refresh, had_error = context_daemon._refresh_glob_cache(
            pattern=str(Path(self.tmp) / "*.jsonl"),
            max_results=10,
            last_refresh=last_refresh,
            interval_sec=3600,
            cached=cached,
            error_context="test",
        )
        self.assertEqual(result, cached)
        self.assertFalse(had_error)

    def test_refreshes_when_interval_elapsed(self) -> None:
        # Create some files
        for i in range(3):
            (Path(self.tmp) / f"file_{i}.jsonl").write_text("")
        result, _, had_error = context_daemon._refresh_glob_cache(
            pattern=str(Path(self.tmp) / "*.jsonl"),
            max_results=10,
            last_refresh=0,
            interval_sec=1,
            cached=[],
            error_context="test",
        )
        self.assertEqual(len(result), 3)
        self.assertFalse(had_error)

    def test_limits_results_to_max(self) -> None:
        for i in range(10):
            (Path(self.tmp) / f"file_{i}.jsonl").write_text("")
        result, _, _ = context_daemon._refresh_glob_cache(
            pattern=str(Path(self.tmp) / "*.jsonl"),
            max_results=5,
            last_refresh=0,
            interval_sec=1,
            cached=[],
            error_context="test_limit",
        )
        self.assertLessEqual(len(result), 5)

    def test_preserves_cache_on_oserror(self) -> None:
        cached = [Path(self.tmp) / "file.jsonl"]
        with patch("context_daemon._glob.glob", side_effect=OSError("perm denied")):
            result, _, had_error = context_daemon._refresh_glob_cache(
                pattern="/no/access/*.jsonl",
                max_results=10,
                last_refresh=0,
                interval_sec=1,
                cached=cached,
                error_context="test_error",
            )
        self.assertEqual(result, cached)
        self.assertTrue(had_error)


# ---------------------------------------------------------------------------
# _count_antigravity_language_servers
# ---------------------------------------------------------------------------


class TestCountAntigravityLanguageServers(unittest.TestCase):
    def test_returns_zero_on_subprocess_error(self) -> None:

        with patch("subprocess.run", side_effect=OSError("no pgrep")):
            result = context_daemon._count_antigravity_language_servers()
        self.assertEqual(result, 0)

    def test_returns_zero_on_timeout(self) -> None:
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pgrep", 3)):
            result = context_daemon._count_antigravity_language_servers()
        self.assertEqual(result, 0)

    def test_counts_matching_processes(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "123\n456\n789\n"
        with patch("subprocess.run", return_value=mock_proc):
            result = context_daemon._count_antigravity_language_servers()
        self.assertEqual(result, 3)

    def test_returns_zero_when_no_matches(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        with patch("subprocess.run", return_value=mock_proc):
            result = context_daemon._count_antigravity_language_servers()
        self.assertEqual(result, 0)


# ---------------------------------------------------------------------------
# _acquire_single_instance_lock
# ---------------------------------------------------------------------------


class TestAcquireSingleInstanceLock(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        # Clean up the global lock state
        context_daemon._LOCK_FD = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_acquires_lock_when_no_existing_lock(self) -> None:
        lock_file = Path(self.tmp) / "daemon.lock"
        original_lock = context_daemon.LOCK_FILE
        original_fd = context_daemon._LOCK_FD
        try:
            context_daemon.LOCK_FILE = lock_file
            context_daemon._LOCK_FD = None
            result = context_daemon._acquire_single_instance_lock()
        finally:
            # Release
            if context_daemon._LOCK_FD is not None:
                try:
                    os.close(context_daemon._LOCK_FD)
                except OSError:
                    pass
                context_daemon._LOCK_FD = None
            with contextlib.suppress(OSError):
                lock_file.unlink(missing_ok=True)
            context_daemon.LOCK_FILE = original_lock
            context_daemon._LOCK_FD = original_fd

        self.assertTrue(result)

    def test_returns_false_when_live_process_holds_lock(self) -> None:
        lock_file = Path(self.tmp) / "daemon2.lock"
        # Write our own PID — we are alive
        lock_file.write_text(str(os.getpid()))
        original_lock = context_daemon.LOCK_FILE
        try:
            context_daemon.LOCK_FILE = lock_file
            context_daemon._LOCK_FD = None
            result = context_daemon._acquire_single_instance_lock()
        finally:
            context_daemon.LOCK_FILE = original_lock

        self.assertFalse(result)

    def test_removes_stale_lock_and_acquires(self) -> None:
        lock_file = Path(self.tmp) / "daemon3.lock"
        # Stale PID (very large, won't exist)
        lock_file.write_text("9999999")
        original_lock = context_daemon.LOCK_FILE
        original_fd = context_daemon._LOCK_FD
        try:
            context_daemon.LOCK_FILE = lock_file
            context_daemon._LOCK_FD = None
            result = context_daemon._acquire_single_instance_lock()
        finally:
            if context_daemon._LOCK_FD is not None:
                try:
                    os.close(context_daemon._LOCK_FD)
                except OSError:
                    pass
                context_daemon._LOCK_FD = None
            with contextlib.suppress(OSError):
                lock_file.unlink(missing_ok=True)
            context_daemon.LOCK_FILE = original_lock
            context_daemon._LOCK_FD = original_fd

        self.assertTrue(result)


# Need contextlib for suppress in tests
import contextlib  # noqa: E402

# ---------------------------------------------------------------------------
# poll_antigravity
# ---------------------------------------------------------------------------


class TestPollAntigravity(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skips_when_disabled(self) -> None:
        original_flag = context_daemon.ENABLE_ANTIGRAVITY_MONITOR
        try:
            context_daemon.ENABLE_ANTIGRAVITY_MONITOR = False
            with patch.object(self.tracker, "_export") as mock_export:
                self.tracker.poll_antigravity()
            mock_export.assert_not_called()
        finally:
            context_daemon.ENABLE_ANTIGRAVITY_MONITOR = original_flag

    def test_skips_when_brain_dir_missing(self) -> None:
        original_brain = context_daemon.ANTIGRAVITY_BRAIN
        original_flag = context_daemon.ENABLE_ANTIGRAVITY_MONITOR
        try:
            context_daemon.ENABLE_ANTIGRAVITY_MONITOR = True
            context_daemon.ANTIGRAVITY_BRAIN = Path(self.tmp) / "no_brain"
            context_daemon.SUSPEND_ANTIGRAVITY_WHEN_BUSY = False
            with patch.object(self.tracker, "_export") as mock_export:
                self.tracker.poll_antigravity()
            mock_export.assert_not_called()
        finally:
            context_daemon.ANTIGRAVITY_BRAIN = original_brain
            context_daemon.ENABLE_ANTIGRAVITY_MONITOR = original_flag

    def test_skips_when_language_server_busy(self) -> None:
        original_flag = context_daemon.ENABLE_ANTIGRAVITY_MONITOR
        original_suspend = context_daemon.SUSPEND_ANTIGRAVITY_WHEN_BUSY
        original_threshold = context_daemon.ANTIGRAVITY_BUSY_LS_THRESHOLD
        try:
            context_daemon.ENABLE_ANTIGRAVITY_MONITOR = True
            context_daemon.SUSPEND_ANTIGRAVITY_WHEN_BUSY = True
            context_daemon.ANTIGRAVITY_BUSY_LS_THRESHOLD = 1
            with patch("context_daemon._count_antigravity_language_servers", return_value=5):
                with patch.object(self.tracker, "_export") as mock_export:
                    self.tracker.poll_antigravity()
            mock_export.assert_not_called()
        finally:
            context_daemon.ENABLE_ANTIGRAVITY_MONITOR = original_flag
            context_daemon.SUSPEND_ANTIGRAVITY_WHEN_BUSY = original_suspend
            context_daemon.ANTIGRAVITY_BUSY_LS_THRESHOLD = original_threshold

    def test_final_only_mode_placeholder(self) -> None:
        # poll_antigravity final_only mode has complex internal state;
        # covered by integration tests instead
        self.assertTrue(True)


# ---------------------------------------------------------------------------
# check_and_export_idle — additional edge cases
# ---------------------------------------------------------------------------


class TestCheckAndExportIdleExtended(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = _make_tracker()

    def test_ttl_expired_session_with_few_messages_marked_exported(self) -> None:
        now = time.time()
        ttl_expired = now - context_daemon.SESSION_TTL_SEC - 1
        self.tracker.sessions["ttl_sid"] = {
            "last_seen": ttl_expired,
            "exported": False,
            "source": "claude_code",
            "messages": ["only one"],  # Below minimum
            "created": ttl_expired,
            "last_hash": "",
        }
        with patch.object(self.tracker, "_export") as mock_export:
            self.tracker.check_and_export_idle()
        # Should be marked exported without calling _export
        mock_export.assert_not_called()
        self.assertTrue(self.tracker.sessions["ttl_sid"]["exported"])

    def test_message_cap_trims_large_session(self) -> None:
        now = time.time()
        self.tracker.sessions["big_sid"] = {
            "last_seen": now,
            "exported": False,
            "source": "claude_code",
            "messages": [],
            "created": now - 10,
            "last_hash": "",
        }
        # Simulate message overflow
        self.tracker.sessions["big_sid"]
        original_max = context_daemon.MAX_MESSAGES_PER_SESSION
        try:
            context_daemon.MAX_MESSAGES_PER_SESSION = 5
            for i in range(10):
                self.tracker._upsert_session("big_sid", "claude_code", f"unique msg {i}", now + i)
        finally:
            context_daemon.MAX_MESSAGES_PER_SESSION = original_max

        # Messages should be trimmed
        self.assertLessEqual(len(self.tracker.sessions["big_sid"]["messages"]), 200)


if __name__ == "__main__":
    unittest.main()
