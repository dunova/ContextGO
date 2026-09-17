#!/usr/bin/env python3
"""Coverage-focused tests for CLI entry points and identity failure paths.

These complement ``test_cross_machine_memory.py`` by exercising branches that
only appear on error or refresh paths, which the behavioural tests never reach.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import context_cli
import node_identity
import source_adapters


class LazyModuleGetterTests(unittest.TestCase):
    """``context_cli.__getattr__`` must resolve known modules and reject others."""

    def test_known_lazy_module_resolves(self) -> None:
        module = context_cli.session_index
        self.assertTrue(hasattr(module, "sync_session_index"))

    def test_unknown_attribute_raises(self) -> None:
        with self.assertRaises(AttributeError):
            context_cli.definitely_not_a_module  # noqa: B018


class MainEntryPointTests(unittest.TestCase):
    """``context_cli.main`` must translate exceptions into documented exit codes."""

    def _run_main(self, side_effect: BaseException) -> tuple[int, str]:
        buffer = io.StringIO()
        with (
            mock.patch.object(context_cli, "build_parser") as parser_factory,
            mock.patch.object(context_cli, "run", side_effect=side_effect),
        ):
            parser = mock.MagicMock()
            parser.parse_args.return_value = type("A", (), {"command": "search"})()
            parser_factory.return_value = parser
            with mock.patch("sys.stderr", buffer):
                code = context_cli.main(["search", "x"])
        return code, buffer.getvalue()

    def test_unhandled_exception_returns_one(self) -> None:
        code, stderr = self._run_main(RuntimeError("boom"))
        self.assertEqual(code, 1)
        self.assertIn("boom", stderr)

    def test_broken_pipe_returns_zero(self) -> None:
        code, _ = self._run_main(BrokenPipeError())
        self.assertEqual(code, 0)

    def test_keyboard_interrupt_returns_130(self) -> None:
        code, stderr = self._run_main(KeyboardInterrupt())
        self.assertEqual(code, 130)
        self.assertIn("Interrupted", stderr)


class AdapterNamespaceFailureTests(unittest.TestCase):
    """Failure branches of the mirror namespace helpers must be safe."""

    def test_adopt_legacy_namespace_tolerates_rename_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "legacy"
            legacy.mkdir()
            current = root / "current"
            with mock.patch.object(Path, "rename", side_effect=OSError("cross-device link")):
                # Must not raise: callers rebuild from live sources instead.
                source_adapters._adopt_legacy_namespace(legacy, current)
            self.assertTrue(legacy.is_dir())

    def test_adopt_legacy_namespace_noop_when_current_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "legacy"
            legacy.mkdir()
            current = root / "current"
            current.mkdir()
            source_adapters._adopt_legacy_namespace(legacy, current)
            self.assertTrue(legacy.is_dir())
            self.assertTrue(current.is_dir())

    def test_adopt_legacy_namespace_noop_when_legacy_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_adapters._adopt_legacy_namespace(root / "absent", root / "current")
            self.assertFalse((root / "current").exists())

    def test_schema_version_mismatch_clears_stale_adapter_children(self) -> None:
        """A schema bump wipes only the adapter mirror's contents, by design."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".schema_version").write_text("ancient-version", encoding="utf-8")
            child_dir = root / "deepseek_session"
            child_dir.mkdir()
            (child_dir / "old.jsonl").write_text("{}", encoding="utf-8")
            stray = root / "stray.txt"
            stray.write_text("x", encoding="utf-8")

            source_adapters._ensure_adapter_schema(root)

            self.assertFalse(child_dir.exists())
            self.assertFalse(stray.exists())
            self.assertEqual(
                (root / ".schema_version").read_text(encoding="utf-8"),
                source_adapters.ADAPTER_SCHEMA_VERSION,
            )

    def test_schema_version_match_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".schema_version").write_text(source_adapters.ADAPTER_SCHEMA_VERSION, encoding="utf-8")
            kept = root / "keep.jsonl"
            kept.write_text("{}", encoding="utf-8")
            source_adapters._ensure_adapter_schema(root)
            self.assertTrue(kept.is_file())


class NodeIdentityRefreshFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.storage = Path(self._tmp.name) / "contextgo"
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

    def test_label_backfill_write_failure_is_swallowed(self) -> None:
        """A read-only identity file must not break indexing."""
        node_identity.node_id()
        path = self.storage / node_identity.NODE_FILE_NAME
        original = node_identity.node_id()
        with (
            mock.patch.object(node_identity, "_label", return_value="new-host"),
            mock.patch.object(node_identity, "atomic_write_json", side_effect=OSError("read-only")),
        ):
            node_identity._CACHE.clear()
            self.assertEqual(node_identity.node_label(), "new-host")
        self.assertTrue(path.is_file())
        self.assertEqual(node_identity.node_id(), original)


if __name__ == "__main__":
    unittest.main()


class PolicySweepSafetyTests(unittest.TestCase):
    """``setup``/``unsetup`` must not rewrite unrelated projects' rule files.

    The sweep used to run unconditionally over every project under ``$HOME``,
    so running ``contextgo unsetup`` (or simply the test suite) stripped the SCF
    block out of unrelated repositories — and, when the block was the whole
    file, left a 0-line artefact behind that silently overrode nothing.
    """

    def setUp(self) -> None:
        import contextgo.context_prewarm as prewarm

        self.prewarm = prewarm
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workdir = Path(self._tmp.name) / "work"
        self.workdir.mkdir(parents=True)
        self._cwd = Path.cwd()
        os.chdir(self.workdir)
        self.addCleanup(lambda: os.chdir(self._cwd))
        self._env = mock.patch.dict(os.environ, {"CONTEXTGO_SETUP_SCAN_HOME": ""}, clear=False)
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_home_sweep_is_off_by_default(self) -> None:
        self.assertFalse(self.prewarm._home_sweep_enabled())

    def test_project_roots_defaults_to_cwd_only(self) -> None:
        roots = self.prewarm._policy_project_roots()
        self.assertEqual(roots, [self.workdir])

    def test_home_sweep_can_be_enabled(self) -> None:
        with mock.patch.dict(os.environ, {"CONTEXTGO_SETUP_SCAN_HOME": "1"}, clear=False):
            self.assertTrue(self.prewarm._home_sweep_enabled())
            # Fake a home with two project directories.
            home = Path(self._tmp.name) / "home"
            (home / "proj-a").mkdir(parents=True)
            (home / "proj-b").mkdir(parents=True)
            with mock.patch.object(Path, "home", return_value=home):
                roots = self.prewarm._policy_project_roots()
        self.assertIn(home / "proj-a", roots)
        self.assertIn(home / "proj-b", roots)

    def test_home_sweep_respects_extra_filter(self) -> None:
        home = Path(self._tmp.name) / "home2"
        (home / "with-github" / ".github").mkdir(parents=True)
        (home / "without-github").mkdir(parents=True)
        with (
            mock.patch.dict(os.environ, {"CONTEXTGO_SETUP_SCAN_HOME": "1"}, clear=False),
            mock.patch.object(Path, "home", return_value=home),
        ):
            roots = self.prewarm._policy_project_roots(lambda p: (p / ".github").exists())
        self.assertIn(home / "with-github", roots)
        self.assertNotIn(home / "without-github", roots)

    def test_teardown_deletes_a_file_that_was_only_the_policy(self) -> None:
        target = self.workdir / ".cursorrules"
        self.prewarm._inject_scf_policy(target)
        self.assertTrue(target.is_file())

        self.prewarm._remove_scf_policy(target)

        self.assertFalse(target.exists(), "an emptied rules file must be removed, not left blank")

    def test_teardown_preserves_unrelated_content(self) -> None:
        target = self.workdir / ".cursorrules"
        target.write_text("# 我的项目规则\n\n不要删除用户数据。\n", encoding="utf-8")
        self.prewarm._inject_scf_policy(target)

        self.prewarm._remove_scf_policy(target)

        self.assertTrue(target.is_file())
        self.assertIn("不要删除用户数据", target.read_text(encoding="utf-8"))

    def test_teardown_does_not_touch_other_projects_by_default(self) -> None:
        """A sibling project's fully-injected rules file must be left alone."""
        sibling = Path(self._tmp.name) / "sibling"
        sibling.mkdir()
        victim = sibling / ".cursorrules"
        self.prewarm._inject_scf_policy(victim)
        before = victim.read_text(encoding="utf-8")

        # cwd is self.workdir; the sibling is not reachable without the sweep.
        self.prewarm.teardown_cursor()

        self.assertTrue(victim.is_file())
        self.assertEqual(victim.read_text(encoding="utf-8"), before)


