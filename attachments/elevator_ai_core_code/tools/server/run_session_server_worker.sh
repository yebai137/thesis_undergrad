#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  run_session_server_worker.sh [options]

Options:
  --repo-root <path>      Repo root. Default: script-relative repo root
  --session <id|latest|all>
                          Session filter. Default: env SESSION_FILTER or all
  --interval <seconds>    Poll interval in watch mode. Default: env POLL_INTERVAL or 15
  --model <name>          Codex model. Default: env CODEX_MODEL or gpt-5.4
  --sandbox <mode>        Codex sandbox. Default: env SANDBOX_MODE or workspace-write
  --once                  Process at most one ready session, then exit
  --watch                 Watch continuously (default)
  --help                  Show this help

Environment:
  SESSION_FILTER          Default session selector
  POLL_INTERVAL           Default poll interval
  CODEX_MODEL             Default model
  SANDBOX_MODE            Default sandbox mode
EOF
}

log() {
    printf '[session-server-worker] %s\n' "$*" >&2
}

find_codex_executable() {
    local candidate=""
    local pattern=""

    if candidate=$(command -v codex 2>/dev/null); then
        printf '%s\n' "$candidate"
        return 0
    fi

    for pattern in \
        "$HOME/.vscode-server/extensions/openai.chatgpt-*-linux-x64/bin/linux-x86_64/codex" \
        "$HOME/.vscode/extensions/openai.chatgpt-*-linux-x64/bin/linux-x86_64/codex"
    do
        candidate=$(compgen -G "$pattern" | sort -V | tail -n 1 || true)
        if [[ -n "$candidate" && -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    if [[ -x "$HOME/.codex/bin/codex" ]]; then
        printf '%s\n' "$HOME/.codex/bin/codex"
        return 0
    fi

    return 1
}

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)
session_filter="${SESSION_FILTER:-all}"
poll_interval="${POLL_INTERVAL:-15}"
codex_model="${CODEX_MODEL:-gpt-5.4}"
sandbox_mode="${SANDBOX_MODE:-workspace-write}"
watch_mode=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-root)
            repo_root="${2:-}"
            shift 2
            ;;
        --session)
            session_filter="${2:-}"
            shift 2
            ;;
        --interval)
            poll_interval="${2:-}"
            shift 2
            ;;
        --model)
            codex_model="${2:-}"
            shift 2
            ;;
        --sandbox)
            sandbox_mode="${2:-}"
            shift 2
            ;;
        --once)
            watch_mode=0
            shift
            ;;
        --watch)
            watch_mode=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

sessions_dir="$repo_root/logs/sessions"
if [[ ! -d "$sessions_dir" ]]; then
    printf 'Error: sessions directory not found: %s\n' "$sessions_dir" >&2
    exit 1
fi

declare -A last_signature

latest_session_id() {
    find "$sessions_dir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail -n 1
}

list_session_ids() {
    case "$session_filter" in
        all)
            find "$sessions_dir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
            ;;
        latest)
            latest_session_id
            ;;
        *)
            printf '%s\n' "$session_filter"
            ;;
    esac
}

session_status() {
    local session_dir="$1"
    local status_path="$session_dir/status.txt"

    if [[ ! -f "$status_path" ]]; then
        return 1
    fi

    sed -n '1p' "$status_path" | tr -d '\r'
}

session_signature() {
    local session_dir="$1"
    local file_path

    for name in status.txt server_to_windows.md windows_to_server.md notes.md; do
        file_path="$session_dir/$name"
        if [[ -f "$file_path" ]]; then
            stat -c '%n:%Y:%s' "$file_path"
        fi
    done | sha1sum | awk '{print $1}'
}

