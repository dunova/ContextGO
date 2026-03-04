# Upstream Sync Audit (2026-03-05)

## Snapshot

| Project | Upstream HEAD (checked) | Status |
|---|---|---|
| OpenViking | `079efd1177496561472ee95973f148771fa6d461` | reachable |
| GSD (`get-shit-done`) | `2eaed7a8475839958f9ec76ca4c26d9a0bbfc33f` | reachable |
| OneContext (`TheAgentContextLab/OneContext`) | N/A | repository unavailable (404) |
| OneContext mirror (`dunova/OneContext`) | `1ad765a01e1436a09e12b71f308dd38a53940a17` | reachable |

## Upstream Bugfix Notes Considered

1. OpenViking
   - Recent fixes include install/runtime robustness and resource path handling.
   - This integration is most sensitive to install reliability and API compatibility.

2. GSD
   - Recent fixes include non-default config path handling (`CLAUDE_CONFIG_DIR`) and workflow/hook robustness.
   - This integration is most sensitive to runtime path resolution in workflow snippets.

3. OneContext
   - Original upstream repository is currently unavailable.
   - Integration now documents and supports mirror/fallback paths for local DB detection.

## Changes Integrated in This Repo

1. `scripts/start_openviking.sh`
   - Added pip-upgrade retry fallback when `pip install openviking` fails once.

2. `integrations/gsd/workflows/health.md`
   - Added `CLAUDE_CONFIG_DIR`-aware GSD path resolution in both health check blocks.

3. `scripts/openviking_mcp.py`
   - Added OneContext DB auto-detection fallback chain:
     - `ONECONTEXT_DB_PATH`
     - `~/.aline/db/aline.db`
     - `~/.onecontext/history.db`

4. `scripts/context_healthcheck.sh`
   - Added OneContext DB auto-detection fallback chain (same as above).

5. `scripts/unified_context_deploy.sh`
   - Launchd patch now injects low-power defaults for daemon.
   - Healthcheck LaunchAgent patch now enforces MCP single-process trimming env vars.

6. Documentation
   - Updated README OneContext upstream references to active mirror context.
   - Added env var docs for `ONECONTEXT_DB_PATH`.