class PolicyLifecycleTests(unittest.TestCase):
    """Full inject → teardown lifecycle for the project-scoped policy targets."""

    def setUp(self) -> None:
        import contextgo.context_prewarm as prewarm

        self.prewarm = prewarm
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()
        self._cwd = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(lambda: os.chdir(self._cwd))
        self._env = mock.patch.dict(os.environ, {"CONTEXTGO_SETUP_SCAN_HOME": ""}, clear=False)
        self._env.start()
        self.addCleanup(self._env.stop)

    # ---- Cursor -----------------------------------------------------------
    def test_cursor_setup_creates_then_teardown_removes(self) -> None:
        self.assertTrue(self.prewarm.setup_cursor())
        rules = self.project / ".cursorrules"
        self.assertTrue(rules.is_file())
        self.assertIn(self.prewarm._SCF_MARKER_START, rules.read_text(encoding="utf-8"))

        self.assertTrue(self.prewarm.teardown_cursor())
        self.assertFalse(rules.exists())

    def test_cursor_setup_preserves_existing_rules(self) -> None:
        rules = self.project / ".cursorrules"
        rules.write_text("# 我的规则\n\n不要动生产数据。\n", encoding="utf-8")
        self.prewarm.setup_cursor()
        text = rules.read_text(encoding="utf-8")
        self.assertIn("不要动生产数据", text)
        self.assertIn(self.prewarm._SCF_MARKER_START, text)

        self.prewarm.teardown_cursor()
        remaining = rules.read_text(encoding="utf-8")
        self.assertIn("不要动生产数据", remaining)
        self.assertNotIn(self.prewarm._SCF_MARKER_START, remaining)

    def test_cursor_setup_is_idempotent(self) -> None:
        self.prewarm.setup_cursor()
        first = (self.project / ".cursorrules").read_text(encoding="utf-8")
        self.prewarm.setup_cursor()
        second = (self.project / ".cursorrules").read_text(encoding="utf-8")
        self.assertEqual(first, second)

    def test_cursor_teardown_without_rules_file_is_ok(self) -> None:
        self.assertTrue(self.prewarm.teardown_cursor())

    # ---- Copilot ----------------------------------------------------------
    def test_copilot_setup_and_teardown(self) -> None:
        (self.project / ".github").mkdir()
        self.assertTrue(self.prewarm.setup_copilot())
        target = self.project / ".github" / "copilot-instructions.md"
        self.assertTrue(target.is_file())
        self.assertIn(self.prewarm._SCF_MARKER_START, target.read_text(encoding="utf-8"))

        self.assertTrue(self.prewarm.teardown_copilot())
        self.assertFalse(target.exists())

    def test_copilot_setup_creates_github_dir(self) -> None:
        self.prewarm.setup_copilot()
        self.assertTrue((self.project / ".github" / "copilot-instructions.md").is_file())

    def test_copilot_teardown_without_file_is_ok(self) -> None:
        self.assertTrue(self.prewarm.teardown_copilot())

    # ---- inject/remove primitives ----------------------------------------
    def test_inject_then_remove_restores_original_exactly(self) -> None:
        original = "# 原文件\n\n第二行\n"
        target = self.project / "notes.md"
        target.write_text(original, encoding="utf-8")

        self.prewarm._inject_scf_policy(target)
        self.assertNotEqual(target.read_text(encoding="utf-8"), original)

        self.prewarm._remove_scf_policy(target)
        self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_remove_reports_true_when_marker_absent(self) -> None:
        target = self.project / "plain.md"
        target.write_text("no policy here\n", encoding="utf-8")
        self.assertTrue(self.prewarm._remove_scf_policy(target))
        self.assertTrue(target.is_file())

    def test_remove_missing_file_is_ok(self) -> None:
        self.assertTrue(self.prewarm._remove_scf_policy(self.project / "absent.md"))

    def test_inject_returns_true_when_already_present(self) -> None:
        target = self.project / "notes.md"
        target.write_text("# 内容\n", encoding="utf-8")
        self.assertTrue(self.prewarm._inject_scf_policy(target))
        self.assertTrue(self.prewarm._inject_scf_policy(target))


