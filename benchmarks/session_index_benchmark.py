#!/usr/bin/env python3
"""Legacy wrapper that runs the bench harness in native mode for compatibility."""

from __future__ import annotations

from benchmarks import run


def main() -> int:
    return run.main(["--mode", "native", "--format", "json"])


if __name__ == "__main__":
    raise SystemExit(main())
