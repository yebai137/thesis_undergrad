#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)
unit_source="$script_dir/systemd/elevator_ai-session-server-worker.service"
user_unit_dir="$HOME/.config/systemd/user"
env_dir="$HOME/.config/elevator_ai"
env_file="$env_dir/session_server_worker.env"

mkdir -p "$user_unit_dir" "$env_dir"
cp "$unit_source" "$user_unit_dir/elevator_ai-session-server-worker.service"

if [[ ! -f "$env_file" ]]; then
    cat > "$env_file" <<EOF
# Session filter: all / latest / explicit session id
SESSION_FILTER=all
POLL_INTERVAL=15
CODEX_MODEL=gpt-5.4
SANDBOX_MODE=workspace-write
http_proxy=${http_proxy:-}
https_proxy=${https_proxy:-}
all_proxy=${all_proxy:-}
HTTP_PROXY=${HTTP_PROXY:-${http_proxy:-}}
HTTPS_PROXY=${HTTPS_PROXY:-${https_proxy:-}}
ALL_PROXY=${ALL_PROXY:-${all_proxy:-}}
EOF
fi

systemctl --user daemon-reload
systemctl --user enable --now elevator_ai-session-server-worker.service
systemctl --user --no-pager --full status elevator_ai-session-server-worker.service
