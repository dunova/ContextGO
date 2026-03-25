#!/usr/bin/env python3
"""Canonical daemon entrypoint."""

try:
    from viking_daemon import *  # noqa: F401,F403
except ImportError:  # pragma: no cover
    from .viking_daemon import *  # type: ignore[import-not-found] # noqa: F401,F403


if __name__ == "__main__":
    main()
