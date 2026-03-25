#!/usr/bin/env python3
"""Legacy wrapper for archived OpenViking semantic patch helper."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


LEGACY_PATH = Path(__file__).resolve().parent / "legacy" / "patch_openviking_semantic_processor.py"


def main() -> int:
    spec = spec_from_file_location("legacy_patch_openviking_semantic_processor", LEGACY_PATH)
    if spec is None or spec.loader is None:
        print(f"Cannot load legacy helper: {LEGACY_PATH}", file=sys.stderr)
        return 1
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "main"):
        return int(module.main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
