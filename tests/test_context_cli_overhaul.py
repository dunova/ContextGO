from __future__ import annotations

import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from contextgo import context_cli


class OverhaulCliTests(unittest.TestCase):
    def _capture(self, fn, args):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn(args)
        return rc, out.getvalue(), err.getvalue()

    def test_sync_actions(self) -> None:
        with mock.patch.object(context_cli, "_get_context_sync") as mod:
            mod.return_value.init_sync.return_value = argparse.Namespace(
                repository="owner/repo", device_id="dev", store_key=True
            )
            mod.return_value.sync_status.return_value = {"configured": True}
            mod.return_value.pull_sync.return_value = {"inserted": 1}
            mod.return_value.push_sync.return_value = {"uploaded_shards": 1}
            mod.return_value.run_sync.return_value = {"completed_at": "now"}
            mod.return_value.disable_sync.return_value = {"disabled": True}
            cases = [
                argparse.Namespace(
                    sync_action="init",
                    repo="owner/repo",
                    branch="main",
                    password="p",
                    no_store_key=False,
                    device_id="dev",
                    no_auto=False,
                ),
                argparse.Namespace(sync_action="status", remote=False),
                argparse.Namespace(sync_action="pull", password=None, token="t"),
                argparse.Namespace(sync_action="push", password=None, token="t", limit=10),
                argparse.Namespace(sync_action="run", password=None, token="t", limit=10),
                argparse.Namespace(sync_action="disable"),
            ]
            for args in cases:
                if args.sync_action == "init":
                    mod.return_value.init_sync.return_value = mock.Mock(
                        repository="owner/repo", device_id="dev", store_key=True
                    )
                rc, out, err = self._capture(context_cli.cmd_sync, args)
                self.assertEqual(rc, 0, (args.sync_action, out, err))
            self.assertTrue(mod.return_value.init_sync.called)
            self.assertTrue(mod.return_value.disable_sync.called)

    def test_sync_error_and_unknown_action(self) -> None:
        with mock.patch.object(context_cli, "_get_context_sync") as mod:
            mod.return_value.SyncError = RuntimeError
            mod.return_value.sync_status.side_effect = RuntimeError("bad sync")
            rc, _, err = self._capture(context_cli.cmd_sync, argparse.Namespace(sync_action="status", remote=False))
            self.assertEqual(rc, 1)
            self.assertIn("Sync error", err)
            rc, _, err = self._capture(context_cli.cmd_sync, argparse.Namespace(sync_action="unknown"))
            self.assertEqual(rc, 2)
            self.assertIn("unknown", err)

    def test_daemon_actions(self) -> None:
        status = argparse.Namespace(running=False, pid=None, pid_file="pid", service="service")
        with mock.patch.object(context_cli, "_get_context_runtime") as runtime:
            runtime.return_value.daemon_status.return_value = status
            runtime.return_value.start_daemon.return_value = 123
            runtime.return_value.stop_daemon.return_value = True
            runtime.return_value.install_service.return_value = {"installed": True}
            runtime.return_value.uninstall_service.return_value = {"removed": True}
            actions = [
                argparse.Namespace(daemon_action="start"),
                argparse.Namespace(daemon_action="stop"),
                argparse.Namespace(daemon_action="status"),
                argparse.Namespace(daemon_action="install"),
                argparse.Namespace(daemon_action="uninstall"),
            ]
            for args in actions:
                rc, _, err = self._capture(context_cli.cmd_daemon, args)
                self.assertEqual(rc, 0, err)
            runtime.return_value.daemon_status.assert_called()

    def test_daemon_error_unknown_and_run(self) -> None:
        with mock.patch.object(context_cli, "_get_context_runtime") as runtime:
            runtime.return_value.start_daemon.side_effect = OSError("no permission")
            rc, _, err = self._capture(context_cli.cmd_daemon, argparse.Namespace(daemon_action="start"))
            self.assertEqual(rc, 1)
            self.assertIn("Daemon error", err)
            rc, _, err = self._capture(context_cli.cmd_daemon, argparse.Namespace(daemon_action="unknown"))
            self.assertEqual(rc, 2)
            self.assertIn("unknown", err)
        with mock.patch.object(context_cli, "_load_module") as loader:
            loader.return_value.main.return_value = None
            rc, _, _ = self._capture(context_cli.cmd_daemon, argparse.Namespace(daemon_action="run"))
            self.assertEqual(rc, 0)

    def test_export_import_error_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "dir"
            directory.mkdir()
            rc, _, err = self._capture(
                context_cli.cmd_export, argparse.Namespace(output="", query="", limit=1, source_type="all")
            )
            self.assertEqual(rc, 2)
            self.assertIn("output", err)
            rc, _, err = self._capture(
                context_cli.cmd_export, argparse.Namespace(output=str(directory), query="", limit=1, source_type="all")
            )
            self.assertEqual(rc, 2)
            missing = Path(tmp) / "missing.json"
            rc, _, err = self._capture(context_cli.cmd_import, argparse.Namespace(input=str(missing), no_sync=False))
            self.assertEqual(rc, 1)
            self.assertIn("Error reading", err)
            invalid = Path(tmp) / "invalid.json"
            invalid.write_text("not-json", encoding="utf-8")
            rc, _, err = self._capture(context_cli.cmd_import, argparse.Namespace(input=str(invalid), no_sync=False))
            self.assertEqual(rc, 1)
            self.assertIn("Error parsing", err)

    def test_completion_errors_and_version(self) -> None:
        rc, _, err = self._capture(context_cli.cmd_completion, argparse.Namespace(shell=""))
        self.assertEqual(rc, 2)
        self.assertIn("shell", err)
        rc, _, err = self._capture(context_cli.cmd_completion, argparse.Namespace(shell="powershell"))
        self.assertEqual(rc, 2)
        self.assertIn("unsupported", err)
        rc, out, _ = self._capture(context_cli.cmd_completion, argparse.Namespace(shell="bash"))
        self.assertEqual(rc, 0)
        self.assertIn("ContextGO", out)
        self.assertRegex(context_cli._read_version(), r"^0\.13\.0")

    def test_search_and_semantic_error_contracts(self) -> None:
        search = argparse.Namespace(query="", type="all", limit=5, literal=False)
        rc, _, err = self._capture(context_cli.cmd_search, search)
        self.assertEqual(rc, 2)
        self.assertIn("query", err)
        search.query = "missing"
        with mock.patch.object(
            context_cli._get_session_index(), "format_search_results", return_value="No matches found"
        ):
            rc, _, err = self._capture(context_cli.cmd_search, search)
        self.assertEqual(rc, 1)
        self.assertIn("No matches", err)
        search.query = "found"
        with mock.patch.object(context_cli._get_session_index(), "format_search_results", return_value="Found result"):
            rc, out, _ = self._capture(context_cli.cmd_search, search)
        self.assertEqual(rc, 0)
        self.assertIn("Found result", out)

        semantic = argparse.Namespace(query="", limit=3)
        rc, _, err = self._capture(context_cli.cmd_semantic, semantic)
        self.assertEqual(rc, 2)
        semantic.query = "nothing"
        with (
            mock.patch.object(context_cli, "_local_memory_matches", return_value=[]),
            mock.patch.object(context_cli._get_session_index(), "format_search_results", return_value=""),
        ):
            rc, _, err = self._capture(context_cli.cmd_semantic, semantic)
        self.assertEqual(rc, 1)
        self.assertIn("No results", err)

    def test_save_remote_security_and_failure_paths(self) -> None:
        args = argparse.Namespace(title="t", content="c", tags="a,b")
        with mock.patch.object(context_cli, "_save_local_memory", return_value="Failed to save memory: bad"):
            rc, _, _ = self._capture(context_cli.cmd_save, args)
        self.assertEqual(rc, 1)
        with mock.patch.object(context_cli._get_context_core(), "write_memory_markdown", side_effect=ValueError("bad")):
            with mock.patch.object(context_cli, "ENABLE_REMOTE_MEMORY_HTTP", False):
                result = context_cli._save_local_memory("t", "c", [])
        self.assertIn("Failed", result)
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(context_cli, "LOCAL_CONVERSATIONS_ROOT", Path(tmp)),
                mock.patch.object(context_cli, "ENABLE_REMOTE_MEMORY_HTTP", True),
                mock.patch.object(context_cli, "REMOTE_MEMORY_URL", "http://remote.invalid/api"),
            ):
                result = context_cli._save_local_memory("t", "c", [])
            self.assertIn("HTTPS required", result)

    def test_serve_native_vector_and_q_edges(self) -> None:
        rc, _, err = self._capture(context_cli.cmd_serve, argparse.Namespace(host="127.0.0.1", port=0, token=""))
        self.assertEqual(rc, 2)
        native = argparse.Namespace(threads=0)
        rc, _, err = self._capture(context_cli.cmd_native_scan, native)
        self.assertEqual(rc, 2)
        vector = argparse.Namespace(force=False)
        si = mock.Mock()
        si.get_session_db_path.return_value = Path("session.db")
        vi = mock.Mock()
        vi.get_vector_db_path.return_value = Path("vector.db")
        vi.vector_status.return_value = {"documents": 0}
        with (
            mock.patch.object(context_cli, "_get_session_index", return_value=si),
            mock.patch.object(context_cli, "_import_vector_index", return_value=vi),
        ):
            rc, _, _ = self._capture(context_cli.cmd_vector_status, vector)
        self.assertEqual(rc, 0)
        q = argparse.Namespace(query=[], limit=5, json=False)
        rc, _, err = self._capture(context_cli.cmd_q, q)
        self.assertEqual(rc, 2)
        q.query = ["abcdef12"]
        with mock.patch.object(context_cli, "_q_session_lookup", return_value=1) as lookup:
            rc, _, _ = self._capture(context_cli.cmd_q, q)
        self.assertEqual(rc, 1)
        lookup.assert_called_once()

    def test_run_and_main_exception_edges(self) -> None:
        rc, _, _ = self._capture(context_cli.run, argparse.Namespace(command=None))
        self.assertEqual(rc, 0)
        rc, _, err = self._capture(context_cli.run, argparse.Namespace(command="unknown"))
        self.assertEqual(rc, 2)
        self.assertIn("unknown", err)
        with mock.patch.object(context_cli, "run", side_effect=KeyboardInterrupt):
            rc = context_cli.main([])
        self.assertEqual(rc, 130)

    def test_setup_all_tools_success_branch(self) -> None:
        fake = mock.Mock(BRAND="ContextGO")
        fake.setup_all.return_value = {"codex": True, "claude": True}
        with mock.patch.object(context_cli, "_get_context_prewarm", return_value=fake):
            rc, out, _ = self._capture(context_cli.cmd_setup, argparse.Namespace())
        self.assertEqual(rc, 0)
        self.assertIn("配置完成", out)

    def test_shell_init_and_quick_recall_rendering(self) -> None:
        rc, out, _ = self._capture(context_cli.cmd_shell_init, argparse.Namespace())
        self.assertEqual(rc, 0)
        self.assertIn("alias cgs", out)
        rows = [
            {
                "session_id": "12345678-rest",
                "created_at": "2026-01-01T00:00:00Z",
                "source_type": "codex_session",
                "title": "Title",
                "snippet": "A useful snippet",
            }
        ]
        rc, out, _ = self._capture(lambda _: context_cli._q_session_lookup("12345678", 5, False), None)
        self.assertEqual(rc, 1)
        with mock.patch.object(context_cli, "_get_session_index") as si:
            si.return_value.lookup_session_by_id.return_value = rows
            rc, out, _ = self._capture(lambda _: context_cli._q_session_lookup("12345678", 5, False), None)
        self.assertEqual(rc, 0)
        self.assertIn("A useful snippet", out)
        context_cli._print_q_results(rows, as_json=True)


if __name__ == "__main__":
    unittest.main()
