#!/usr/bin/env python3
"""Archived legacy MCP bridge stub.

The standalone Context Mesh runtime no longer uses MCP. This module remains only
to keep old imports and shell paths from crashing hard during migration.
"""

from __future__ import annotations

import json


class _NoopMCP:
    @staticmethod
    def tool(*_args, **_kwargs):
        def _decorator(func):
            return func

        return _decorator

    @staticmethod
    def run(*_args, **_kwargs):
        print("Legacy MCP bridge is archived. Use `python3 scripts/context_cli.py` instead.")
        return None


mcp = _NoopMCP()


def _disabled_message() -> str:
    return "Legacy MCP bridge is archived. Use `python3 scripts/context_cli.py` for standalone local search."


@mcp.tool()
def save_conversation_memory(*_args, **_kwargs) -> str:
    return _disabled_message()


@mcp.tool()
def query_viking_memory(*_args, **_kwargs) -> str:
    return _disabled_message()


@mcp.tool()
def search_onecontext_history(*_args, **_kwargs) -> str:
    return _disabled_message()


@mcp.tool()
def context_system_health() -> str:
    payload = {
        "mode": "archived-legacy-bridge",
        "all_ok": True,
        "message": _disabled_message(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> int:
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
