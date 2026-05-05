#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
default_env_file="$HOME/.config/elevator_ai/session_pusher.env"
env_file="${SESSION_PUSHER_ENV:-$default_env_file}"

log() {
    printf '[session-pusher] %s\n' "$*" >&2
}

load_env() {
    if [[ ! -f "$env_file" ]]; then
        log "waiting for env file: $env_file"
        return 1
    fi

    # shellcheck disable=SC1090
    set -a
    source "$env_file"
    set +a
    return 0
}

select_target() {
    local primary_host="$1"
    local primary_port="$2"
    local fallback_host="$3"
    local fallback_port="$4"
    local retry_interval="$5"

    if nc -z -w 3 "$primary_host" "$primary_port" >/dev/null 2>&1; then
        printf '%s %s primary\n' "$primary_host" "$primary_port"
        return 0
    fi

    if [[ -n "$fallback_host" ]] && nc -z -w 3 "$fallback_host" "$fallback_port" >/dev/null 2>&1; then
        printf '%s %s fallback\n' "$fallback_host" "$fallback_port"
        return 0
    fi

    if [[ -n "$fallback_host" ]]; then
        log "Windows SSH is not reachable at $primary_host:$primary_port; fallback $fallback_host:$fallback_port is also unavailable; retrying in ${retry_interval}s"
    else
        log "Windows SSH is not reachable at $primary_host:$primary_port; retrying in ${retry_interval}s"
    fi

    return 1
}

while true; do
    if ! load_env; then
        sleep 15
        continue
    fi

    windows_host="${WINDOWS_HOST:-}"
    windows_user="${WINDOWS_USER:-}"
    windows_repo_root="${WINDOWS_REPO_ROOT:-D:/elevator_ai/elevator_ai}"
    ssh_port="${SSH_PORT:-22}"
    fallback_windows_host="${FALLBACK_WINDOWS_HOST:-}"
    fallback_ssh_port="${FALLBACK_SSH_PORT:-10023}"
    identity_file="${IDENTITY_FILE:-}"
    session_filter="${SESSION_FILTER:-all}"
    sync_interval="${SYNC_INTERVAL:-10}"
    retry_interval="${RETRY_INTERVAL:-15}"

    if [[ -z "$windows_host" ]]; then
        log "waiting for WINDOWS_HOST in $env_file"
        sleep "$retry_interval"
        continue
    fi

    if [[ -z "$windows_user" ]]; then
        log "waiting for WINDOWS_USER in $env_file"
        sleep "$retry_interval"
        continue
    fi

    if [[ -n "$identity_file" && ! -f "$identity_file" ]]; then
        log "waiting for IDENTITY_FILE to exist: $identity_file"
        sleep "$retry_interval"
        continue
    fi

    if ! read -r active_host active_port active_mode < <(
        select_target "$windows_host" "$ssh_port" "$fallback_windows_host" "$fallback_ssh_port" "$retry_interval"
    ); then
        sleep "$retry_interval"
        continue
    fi

    log "starting watcher for $windows_user@$active_host:$active_port ($active_mode) -> $windows_repo_root"

    push_args=(
        --windows-host "$active_host"
        --windows-user "$windows_user"
        --windows-repo-root "$windows_repo_root"
        --ssh-port "$active_port"
        --session "$session_filter"
        --interval "$sync_interval"
        --watch
    )

    if [[ -n "$identity_file" ]]; then
        push_args+=(--identity-file "$identity_file")
    fi

    if "$script_dir/push_sessions_to_windows.sh" "${push_args[@]}"; then
        log "watcher exited normally; restarting in ${retry_interval}s"
    else
        rc=$?
        log "watcher exited with code $rc; restarting in ${retry_interval}s"
    fi

    sleep "$retry_interval"
done
