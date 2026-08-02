from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import contextgo.context_runtime as runtime


class RuntimeTests(unittest.TestCase):
    def test_windows_directories_use_appdata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            local = Path(tmp) / "localappdata"
            roaming = Path(tmp) / "appdata"
            with mock.patch.object(runtime, "os") as os_mock:
                os_mock.name = "nt"
                os_mock.environ = {"LOCALAPPDATA": str(local), "APPDATA": str(roaming)}
                os_mock.path = os.path
                self.assertEqual(runtime.platform_data_dir(home), local / "contextgo")
                self.assertEqual(runtime.platform_config_dir(home), roaming / "contextgo")

    def test_runtime_python_is_current_interpreter(self) -> None:
        self.assertEqual(runtime.runtime_python(), os.sys.executable)

    def test_atomic_json_write_is_readable_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "state.json"
            runtime.atomic_write_json(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"ok": True})
            self.assertFalse(path.with_name(".state.json.999.tmp").exists())

    def test_dead_pid_is_not_running(self) -> None:
        self.assertFalse(runtime.process_is_alive(2**31 - 1))

    def test_platform_dirs_cover_darwin_and_linux(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            with mock.patch.object(runtime.sys, "platform", "darwin"), mock.patch.object(runtime.os, "name", "posix"):
                self.assertIn("Application Support", str(runtime.platform_data_dir(home)))
                self.assertIn("Caches", str(runtime.platform_cache_dir(home)))
            with mock.patch.object(runtime.sys, "platform", "linux"), mock.patch.object(runtime.os, "name", "posix"):
                self.assertEqual(runtime.platform_config_dir(home), home / ".config" / "contextgo")
                self.assertEqual(runtime.platform_cache_dir(home), home / ".cache" / "contextgo")

    def test_storage_root_preserves_legacy_unless_opted_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            legacy = home / ".contextgo"
            legacy.mkdir(parents=True)
            with mock.patch.dict(
                os.environ,
                {"CONTEXTGO_HOME": str(home), "CONTEXTGO_STORAGE_ROOT": "", "CONTEXTGO_PLATFORM_STORAGE": ""},
                clear=False,
            ):
                self.assertEqual(runtime.storage_root(home=home), legacy.resolve())
            with mock.patch.dict(
                os.environ,
                {"CONTEXTGO_HOME": str(home), "CONTEXTGO_STORAGE_ROOT": "", "CONTEXTGO_PLATFORM_STORAGE": "1"},
                clear=False,
            ):
                self.assertNotEqual(runtime.storage_root(home=home), legacy.resolve())

    def test_pid_reading_and_daemon_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "daemon.lock"
            pid_file.write_text("not-a-pid", encoding="utf-8")
            self.assertIsNone(runtime.read_pid(pid_file))
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
            self.assertEqual(runtime.read_pid(pid_file), os.getpid())
            with mock.patch.object(runtime, "daemon_pid_path", return_value=pid_file):
                status = runtime.daemon_status()
            self.assertTrue(status.running)
            self.assertEqual(status.pid, os.getpid())

    def test_service_names_and_install_without_windows_schtasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(runtime, "config_dir", return_value=Path(tmp) / "cfg"),
                mock.patch.object(runtime.os, "name", "nt"),
                mock.patch.object(runtime, "command_available", return_value=False),
            ):
                result = runtime.install_service()
            self.assertFalse(result["installed"])
            self.assertIn("schtasks", str(result["error"]))

    def test_install_uninstall_for_posix_service_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cfg = Path(tmp) / "cfg"
            with (
                mock.patch.object(runtime, "config_dir", return_value=cfg),
                mock.patch.object(runtime, "command_available", return_value=False),
                mock.patch.object(runtime.Path, "home", return_value=home),
                mock.patch.object(runtime.os, "name", "posix"),
                mock.patch.object(runtime.sys, "platform", "linux"),
            ):
                installed = runtime.install_service()
                removed = runtime.uninstall_service()
            self.assertTrue(installed["installed"])
            self.assertTrue(str(installed["path"]).endswith("contextgo.service"))
            self.assertTrue(removed["removed"])

    def test_start_and_stop_daemon_edges(self) -> None:
        alive = runtime.DaemonStatus(True, 123, "pid", "svc")
        dead = runtime.DaemonStatus(False, None, "pid", "svc")
        with mock.patch.object(runtime, "daemon_status", return_value=alive):
            self.assertEqual(runtime.start_daemon(), 123)
        with mock.patch.object(runtime, "daemon_status", return_value=dead):
            self.assertTrue(runtime.stop_daemon())

    def test_environment_overrides_and_tool_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            with mock.patch.dict(
                os.environ,
                {
                    "CONTEXTGO_HOME": str(home),
                    "XDG_DATA_HOME": str(Path(tmp) / "data"),
                    "XDG_CONFIG_HOME": str(Path(tmp) / "cfg"),
                    "XDG_CACHE_HOME": str(Path(tmp) / "cache"),
                },
                clear=False,
            ):
                self.assertTrue(runtime.user_home() == home.resolve())
                self.assertTrue(runtime.config_dir().name == "contextgo")
                self.assertTrue(runtime.cache_dir().name == "contextgo")
                self.assertTrue(runtime.platform_state_dir(home).name == "state")
                self.assertTrue(runtime.tool_data_roots(home))
                self.assertTrue(runtime.tool_config_roots(home))

    def test_private_helpers_and_pid_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "private"
            self.assertEqual(runtime.ensure_private_dir(root), root)
            file = root / "file"
            runtime.atomic_write_text(file, "hello")
            runtime.restrict_file(file)
            self.assertEqual(file.read_text(encoding="utf-8"), "hello")
            bad = root / "bad"
            bad.write_text("0", encoding="utf-8")
            self.assertIsNone(runtime.read_pid(bad))
            self.assertFalse(runtime.process_is_alive(0))

    def test_platform_service_names(self) -> None:
        with mock.patch.object(runtime.os, "name", "nt"):
            self.assertIn("Task Scheduler", runtime.service_name())
        with mock.patch.object(runtime.os, "name", "posix"), mock.patch.object(runtime.sys, "platform", "darwin"):
            self.assertIn("launchd", runtime.service_name())
        with mock.patch.object(runtime.os, "name", "posix"), mock.patch.object(runtime.sys, "platform", "linux"):
            self.assertIn("systemd", runtime.service_name())

    def test_start_daemon_running_and_spawn_paths(self) -> None:
        running = runtime.DaemonStatus(True, 42, "pid", "service")
        with mock.patch.object(runtime, "daemon_status", return_value=running):
            self.assertEqual(runtime.start_daemon(), 42)
        dead = runtime.DaemonStatus(False, None, "pid", "service")
        proc = mock.Mock(pid=99)
        proc.poll.return_value = 0
        spawn_root = Path(tempfile.gettempdir()) / "cg-runtime-test"
        (spawn_root / "logs").mkdir(parents=True, exist_ok=True)
        with (
            mock.patch.object(runtime, "daemon_status", return_value=dead),
            mock.patch.object(runtime.subprocess, "Popen", return_value=proc),
            mock.patch.object(runtime, "storage_root", return_value=spawn_root),
            mock.patch.object(runtime, "ensure_private_dir"),
        ):
            self.assertEqual(runtime.start_daemon(), 99)

    def test_stop_daemon_no_pid_and_kill_failure(self) -> None:
        with mock.patch.object(runtime, "daemon_status", return_value=runtime.DaemonStatus(False, None, "p", "s")):
            self.assertTrue(runtime.stop_daemon())
        status = runtime.DaemonStatus(True, 123, "p", "s")
        with (
            mock.patch.object(runtime, "daemon_status", return_value=status),
            mock.patch.object(runtime.os, "kill", side_effect=OSError("gone")),
        ):
            self.assertTrue(runtime.stop_daemon())

    def test_service_install_windows_and_posix_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            home = Path(tmp) / "home"
            with (
                mock.patch.object(runtime, "config_dir", return_value=cfg),
                mock.patch.object(runtime.os, "name", "nt"),
                mock.patch.object(runtime, "command_available", return_value=True),
                mock.patch.object(runtime.subprocess, "run", return_value=mock.Mock(returncode=0)),
            ):
                self.assertTrue(runtime.install_service()["installed"])
                self.assertTrue(runtime.uninstall_service()["removed"])
            with (
                mock.patch.object(runtime, "config_dir", return_value=cfg),
                mock.patch.object(runtime.os, "name", "posix"),
                mock.patch.object(runtime.sys, "platform", "darwin"),
                mock.patch.object(runtime.Path, "home", return_value=home),
            ):
                self.assertTrue(runtime.install_service()["installed"])
                self.assertTrue(runtime.uninstall_service()["removed"])
            with (
                mock.patch.object(runtime, "config_dir", return_value=cfg),
                mock.patch.object(runtime.os, "name", "posix"),
                mock.patch.object(runtime.sys, "platform", "linux"),
                mock.patch.object(runtime.Path, "home", return_value=home),
                mock.patch.object(runtime, "command_available", return_value=False),
            ):
                self.assertTrue(runtime.install_service()["installed"])
                self.assertTrue(runtime.uninstall_service()["removed"])


if __name__ == "__main__":
    unittest.main()