class QuickRecallVectorPathTests(unittest.TestCase):
    """``contextgo q`` must prefer vector search and fall back to FTS5 cleanly."""

    def setUp(self) -> None:
        import contextgo.context_cli as cli

        self.cli = cli
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._env = mock.patch.dict(
            os.environ,
            {
                "CONTEXTGO_STORAGE_ROOT": str(Path(self._tmp.name) / "cg"),
                "CONTEXTGO_NODE_ID": "feedfacefeedface",
            },
            clear=False,
        )
        self._env.start()
        self.addCleanup(self._env.stop)

    def _args(self, query="what did we decide", **kw):
        import argparse

        return argparse.Namespace(query=[query], json=kw.get("json", False), limit=kw.get("limit", 5))

    def _fake_vector_module(self, *, ranked, enriched, available=True):
        module = mock.MagicMock()
        module.vector_available.return_value = available
        module.get_vector_db_path.return_value = Path("/tmp/v.db")
        module.hybrid_search_session.return_value = ranked
        module.fetch_enriched_results.return_value = enriched
        return module

    def test_vector_hits_short_circuit(self) -> None:
        rows = [{"session_id": "abcdef12", "created_at": "2026-01-01", "source_type": "x", "title": "T"}]
        module = self._fake_vector_module(ranked=[1], enriched=rows)
        buffer = io.StringIO()
        with (
            mock.patch.object(self.cli, "_import_vector_index", return_value=module),
            contextlib.redirect_stdout(buffer),
        ):
            rc = self.cli.cmd_q(self._args())
        self.assertEqual(rc, 0)
        self.assertIn("T", buffer.getvalue())

    def test_vector_hits_with_json_output(self) -> None:
        rows = [{"session_id": "abcdef12", "title": "T"}]
        module = self._fake_vector_module(ranked=[1], enriched=rows)
        buffer = io.StringIO()
        with (
            mock.patch.object(self.cli, "_import_vector_index", return_value=module),
            contextlib.redirect_stdout(buffer),
        ):
            rc = self.cli.cmd_q(self._args(json=True))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buffer.getvalue())[0]["title"], "T")

    def test_empty_vector_ranking_falls_back_to_fts(self) -> None:
        module = self._fake_vector_module(ranked=[], enriched=[])
        si = mock.MagicMock()
        si.format_search_results.return_value = "fts hit"
        buffer = io.StringIO()
        with (
            mock.patch.object(self.cli, "_import_vector_index", return_value=module),
            mock.patch.object(self.cli, "_get_session_index", return_value=si),
            contextlib.redirect_stdout(buffer),
        ):
            rc = self.cli.cmd_q(self._args())
        self.assertEqual(rc, 0)
        self.assertIn("fts hit", buffer.getvalue())

    def test_vector_exception_falls_back_to_fts(self) -> None:
        si = mock.MagicMock()
        si.format_search_results.return_value = "fts hit"
        buffer = io.StringIO()
        with (
            mock.patch.object(self.cli, "_import_vector_index", side_effect=ImportError("no vector")),
            mock.patch.object(self.cli, "_get_session_index", return_value=si),
            contextlib.redirect_stdout(buffer),
        ):
            rc = self.cli.cmd_q(self._args())
        self.assertEqual(rc, 0)
        self.assertIn("fts hit", buffer.getvalue())

    def test_no_matches_returns_one(self) -> None:
        si = mock.MagicMock()
        si.format_search_results.return_value = "No matches found for: 'x'"
        buffer = io.StringIO()
        with (
            mock.patch.object(self.cli, "_import_vector_index", side_effect=ImportError("no vector")),
            mock.patch.object(self.cli, "_get_session_index", return_value=si),
            contextlib.redirect_stdout(buffer),
        ):
            rc = self.cli.cmd_q(self._args())
        self.assertEqual(rc, 1)

    def test_json_fallback_uses_private_search_rows_when_available(self) -> None:
        si = mock.MagicMock()
        si.format_search_results.return_value = "something"
        si._search_rows.return_value = [{"session_id": "abcdef12"}]

        buffer = io.StringIO()
        with (
            mock.patch.object(self.cli, "_import_vector_index", side_effect=ImportError("no vector")),
            mock.patch.object(self.cli, "_get_session_index", return_value=si),
            contextlib.redirect_stdout(buffer),
        ):
            rc = self.cli.cmd_q(self._args(json=True))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buffer.getvalue())[0]["session_id"], "abcdef12")

    def test_empty_query_prints_usage(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            rc = self.cli.cmd_q(self._args(query="   "))
        self.assertEqual(rc, 2)
        self.assertIn("Usage", buffer.getvalue())
