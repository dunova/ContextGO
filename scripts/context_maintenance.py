#!/usr/bin/env python3
"""Canonical maintenance entrypoint."""

try:
    from legacy.onecontext_maintenance import *  # noqa: F401,F403
except ImportError:  # pragma: no cover
    from .legacy.onecontext_maintenance import *  # type: ignore[import-not-found] # noqa: F401,F403


if __name__ == "__main__":
    raise SystemExit(main())
