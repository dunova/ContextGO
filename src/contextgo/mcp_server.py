"""Model Context Protocol (MCP) Server for ContextGO.

Provides a standard JSON-RPC 2.0 stdio server compatible with the MCP specification,
enabling native Tool Calling / Function Calling for DeepSeek Agent (dsh),
Claude Code, Cursor, Windsurf, OpenCode, and any MCP-compliant client.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from contextgo import context_core, memory_index, session_index

_logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "contextgo"
SERVER_VERSION = "0.14.0"

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "contextgo_recall",
        "description": "Fast hybrid recall for cross-agent technical history, session context, and past decisions. Recommended for quick context lookups.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic, keywords, or error description to recall from memory and sessions.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "contextgo_search",
        "description": "Full-text lexical search over all indexed AI coding sessions (DeepSeek, Reasonix, Hermes, Claude Code, Factory, Copilot, Cursor, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Literal keywords, error strings, function names, or file paths.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "contextgo_semantic",
        "description": "Semantic search prioritizing durable architectural decisions and root causes, with fallback to historical sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Conceptual question, architecture topic, or design rationale.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 3).",
                    "default": 3,
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "contextgo_save",
        "description": "Save a durable architectural decision, confirmed bug root cause, or cross-session handoff memory to ContextGO.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Concise summary title (e.g. 'Decision: ...' or 'Bug: ...').",
                },
                "content": {
                    "type": "string",
                    "description": "Detailed explanation, root cause analysis, or technical implementation notes.",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags (e.g. 'architecture,router,deepseek').",
                    "default": "",
                },
            },
            "required": ["title", "content"],
        },
    },
]


def _handle_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool and return markdown-formatted result text."""
    if name == "contextgo_recall" or name == "contextgo_search":
        query = str(arguments.get("query", "")).strip()
        limit = max(1, min(20, int(arguments.get("limit", 5) or 5)))
        if not query:
            return "No search query provided."
        res_text = session_index.format_search_results(query, limit=limit)
        return res_text or f"No sessions found matching: '{query}'"

    if name == "contextgo_semantic":
        topic = str(arguments.get("topic", "")).strip()
        limit = max(1, min(10, int(arguments.get("limit", 3) or 3)))
        if not topic:
            return "No topic provided."
        memories = memory_index.search_index(topic, limit=limit)
        lines = []
        if memories:
            lines.append(f"Durable Memories for '{topic}':")
            for idx, m in enumerate(memories, 1):
                title = m.get("title", "") or m.get("text", "")[:60]
                content = m.get("text", "") or m.get("snippet", "")
                lines.append(f"[{idx}] {title}\n{content}")
        # If memories are fewer than limit, supplement with session results
        if len(memories) < limit:
            rem = limit - len(memories)
            sess_text = session_index.format_search_results(topic, limit=rem)
            if sess_text and not sess_text.startswith("No matches found"):
                lines.append(f"\nRelated Sessions for '{topic}':\n{sess_text}")
        if not lines:
            return f"No memories or sessions found for: '{topic}'"
        return "\n\n".join(lines)

    if name == "contextgo_save":
        title = str(arguments.get("title", "")).strip()
        content = str(arguments.get("content", "")).strip()
        tags = str(arguments.get("tags", "")).strip()
        if not title or not content:
            return "Error: Both 'title' and 'content' are required."
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        context_core.save_memory(title=title, content=content, tags=tag_list)
        return f"Successfully saved durable memory: '{title}'"

    return f"Unknown tool: '{name}'"


def run_mcp_stdio_server() -> int:
    """Run standard JSON-RPC 2.0 loop on stdin / stdout."""
    # Ensure stdout writes are unbuffered and utf-8 where supported
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            raw = line.strip()
            if not raw:
                continue

            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                _send_error(None, -32700, "Parse error")
                continue

            if not isinstance(req, dict):
                _send_error(None, -32600, "Invalid Request")
                continue

            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params") or {}

            # Handle notifications (no id)
            if req_id is None:
                if method == "notifications/initialized":
                    pass
                continue

            if method == "initialize":
                _send_response(
                    req_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {},
                        },
                        "serverInfo": {
                            "name": SERVER_NAME,
                            "version": SERVER_VERSION,
                        },
                    },
                )
            elif method == "ping":
                _send_response(req_id, {})
            elif method == "tools/list":
                _send_response(req_id, {"tools": _TOOLS})
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments") or {}
                try:
                    result_text = _handle_tool_call(tool_name, arguments)
                    _send_response(
                        req_id,
                        {
                            "content": [
                                {
                                    "type": "text",
                                    "text": result_text,
                                }
                            ],
                            "isError": False,
                        },
                    )
                except Exception as exc:
                    _send_response(
                        req_id,
                        {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Tool execution failed: {exc}",
                                }
                            ],
                            "isError": True,
                        },
                    )
            else:
                _send_error(req_id, -32601, f"Method not found: {method}")

        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as exc:
            _logger.exception("MCP server unhandled error: %s", exc)

    return 0


def _send_response(req_id: Any, result: dict[str, Any]) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _send_error(req_id: Any, code: int, message: str) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
