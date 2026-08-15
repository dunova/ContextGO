"""Unit tests for ContextGO MCP (Model Context Protocol) server."""

import io
import json
import unittest
from unittest import mock

from contextgo import mcp_server


class TestMCPServer(unittest.TestCase):
    """Test MCP protocol handling and tool execution."""

    def test_mcp_tools_list_and_schema(self) -> None:
        self.assertGreaterEqual(len(mcp_server._TOOLS), 4)
        tool_names = {t["name"] for t in mcp_server._TOOLS}
        self.assertIn("contextgo_recall", tool_names)
        self.assertIn("contextgo_search", tool_names)
        self.assertIn("contextgo_semantic", tool_names)
        self.assertIn("contextgo_save", tool_names)

    def test_mcp_initialize_and_ping(self) -> None:
        input_data = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})
            + "\n"
        )
        fake_stdin = io.StringIO(input_data)
        fake_stdout = io.StringIO()

        with mock.patch("sys.stdin", fake_stdin), mock.patch("sys.stdout", fake_stdout):
            ret = mcp_server.run_mcp_stdio_server()

        self.assertEqual(ret, 0)
        output_lines = [json.loads(line) for line in fake_stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(output_lines), 2)
        self.assertEqual(output_lines[0]["id"], 1)
        self.assertEqual(output_lines[0]["result"]["serverInfo"]["name"], "contextgo")
        self.assertEqual(output_lines[1]["id"], 2)

    def test_mcp_tools_call(self) -> None:
        input_data = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {"name": "contextgo_recall", "arguments": {"query": "test query", "limit": 2}},
                }
            )
            + "\n"
        )
        fake_stdin = io.StringIO(input_data)
        fake_stdout = io.StringIO()

        with mock.patch("sys.stdin", fake_stdin), mock.patch("sys.stdout", fake_stdout):
            with mock.patch(
                "contextgo.session_index.format_search_results",
                return_value="Found 1 session(s):\n[1] 2026-08-15 | Test Session (deepseek_session)",
            ):
                ret = mcp_server.run_mcp_stdio_server()

        self.assertEqual(ret, 0)
        output_lines = [json.loads(line) for line in fake_stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(output_lines), 1)
        self.assertEqual(output_lines[0]["id"], 10)
        self.assertFalse(output_lines[0]["result"]["isError"])
        self.assertIn("Test Session", output_lines[0]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
