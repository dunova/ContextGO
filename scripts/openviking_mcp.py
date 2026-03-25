#!/usr/bin/env python3
"""Legacy wrapper for the archived OpenViking MCP bridge."""

try:
    from legacy.openviking_mcp import *  # noqa: F401,F403
    import legacy.openviking_mcp as _legacy
except ImportError:  # pragma: no cover
    from .legacy.openviking_mcp import *  # type: ignore[import-not-found] # noqa: F401,F403
    from .legacy import openviking_mcp as _legacy  # type: ignore[import-not-found]


if __name__ == "__main__":
    if hasattr(_legacy, "mcp"):
        _legacy.mcp.run(transport="stdio")
    elif hasattr(_legacy, "main"):
        raise SystemExit(_legacy.main())
    else:
        import sys
        print("Legacy bridge not runnable.", file=sys.stderr)
        raise SystemExit(1)