run_session() {
    local session_id="$1"
    local session_dir="$sessions_dir/$session_id"
    local automation_dir="$session_dir/.automation"
    local lock_dir="$automation_dir/server_worker.lock"
    local prompt_path="$automation_dir/server_worker_prompt.txt"
    local jsonl_path="$automation_dir/server_worker_exec.jsonl"
    local last_message_path="$automation_dir/server_worker_last_message.txt"
    local stderr_path="$automation_dir/server_worker_stderr.txt"
    local run_summary_path="$automation_dir/server_worker_run.txt"
    local started_at
    local finished_at
    local status_before
    local status_after
    local rc=0
    local codex_executable=""
    local -a codex_cmd

    status_before=$(session_status "$session_dir" || printf 'missing')
    if [[ "$status_before" != "waiting_server" ]]; then
        return 0
    fi

    mkdir -p "$automation_dir"
    if ! mkdir "$lock_dir" 2>/dev/null; then
        log "session $session_id is already locked; skipping"
        return 0
    fi

    started_at=$(date -Iseconds)

    cat > "$prompt_path" <<EOF
You are the server-side Codex worker for the elevator_ai dual-Codex session workflow.

Session id: $session_id
Session directory: $session_dir
Repository root: $repo_root

Read and use these files as the current source of truth:
- $session_dir/server_to_windows.md
- $session_dir/windows_to_server.md
- $session_dir/status.txt
- $session_dir/notes.md
- Any evidence under $session_dir/artifacts/

Your job is to process this session only if status.txt currently says waiting_server.

What you should do:
1. Analyze the newest evidence for this session.
2. Make any needed repo changes, tests, packaging, metrics merging, or session-file updates.
3. Advance the same session to exactly one of:
   - waiting_windows: another Windows-side iteration is needed
   - blocked: an external physical action or truly missing information is required
   - done: the session is complete

Rules:
- Stay within this existing session. Do not create a new session.
- If another Windows iteration is needed, update server_to_windows.md, notes.md, and status.txt.
- If the evidence already validates a stable path, close the session cleanly with status.txt=done and summarize the conclusion in notes.md.
- Do not wait for user input; make reasonable assumptions.
- Do not tell the user to manually relay anything; operate entirely through the session files.
EOF

    if ! codex_executable=$(find_codex_executable); then
        printf 'Unable to find codex executable in PATH or bundled extension locations.\n' >"$stderr_path"
        rc=127
    else
        codex_cmd=("$codex_executable" exec -C "$repo_root" --sandbox "$sandbox_mode" -c 'approval_policy="never"' --json -o "$last_message_path")
        if [[ -n "$codex_model" ]]; then
            codex_cmd+=(-m "$codex_model")
        fi

        if "${codex_cmd[@]}" <"$prompt_path" >"$jsonl_path" 2>"$stderr_path"; then
            rc=0
        else
            rc=$?
        fi
    fi

    finished_at=$(date -Iseconds)
    status_after=$(session_status "$session_dir" || printf 'missing')
    cat > "$run_summary_path" <<EOF
session_id=$session_id
started_at=$started_at
finished_at=$finished_at
codex_executable=$codex_executable
exit_code=$rc
status_before=$status_before
status_after=$status_after
jsonl_path=$jsonl_path
stderr_path=$stderr_path
last_message_path=$last_message_path
EOF

    rm -rf "$lock_dir"
    log "processed $session_id: exit_code=$rc status_before=$status_before status_after=$status_after"
    return "$rc"
}

scan_once() {
    local session_id
    local session_dir
    local signature
    local status

    while IFS= read -r session_id; do
        [[ -z "$session_id" ]] && continue
        session_dir="$sessions_dir/$session_id"
        [[ -d "$session_dir" ]] || continue

        status=$(session_status "$session_dir" || printf '')
        [[ "$status" == "waiting_server" ]] || continue

        signature=$(session_signature "$session_dir")
        if [[ "${last_signature[$session_id]-}" == "$signature" ]]; then
            continue
        fi

        run_session "$session_id" || true
        last_signature["$session_id"]=$(session_signature "$session_dir")
        return 0
    done < <(list_session_ids)

    return 1
}

scan_once || true

if [[ "$watch_mode" -eq 0 ]]; then
    exit 0
fi

log "watching $sessions_dir every ${poll_interval}s for waiting_server sessions"
while true; do
    sleep "$poll_interval"
    scan_once || true
done
