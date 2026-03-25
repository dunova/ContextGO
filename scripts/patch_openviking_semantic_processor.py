#!/usr/bin/env python3
"""Legacy wrapper for archived OpenViking semantic patch helper."""

try:
    import legacy.patch_openviking_semantic_processor as _legacy
except ImportError:  # pragma: no cover
    from .legacy import patch_openviking_semantic_processor as _legacy  # type: ignore[import-not-found]


def main() -> int:
    if hasattr(_legacy, "main"):
        return int(_legacy.main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
