#!/bin/bash
# =============================================================================
# Unified Context System Health Check
# onecontext + openviking + gsd bridge runtime checks
# =============================================================================

LOG_DIR="$HOME/.context_system/logs"
HEALTHCHECK_LOG="$LOG_DIR/healthcheck.log"
UNIFIED_CONTEXT_STORAGE_ROOT="${UNIFIED_CONTEXT_STORAGE_ROOT:-${OPENVIKING_STORAGE_ROOT:-$HOME/.unified_context_data}}"
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR" 2>/dev/null || true
PRINT_STDOUT=1
DEEP_PROBE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --quiet) PRINT_STDOUT=0 ;;
        --deep) DEEP_PROBE=1 ;;
    esac
    shift
done

TS=$(date '+%Y-%m-%d %H:%M:%S')
STATUS=0
REPORT=""

file_size_bytes() {
    local p="$1"
    stat -f%z "$p" 2>/dev/null || stat -c%s "$p" 2>/dev/null || echo 0
}

file_perm_mode() {
    local p="$1"
    stat -f%Lp "$p" 2>/dev/null || stat -c%a "$p" 2>/dev/null || echo 000
}

etime_to_seconds() {
    local raw="$1"
    local d h m s
    raw="${raw// /}"
    if [[ "$raw" =~ ^([0-9]+)-([0-9]{1,2}):([0-9]{2}):([0-9]{2})$ ]]; then
        d="${BASH_REMATCH[1]}"
        h="${BASH_REMATCH[2]}"
        m="${BASH_REMATCH[3]}"
        s="${BASH_REMATCH[4]}"
        echo $((10#$d * 86400 + 10#$h * 3600 + 10#$m * 60 + 10#$s))
        return
    fi
    if [[ "$raw" =~ ^([0-9]{1,2}):([0-9]{2}):([0-9]{2})$ ]]; then
        h="${BASH_REMATCH[1]}"
        m="${BASH_REMATCH[2]}"
        s="${BASH_REMATCH[3]}"
        echo $((10#$h * 3600 + 10#$m * 60 + 10#$s))
        return
    fi
    if [[ "$raw" =~ ^([0-9]{1,2}):([0-9]{2})$ ]]; then
        m="${BASH_REMATCH[1]}"
        s="${BASH_REMATCH[2]}"
        echo $((10#$m * 60 + 10#$s))
        return
    fi
    echo 0
}

resolve_onecontext_db() {
    local candidates=(
        "${ONECONTEXT_DB_PATH:-}"
        "$HOME/.aline/db/aline.db"
        "$HOME/.onecontext/history.db"
    )
    local c
    for c in "${candidates[@]}"; do
        [ -z "$c" ] && continue
        c="${c/#\~/$HOME}"
        if [ -f "$c" ]; then
            echo "$c"
            return
        fi
    done
    for c in "${candidates[@]}"; do
        [ -z "$c" ] && continue
        c="${c/#\~/$HOME}"
        echo "$c"
        return
    done
    echo "$HOME/.aline/db/aline.db"
}

check_process() {
    local name="$1"
    local pattern="$2"
    if pgrep -f "$pattern" > /dev/null 2>&1; then
        REPORT+="  ✅ $name: running (PID $(pgrep -f "$pattern" | head -1))\n"
    else
        REPORT+="  ❌ $name: NOT RUNNING\n"
        STATUS=1
    fi
}

get_launchd_pid() {
    local label="$1"
    local uid_num
    uid_num="$(id -u)"
    launchctl print "gui/${uid_num}/${label}" 2>/dev/null | awk -F'= ' '/^[[:space:]]*pid = / {print $2; exit}'
}

dedupe_process_keep_launchd() {
    local display_name="$1"
    local pattern="$2"
    local launchd_label="$3"
    local keep_pid pids pid_count removed

    keep_pid="$(get_launchd_pid "$launchd_label" | tr -d '[:space:]')"
    pids="$(pgrep -f "$pattern" 2>/dev/null || true)"
    pid_count="$(echo "$pids" | awk 'NF' | wc -l | tr -d ' ')"
    [ -z "$pid_count" ] && pid_count=0

    if [ "$pid_count" -le 1 ]; then
        return 0
    fi

    if [ -z "$keep_pid" ]; then
        keep_pid="$(echo "$pids" | awk 'NF{print; exit}')"
    fi

    removed=0
    while IFS= read -r pid; do
        [ -z "$pid" ] && continue
        if [ "$pid" = "$keep_pid" ]; then
            continue
        fi
        kill "$pid" >/dev/null 2>&1 || true
        sleep 0.2
        if kill -0 "$pid" >/dev/null 2>&1; then
            kill -9 "$pid" >/dev/null 2>&1 || true
        fi
        removed=$((removed + 1))
    done <<< "$pids"

    if [ "$removed" -gt 0 ]; then
        REPORT+="  ⚠️  dedupe $display_name: found=$pid_count kept=$keep_pid removed=$removed\n"
    fi
}

prune_stale_openviking_mcp() {
    local max_instances stale_sec pids pid_count removed force_trim
    max_instances="${OPENVIKING_MCP_MAX_PROCS:-1}"
    stale_sec="${OPENVIKING_MCP_STALE_SEC:-7200}"
    force_trim="${OPENVIKING_MCP_FORCE_TRIM:-0}"
    pids="$(pgrep -f "openviking_mcp.py" 2>/dev/null || true)"
    pid_count="$(echo "$pids" | awk 'NF' | wc -l | tr -d ' ')"
    [ -z "$pid_count" ] && pid_count=0

    if [ "$pid_count" -eq 0 ]; then
        REPORT+="  ✅ openviking-mcp: no running process\n"
        return 0
    fi

    REPORT+="  ✅ openviking-mcp: instances=$pid_count\n"
    if [ "$pid_count" -le "$max_instances" ]; then
        return 0
    fi
    if [ "$pid_count" -gt $((max_instances * 2)) ]; then
        force_trim=1
    fi

    removed=0
    while read -r pid age_sec; do
        [ -z "$pid" ] && continue
        [ -z "$age_sec" ] && continue
        if ! [[ "$age_sec" =~ ^[0-9]+$ ]]; then
            continue
        fi
        if [ "$pid_count" -le "$max_instances" ]; then
            break
        fi
        if [ "$force_trim" != "1" ] && [ "$age_sec" -lt "$stale_sec" ]; then
            continue
        fi
        kill "$pid" >/dev/null 2>&1 || true
        sleep 0.2
        if kill -0 "$pid" >/dev/null 2>&1; then
            kill -9 "$pid" >/dev/null 2>&1 || true
        fi
        removed=$((removed + 1))
        pid_count=$((pid_count - 1))
    done < <(
        ps -ax -o pid=,etime=,command= 2>/dev/null \
          | awk '/openviking_mcp.py/ && !/awk/ {print $1" "$2}' \
          | while read -r pid etime; do
                [ -z "$pid" ] && continue
                [ -z "$etime" ] && continue
                age_sec="$(etime_to_seconds "$etime")"
                echo "$pid $age_sec"
            done \
          | sort -k2 -nr
    )

    if [ "$removed" -gt 0 ]; then
        if [ "$force_trim" = "1" ]; then
            REPORT+="  ⚠️  openviking-mcp prune: removed=$removed keep_limit=$max_instances force_trim=1\n"
        else
            REPORT+="  ⚠️  openviking-mcp prune: removed=$removed keep_limit=$max_instances stale>=${stale_sec}s\n"
        fi
    fi
    if [ "$pid_count" -gt "$max_instances" ]; then
        REPORT+="  ⚠️  openviking-mcp pressure: current=$pid_count limit=$max_instances (all active)\n"
    fi
}

check_openviking_api() {
    local http_status
    local deep_status=""
    http_status=$(curl -s -o /dev/null -w "%{http_code}" \
      "http://127.0.0.1:8090/health" \
      --max-time 6 2>/dev/null || true)
    http_status="${http_status: -3}"
    [ -z "$http_status" ] && http_status="000"

    if [ "$DEEP_PROBE" = "1" ] || [ "$http_status" != "200" ]; then
        # Deep probe verifies core search endpoint in addition to /health.
        deep_status=$(curl -s -o /dev/null -w "%{http_code}" \
          -X POST "http://127.0.0.1:8090/api/v1/search/find" \
          -H "Content-Type: application/json" \
          -d '{"query":"__healthcheck__","target_uri":"viking://resources","limit":1}' \
          --max-time 15 2>/dev/null || true)
        deep_status="${deep_status: -3}"
        [ -z "$deep_status" ] && deep_status="000"
        if [ "$http_status" != "200" ]; then
            http_status="$deep_status"
        fi
    fi

    if [ "$http_status" = "200" ]; then
        REPORT+="  ✅ openviking-api: HTTP 200\n"
        if [ "$DEEP_PROBE" = "1" ]; then
            if [ "$deep_status" = "200" ]; then
                REPORT+="  ✅ openviking-deep-probe: HTTP 200\n"
            else
                REPORT+="  ❌ openviking-deep-probe: HTTP ${deep_status:-000}\n"
                STATUS=1
            fi
        fi
    else
        REPORT+="  ❌ openviking-api: HTTP $http_status\n"
        STATUS=1
    fi
}

check_onecontext() {
    local rc=127
    local cli_name=""
    local cli_output=""
    if command -v onecontext >/dev/null 2>&1; then
        cli_name="onecontext"
        set +e
        cli_output="$(onecontext search "healthcheck" -t all -l 1 2>&1)"
        rc=$?
        set -e
    elif command -v aline >/dev/null 2>&1; then
        cli_name="aline"
        set +e
        cli_output="$(aline search "healthcheck" -t all -l 1 2>&1)"
        rc=$?
        set -e
    fi

    if [ "$rc" = "0" ]; then
        REPORT+="  ✅ onecontext-search: callable ($cli_name)\n"
    elif [ "$rc" = "127" ]; then
        REPORT+="  ⚠️  onecontext-search: no cli command found\n"
    elif echo "$cli_output" | grep -Eq 'Found 0 matches|No matches found'; then
        REPORT+="  ✅ onecontext-search: callable ($cli_name, no matches)\n"
    else
        REPORT+="  ❌ onecontext-search: error ($cli_name, exit=$rc)\n"
        STATUS=1
    fi
}

check_onecontext_coverage() {
    if ! command -v sqlite3 >/dev/null 2>&1; then
        REPORT+="  ℹ️  onecontext coverage: sqlite3 not found\n"
        return 0
    fi
    local db
    db="$(resolve_onecontext_db)"
    if [ ! -f "$db" ]; then
        REPORT+="  ⚠️  onecontext coverage: DB not found ($db)\n"
        STATUS=1
        return 0
    fi

    local sessions codex claude events llm_err queued_sp processing_sp
    sessions=$(sqlite3 "$db" "SELECT count(*) FROM sessions;" 2>/dev/null || echo "ERR")
    codex=$(sqlite3 "$db" "SELECT count(*) FROM sessions WHERE session_type='codex';" 2>/dev/null || echo "ERR")
    claude=$(sqlite3 "$db" "SELECT count(*) FROM sessions WHERE session_type='claude';" 2>/dev/null || echo "ERR")
    events=$(sqlite3 "$db" "SELECT count(*) FROM events;" 2>/dev/null || echo "ERR")
    llm_err=$(sqlite3 "$db" "SELECT count(*) FROM sessions WHERE session_title LIKE '⚠ LLM API Error%';" 2>/dev/null || echo "ERR")
    queued_sp=$(sqlite3 "$db" "SELECT count(*) FROM jobs WHERE kind='session_process' AND status='queued';" 2>/dev/null || echo "ERR")
    processing_sp=$(sqlite3 "$db" "SELECT count(*) FROM jobs WHERE kind='session_process' AND status='processing';" 2>/dev/null || echo "ERR")

    REPORT+="  ✅ onecontext sessions: total=$sessions codex=$codex claude=$claude events=$events\n"
    REPORT+="  ✅ onecontext queue: session_process queued=$queued_sp processing=$processing_sp\n"
    REPORT+="  ✅ onecontext summary-error sessions: $llm_err\n"

    local codex_local claude_local
    codex_local=$(find "$HOME/.codex/sessions" -type f -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
    claude_local=$(find "$HOME/.claude/projects" -type f -name '*.jsonl' ! -path '*/subagents/*' 2>/dev/null | wc -l | tr -d ' ')
    REPORT+="  ✅ local session files: codex=$codex_local claude_main=$claude_local\n"

    # Coverage check (python for path-level exact diff)
    if command -v python3 >/dev/null 2>&1; then
        local cov
        cov="$(python3 - <<'PY'
from pathlib import Path
import sqlite3, os
db = os.path.expanduser("~/.aline/db/aline.db")
conn = sqlite3.connect(db)
cur = conn.cursor()
db_paths = set(r[0] for r in cur.execute("select session_file_path from sessions where session_file_path is not null"))
conn.close()
codex = [str(p) for p in Path(os.path.expanduser("~/.codex/sessions")).rglob("*.jsonl")]
claude = [str(p) for p in Path(os.path.expanduser("~/.claude/projects")).rglob("*.jsonl") if "/subagents/" not in str(p)]
miss_codex = sum(1 for p in codex if p not in db_paths)
miss_claude = sum(1 for p in claude if p not in db_paths)
print(f"{miss_codex},{miss_claude}")
PY
)"
        local miss_codex miss_claude
        miss_codex="${cov%%,*}"
        miss_claude="${cov##*,}"
        REPORT+="  ✅ onecontext missing files: codex=$miss_codex claude_main=$miss_claude\n"
        if [ "$miss_codex" -gt 0 ] || [ "$miss_claude" -gt 0 ]; then
            REPORT+="  ⚠️  onecontext backlog exists; run run_onecontext_maintenance.sh\n"
            STATUS=1
        fi
    fi
}

check_source_file() {
    local label="$1"
    local path="$2"
    local required="$3"

    if [ -f "$path" ]; then
        REPORT+="  ✅ $label: $path\n"
    else
        if [ "$required" = "1" ]; then
            REPORT+="  ❌ $label missing: $path\n"
            STATUS=1
        else
            REPORT+="  ℹ️  $label not found: $path\n"
        fi
    fi
}

check_log_size() {
    local label="$1"
    local path="$2"
    local max_mb="${3:-100}"
    if [ -f "$path" ]; then
        local size_mb=$(( $(file_size_bytes "$path") / 1048576 ))
        if [ "$size_mb" -gt "$max_mb" ]; then
            REPORT+="  ⚠️  $label: ${size_mb}MB (>${max_mb}MB) – truncating\n"
            local tmpfile
            tmpfile="$(mktemp "${path}.XXXXXX")" || { REPORT+="  ❌ $label: failed to create tmpfile\n"; return; }
            tail -c $((max_mb * 1048576 / 2)) "$path" > "$tmpfile" && mv "$tmpfile" "$path" || rm -f "$tmpfile"
            STATUS=1
        else
            REPORT+="  ✅ $label: ${size_mb}MB\n"
        fi
    fi
}

check_perm_max() {
    local label="$1"
    local path="$2"
    local max_perm="$3"
    local effective_path="$path"
    if [ -L "$path" ]; then
        local target
        target="$(readlink "$path" 2>/dev/null || true)"
        if [ -n "$target" ]; then
            if [[ "$target" = /* ]]; then
                effective_path="$target"
            else
                effective_path="$(cd "$(dirname "$path")" && pwd)/$target"
            fi
        fi
    fi
    if [ ! -f "$effective_path" ]; then
        REPORT+="  ℹ️  $label not found: $effective_path\n"
        return 0
    fi
    local perm
    perm=$(file_perm_mode "$effective_path")
    if [ "$perm" -le "$max_perm" ]; then
        REPORT+="  ✅ $label perms: $perm\n"
    else
        REPORT+="  ⚠️  $label perms too open: $perm (expected <= $max_perm)\n"
        STATUS=1
    fi
}

check_launchd_job() {
    local label="$1"
    local uid_num
    uid_num="$(id -u)"
    if ! command -v launchctl >/dev/null 2>&1; then
        REPORT+="  ℹ️  launchctl unavailable\n"
        return 0
    fi
    local state
    state=$(launchctl print "gui/${uid_num}/${label}" 2>/dev/null | awk -F'= ' '/^[[:space:]]*state = / {print $2; exit}')
    if [ -z "$state" ]; then
        REPORT+="  ❌ launchd $label: missing\n"
        STATUS=1
        return 0
    fi
    if [ "$label" = "com.context.healthcheck" ] && [ "$state" = "not running" ]; then
        REPORT+="  ✅ launchd $label: loaded ($state)\n"
        return 0
    fi
    if [ "$state" = "running" ] || [ "$state" = "spawn scheduled" ]; then
        REPORT+="  ✅ launchd $label: $state\n"
    else
        REPORT+="  ⚠️  launchd $label: $state\n"
        STATUS=1
    fi
}

REPORT+="[$TS] Context System Health Check\n"
REPORT+="─────────────────────────────────\n"
REPORT+="Processes:\n"

dedupe_process_keep_launchd "aline-watcher" "realign.watcher_daemon" "com.aline.watcher"
dedupe_process_keep_launchd "aline-worker" "realign.worker_daemon" "com.aline.worker"
check_process "viking_daemon" "viking_daemon.py"
check_process "openviking-server" "openviking-server|openviking.server.bootstrap"
check_process "aline-watcher" "realign.watcher_daemon"
check_process "aline-worker" "realign.worker_daemon"
prune_stale_openviking_mcp
check_openviking_api
check_onecontext

REPORT+="\nLaunchd:\n"
check_launchd_job "com.openviking.server"
check_launchd_job "com.openviking.daemon"
check_launchd_job "com.context.healthcheck"

REPORT+="\nSources:\n"
check_source_file "claude-history" "$HOME/.claude/history.jsonl" 0
check_source_file "codex-history" "$HOME/.codex/history.jsonl" 0
check_source_file "opencode-history" "$HOME/.local/state/opencode/prompt-history.jsonl" 0
check_source_file "zsh-history" "$HOME/.zsh_history" 0
check_source_file "bash-history" "$HOME/.bash_history" 0

REPORT+="\nPermissions:\n"
check_perm_max "openviking-config" "$HOME/.openviking_data/ov.conf" 600
check_perm_max "antigravity-secrets" "$HOME/.antigravity_secrets" 600

REPORT+="\nLog Sizes:\n"
check_log_size "viking_daemon" "$LOG_DIR/viking_daemon.log" 50
check_log_size "openviking_server" "$LOG_DIR/openviking_server_launchd.log" 50
check_log_size "aline_watcher" "$HOME/.aline/.logs/watcher_core.log" 100
check_log_size "aline_worker" "$HOME/.aline/.logs/worker_core.log" 100
check_log_size "aline_watcher_stderr" "$HOME/.aline/.logs/watcher_stderr.log" 120
check_log_size "aline_llm" "$HOME/.aline/.logs/llm.log" 120

REPORT+="\nAline DB:\n"
if ! command -v sqlite3 >/dev/null 2>&1; then
    REPORT+="  ℹ️  sqlite3 not found, skipping DB checks\n"
elif [ -f "$HOME/.aline/db/aline.db" ]; then
    RECENT=$(sqlite3 "$HOME/.aline/db/aline.db" "SELECT count(*) FROM sessions WHERE created_at > datetime('now', '-2 hours');" 2>/dev/null || echo "ERR")
    if [ "$RECENT" = "0" ] || [ "$RECENT" = "ERR" ]; then
        REPORT+="  ⚠️  No new sessions in the last 2 hours ($RECENT)\n"
    else
        REPORT+="  ✅ $RECENT sessions in the last 2 hours\n"
    fi
    DB_SIZE=$(( $(file_size_bytes "$HOME/.aline/db/aline.db") / 1048576 ))
    REPORT+="  📦 DB size: ${DB_SIZE}MB\n"
else
    REPORT+="  ⚠️  ~/.aline/db/aline.db missing\n"
fi

REPORT+="\nOneContext Coverage:\n"
check_onecontext_coverage

REPORT+="\nViking Sync:\n"
PENDING_DIR="$UNIFIED_CONTEXT_STORAGE_ROOT/resources/shared/history/.pending"
if [ -d "$PENDING_DIR" ]; then
    PENDING_COUNT=$(ls -1 "$PENDING_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')
    if [ "$PENDING_COUNT" -gt 0 ]; then
        REPORT+="  ⚠️  $PENDING_COUNT pending sync files\n"
    else
        REPORT+="  ✅ No pending sync files\n"
    fi
else
    REPORT+="  ✅ No pending directory\n"
fi

REPORT+="\n"
if [ "$STATUS" -eq 0 ]; then
    REPORT+="🟢 All systems nominal.\n"
else
    REPORT+="🔴 Issues detected – review above.\n"
fi
REPORT+="─────────────────────────────────\n\n"

if [ "$PRINT_STDOUT" = "1" ]; then
    echo -e "$REPORT"
fi
echo -e "$REPORT" >> "$HEALTHCHECK_LOG"

HC_SIZE=$(( $(file_size_bytes "$HEALTHCHECK_LOG") / 1048576 ))
if [ "$HC_SIZE" -gt 5 ]; then
    HC_TMPFILE="$(mktemp "${HEALTHCHECK_LOG}.XXXXXX")" && \
        tail -c 2621440 "$HEALTHCHECK_LOG" > "$HC_TMPFILE" && \
        mv "$HC_TMPFILE" "$HEALTHCHECK_LOG" || \
        rm -f "$HC_TMPFILE" 2>/dev/null
fi

exit $STATUS
