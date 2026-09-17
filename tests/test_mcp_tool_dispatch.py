#!/usr/bin/env python3
"""Coverage tests for the MCP tool dispatch surface and JSON-RPC emitters.

The stdio loop itself is covered by ``tests/test_mcp_server.py``; these tests
target the per-tool branches and the response emitters.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_server


class TestToolDispatch:
    def test_recall_requires_query(self):
        assert mcp_server._handle_tool_call("contextgo_recall", {}) == "No search query provided."

    def test_search_returns_placeholder_when_empty(self, monkeypatch):
        monkeypatch.setattr(mcp_server.session_index, "format_search_results", lambda *a, **k: "")
        result = mcp_server._handle_tool_call("contextgo_search", {"query": "abc"})
        assert result == "No sessions found matching: 'abc'"

    def test_search_passes_clamped_limit(self, monkeypatch):
        captured = {}

        def fake(query, *, limit):
            captured["limit"] = limit
            return "hits"

        monkeypatch.setattr(mcp_server.session_index, "format_search_results", fake)
        assert mcp_server._handle_tool_call("contextgo_search", {"query": "q", "limit": 99}) == "hits"
        assert captured["limit"] == 20

    def test_search_defaults_limit_when_missing(self, monkeypatch):
        captured = {}

        def fake(query, *, limit):
            captured["limit"] = limit
            return "hits"

        monkeypatch.setattr(mcp_server.session_index, "format_search_results", fake)
        mcp_server._handle_tool_call("contextgo_recall", {"query": "q"})
        assert captured["limit"] == 5

    def test_semantic_requires_topic(self):
        assert mcp_server._handle_tool_call("contextgo_semantic", {}) == "No topic provided."

    def test_semantic_lists_memories_and_supplements_with_sessions(self, monkeypatch):
        monkeypatch.setattr(
            mcp_server.memory_index,
            "search_index",
            lambda topic, limit: [{"title": "T1", "text": "body one"}],
        )
        monkeypatch.setattr(
            mcp_server.session_index,
            "format_search_results",
            lambda q, limit: "session-hit",
        )
        result = mcp_server._handle_tool_call("contextgo_semantic", {"topic": "topic", "limit": 3})
        assert "Durable Memories for 'topic':" in result
        assert "Related Sessions for 'topic':" in result

    def test_semantic_skips_no_match_supplement(self, monkeypatch):
        monkeypatch.setattr(mcp_server.memory_index, "search_index", lambda topic, limit: [])
        monkeypatch.setattr(
            mcp_server.session_index,
            "format_search_results",
            lambda q, limit: "No matches found for: 'x'",
        )
        result = mcp_server._handle_tool_call("contextgo_semantic", {"topic": "x"})
        assert result == "No memories or sessions found for: 'x'"

    def test_semantic_falls_back_to_text_snippet(self, monkeypatch):
        monkeypatch.setattr(
            mcp_server.memory_index,
            "search_index",
            lambda topic, limit: [{"snippet": "snippet body"}],
        )
        monkeypatch.setattr(mcp_server.session_index, "format_search_results", lambda q, limit: "")
        result = mcp_server._handle_tool_call("contextgo_semantic", {"topic": "t", "limit": 1})
        assert "snippet body" in result

    def test_save_requires_title_and_content(self):
        assert "required" in mcp_server._handle_tool_call("contextgo_save", {"title": "t"})

    def test_save_delegates_to_the_cli_save_path(self, monkeypatch):
        """Regression: this used to call a non-existent ``save_memory``."""
        # mcp_server resolves context_cli through the ``contextgo`` package, so
        # the patch must target that module object, not the flat-imported twin.
        import contextgo.context_cli as context_cli

        captured = {}

        def fake_save(title, content, tags):
            captured.update({"title": title, "content": content, "tags": tags})
            return f"Saved locally: {title}"

        monkeypatch.setattr(context_cli, "_save_local_memory", fake_save)
        result = mcp_server._handle_tool_call("contextgo_save", {"title": "T", "content": "C", "tags": " a , b , "})
        assert captured == {"title": "T", "content": "C", "tags": ["a", "b"]}
        assert result == "Saved locally: T"

    def test_save_without_tags_passes_empty_list(self, monkeypatch):
        import contextgo.context_cli as context_cli

        captured = {}

        def fake_save(title, content, tags):
            captured["tags"] = tags
            return "ok"

        monkeypatch.setattr(context_cli, "_save_local_memory", fake_save)
        mcp_server._handle_tool_call("contextgo_save", {"title": "T", "content": "C"})
        assert captured["tags"] == []

    def test_save_actually_writes_a_memory(self, tmp_path, monkeypatch):
        """End-to-end: the tool must persist rather than raise."""
        monkeypatch.setenv("CONTEXTGO_STORAGE_ROOT", str(tmp_path / "cg"))
        result = mcp_server._handle_tool_call(
            "contextgo_save", {"title": "Cross machine memory", "content": "body", "tags": "x"}
        )
        assert result.startswith("Saved locally:")

    def test_server_version_is_not_hardcoded(self):
        version = mcp_server._server_version()
        assert version and version != "0.14.1"

    def test_unknown_tool(self):
        assert mcp_server._handle_tool_call("nope", {}) == "Unknown tool: 'nope'"


class TestJsonRpcEmitters:
    def _capture(self, fn):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            fn()
        return buffer.getvalue()

    def test_send_response_writes_json_line(self):
        raw = self._capture(lambda: mcp_server._send_response(7, {"ok": True}))
        assert json.loads(raw.strip()) == {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}

    def test_send_error_writes_json_line(self):
        raw = self._capture(lambda: mcp_server._send_error(9, -32601, "method not found"))
        payload = json.loads(raw.strip())
        assert payload["error"]["code"] == -32601
        assert payload["id"] == 9
        assert payload["jsonrpc"] == "2.0"

    def test_send_response_handles_null_id(self):
        raw = self._capture(lambda: mcp_server._send_response(None, {}))
        assert json.loads(raw.strip())["id"] is None


class TestStdioLoop:
    """Drive the JSON-RPC loop end to end with a scripted stdin transcript."""

    def _run(self, lines, monkeypatch, tmp_path, tool_call=None):
        import contextlib as _cl

        stdin = io.StringIO("".join(line + "\n" for line in lines))
        stdout = io.StringIO()
        monkeypatch.setattr(mcp_server.sys, "stdin", stdin)
        monkeypatch.setattr(mcp_server.sys, "stdout", stdout)
        if tool_call is not None:
            monkeypatch.setattr(mcp_server, "_handle_tool_call", tool_call)
        with _cl.redirect_stderr(io.StringIO()):
            rc = mcp_server.run_mcp_stdio_server()
        return rc, [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]

    def test_full_transcript(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CONTEXTGO_STORAGE_ROOT", str(tmp_path / "cg"))
        lines = [
            "",  # blank line is ignored
            "not-json",  # -> parse error
            "[1,2,3]",  # -> invalid request (not an object)
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "contextgo_search", "arguments": {"query": "q"}},
                }
            ),
            json.dumps({"jsonrpc": "2.0", "id": 5, "method": "no/such/method"}),
        ]
        rc, responses = self._run(lines, monkeypatch, tmp_path)
        assert rc == 0
        by_id = {r.get("id"): r for r in responses if r.get("id") is not None}
        # Both malformed inputs answer with a null id, so collect their codes.
        null_id_codes = sorted(r["error"]["code"] for r in responses if r.get("id") is None and "error" in r)
        assert null_id_codes == [-32700, -32600]
        assert by_id[1]["result"]["serverInfo"]["name"] == "contextgo"
        assert by_id[2]["result"] == {}
        assert [t["name"] for t in by_id[3]["result"]["tools"]]
        assert by_id[4]["result"]["isError"] is False
        assert by_id[5]["error"]["code"] == -32601

    def test_invalid_request_object_reports_minus_32600(self, monkeypatch, tmp_path):
        lines = ["123"]  # parses as a scalar, not a dict
        _, responses = self._run(lines, monkeypatch, tmp_path)
        assert responses[0]["error"]["code"] == -32600

    def test_tool_exception_is_reported_as_iserror(self, monkeypatch, tmp_path):
        def boom(name, arguments):
            raise RuntimeError("kaboom")

        lines = [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "contextgo_save", "arguments": {}},
                }
            )
        ]
        _, responses = self._run(lines, monkeypatch, tmp_path, tool_call=boom)
        assert responses[0]["result"]["isError"] is True
        assert "kaboom" in responses[0]["result"]["content"][0]["text"]

    def test_loop_survives_unexpected_iterator_error(self, monkeypatch, tmp_path):
        class Exploding:
            def __init__(self):
                self.calls = 0

            def readline(self):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
                raise OSError("sudden pipe death")

            def reconfigure(self, **_kw):
                return None

        stdout = io.StringIO()
        monkeypatch.setattr(mcp_server.sys, "stdin", Exploding())
        monkeypatch.setattr(mcp_server.sys, "stdout", stdout)
        import contextlib as _cl

        with _cl.redirect_stderr(io.StringIO()):
            rc = mcp_server.run_mcp_stdio_server()
        assert rc == 0
        assert json.loads(stdout.getvalue().strip())["id"] == 1

    def test_keyboard_interrupt_exits_cleanly(self, monkeypatch, tmp_path):
        class Interrupting:
            def readline(self):
                raise KeyboardInterrupt

            def reconfigure(self, **_kw):
                return None

        monkeypatch.setattr(mcp_server.sys, "stdin", Interrupting())
        monkeypatch.setattr(mcp_server.sys, "stdout", io.StringIO())
        assert mcp_server.run_mcp_stdio_server() == 0
