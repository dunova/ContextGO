# ContextGO 0.13.0

ContextGO 0.13.0 is a cross-platform overhaul focused on Windows support, privacy-first multi-machine synchronization, and release-grade verification.

## Highlights

- Unified Windows, macOS, and Linux runtime handling for user directories, configuration, caches, atomic writes, PID state, and per-user services.
- Added explicit GitHub Contents synchronization with scrypt-derived keys, AES-256-GCM encryption, compressed per-device shards, public non-secret manifests, idempotent imports, and fail-closed salt conflict detection.
- Added `contextgo sync init|status|pull|push|run|disable` and `contextgo daemon run|start|stop|status|install|uninstall`.
- Added Windows AppData discovery for supported coding-agent stores and replaced hard-coded `python3` subprocess assumptions with the active Python interpreter.
- Added local-first daemon synchronization with exponential backoff so remote failures do not block local capture, indexing, search, or shutdown.
- Strengthened portable export and sync privacy handling by removing known secrets and Windows/macOS/Linux absolute paths before encryption.
- Expanded CI to Windows, macOS, and Linux runtime contracts, Python 3.10-3.13, Rust, Go, E2E, smoke, security, and wheel installation checks.
- Fixed a vector-cache lock re-entry deadlock and made vector test fixtures offline-safe.

## Upgrade

```bash
pipx upgrade "contextgo[sync,vector]"
contextgo health
contextgo sources
```

Existing `~/.contextgo` data remains readable. Synchronization stays disabled unless `contextgo sync init` is explicitly completed.

## Verification

The release candidate passed on Windows 10 with:

- 1483 tests passed, 8 skipped
- 86.28% branch coverage, meeting the 86% project gate
- Ruff, mypy, Bandit, E2E quality gate, sandbox smoke, wheel build, and installed module CLI checks

## Documentation

- [English README](../README.md)
- [Chinese README](../README.zh.md)
- [Migration guide](MIGRATION.md)
- [Configuration](CONFIGURATION.md)
- [Troubleshooting](TROUBLESHOOTING.md)
