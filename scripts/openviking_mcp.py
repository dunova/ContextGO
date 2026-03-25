#!/usr/bin/env python3
"""Legacy wrapper for the archived OpenViking MCP bridge."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


LEGACY_PATH = Path(__file__).resolve().parent / "legacy" / "openviking_mcp.py"


def _load_legacy():
    spec = spec_from_file_location("legacy_openviking_mcp", LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load legacy module: {LEGACY_PATH}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_legacy = _load_legacy()
globals().update({k: v for k, v in _legacy.__dict__.items() if not k.startswith("__")})


if __name__ == "__main__":
    if hasattr(_legacy, "mcp"):
        _legacy.mcp.run(transport="stdio")
    elif hasattr(_legacy, "main"):
        raise SystemExit(_legacy.main())
    else:
        print(f"Legacy bridge not runnable: {LEGACY_PATH}", file=sys.stderr)
        raise SystemExit(1)
