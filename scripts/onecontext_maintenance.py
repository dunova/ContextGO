#!/usr/bin/env python3
"""Legacy compatibility wrapper for maintenance logic."""

from legacy.onecontext_maintenance import *  # noqa: F401,F403


if __name__ == "__main__":
    raise SystemExit(main())
