"""Allow ``python -m contextgo`` to launch the CLI."""

from contextgo.context_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
