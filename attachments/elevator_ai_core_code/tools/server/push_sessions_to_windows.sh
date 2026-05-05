#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  push_sessions_to_windows.sh --windows-host <host> [options]

Options:
  --windows-host <host>        Windows machine hostname or IP.
  --windows-user <user>        Windows SSH username. Default: <current user>
  --windows-repo-root <path>   Remote repo root. Default: D:/elevator_ai/elevator_ai
  --ssh-port <port>            Windows SSH port. Default: 22
  --identity-file <path>       SSH private key used for non-interactive push.
  --session <id|latest|all>    Session filter. Default: all
  --interval <seconds>         Poll interval in watch mode. Default: 10
  --watch                      Keep syncing when task files change.
  --help                       Show this help text.

Examples:
  push_sessions_to_windows.sh --windows-host 192.168.1.10 --windows-user yebai
  push_sessions_to_windows.sh --windows-host 192.168.1.10 --windows-user yebai --watch
  push_sessions_to_windows.sh --windows-host 192.168.1.10 --windows-user yebai --session latest

Notes:
  1. Windows must enable OpenSSH Server and allow the Linux server to SSH in.
  2. This script syncs runtime session metadata only, not large artifacts.
EOF
}

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)
sessions_dir="$repo_root/logs/sessions"

windows_host=""
windows_user="${USER:-ywj}"
windows_repo_root="D:/elevator_ai/elevator_ai"
ssh_port="22"
identity_file=""
session_filter="all"
interval_seconds=10
watch_mode=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --windows-host)
            windows_host="${2:-}"
            shift 2
            ;;
        --windows-user)
            windows_user="${2:-}"
            shift 2
            ;;
        --windows-repo-root)
            windows_repo_root="${2:-}"
            shift 2
            ;;
        --ssh-port)
            ssh_port="${2:-}"
            shift 2
            ;;
        --identity-file)
            identity_file="${2:-}"
            shift 2
            ;;
        --session)
            session_filter="${2:-}"
            shift 2
            ;;
        --interval)
            interval_seconds="${2:-}"
            shift 2
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

if [[ -z "$windows_host" ]]; then
    printf 'Error: --windows-host is required.\n' >&2
    usage >&2
    exit 1
fi

if [[ ! -d "$sessions_dir" ]]; then
    printf 'Error: sessions directory not found: %s\n' "$sessions_dir" >&2
    exit 1
fi

ssh_base_cmd=(ssh -p "$ssh_port" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5)
scp_base_cmd=(scp -P "$ssh_port" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5)

if [[ -n "$identity_file" ]]; then
    ssh_base_cmd+=(-i "$identity_file")
    scp_base_cmd+=(-i "$identity_file")
fi

declare -A last_signature
metadata_files=("server_to_windows.md" "windows_to_server.md" "status.txt" "notes.md")

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

session_signature() {
    local session_id="$1"
    local session_dir="$sessions_dir/$session_id"
    local file_path

    for name in "${metadata_files[@]}"; do
        file_path="$session_dir/$name"
        if [[ -f "$file_path" ]]; then
            stat -c '%n:%Y:%s' "$file_path"
        fi
    done | sha1sum | awk '{print $1}'
}

remote_path_for_session() {
    local session_id="$1"
    printf '%s/logs/sessions/%s' "$windows_repo_root" "$session_id"
}

ensure_remote_dir() {
    local remote_dir="$1"
    "${ssh_base_cmd[@]}" "$windows_user@$windows_host" \
        "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force -Path '$remote_dir' | Out-Null\""
}

copy_file_to_windows() {
    local local_file="$1"
    local remote_file="$2"
    "${scp_base_cmd[@]}" "$local_file" "$windows_user@$windows_host:$remote_file"
}

remote_file_signature() {
    local remote_file="$1"
    local remote_script

    remote_script=$(cat <<EOF
\$path = '$remote_file'
if (Test-Path -LiteralPath \$path) {
    \$item = Get-Item -LiteralPath \$path
    \$mtime = ([DateTimeOffset]\$item.LastWriteTimeUtc).ToUnixTimeSeconds()
    Write-Output ("\$mtime {0}" -f \$item.Length)
}
EOF
)

    "${ssh_base_cmd[@]}" "$windows_user@$windows_host" \
        "powershell -NoProfile -Command \"$remote_script\"" 2>/dev/null || true
}

should_copy_to_windows() {
    local local_file="$1"
    local remote_file="$2"
    local local_mtime
    local local_size
    local remote_info
    local remote_mtime
    local remote_size

    read -r local_mtime local_size < <(stat -c '%Y %s' "$local_file")
    remote_info=$(remote_file_signature "$remote_file" | tail -n 1 || true)

    if [[ -z "$remote_info" ]]; then
        return 0
    fi

    read -r remote_mtime remote_size <<<"$remote_info"
    if [[ -z "$remote_mtime" || -z "$remote_size" ]]; then
        return 0
    fi

    if (( local_mtime > remote_mtime )); then
        return 0
    fi

    if (( local_mtime == remote_mtime )) && [[ "$local_size" != "$remote_size" ]]; then
        return 0
    fi

    return 1
}

sync_session() {
    local session_id="$1"
    local session_dir="$sessions_dir/$session_id"
    local remote_session_dir
    local remote_file
    local name

    if [[ ! -d "$session_dir" ]]; then
        return 0
    fi

    remote_session_dir=$(remote_path_for_session "$session_id")
    ensure_remote_dir "$remote_session_dir"

    for name in "${metadata_files[@]}"; do
        if [[ -f "$session_dir/$name" ]]; then
            remote_file="$remote_session_dir/$name"
            if should_copy_to_windows "$session_dir/$name" "$remote_file"; then
                copy_file_to_windows "$session_dir/$name" "$remote_file"
            fi
        fi
    done

    printf 'Pushed session: %s -> %s\n' "$session_id" "$remote_session_dir"
}

sync_changed_sessions_once() {
    local session_id
    local signature

    while IFS= read -r session_id; do
        [[ -z "$session_id" ]] && continue
        signature=$(session_signature "$session_id")
        if [[ "${last_signature[$session_id]-}" != "$signature" ]]; then
            sync_session "$session_id"
            last_signature["$session_id"]="$signature"
        fi
    done < <(list_session_ids)
}

sync_changed_sessions_once

if [[ "$watch_mode" -eq 0 ]]; then
    exit 0
fi

printf 'Watching %s for session updates every %s seconds...\n' "$sessions_dir" "$interval_seconds"

while true; do
    sleep "$interval_seconds"
    sync_changed_sessions_once
done
