#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)
unit_source="$script_dir/systemd/elevator_ai-session-pusher.service"
user_unit_dir="$HOME/.config/systemd/user"
env_dir="$HOME/.config/elevator_ai"
env_file="$env_dir/session_pusher.env"

mkdir -p "$user_unit_dir" "$env_dir"
cp "$unit_source" "$user_unit_dir/elevator_ai-session-pusher.service"

if [[ ! -f "$env_file" ]]; then
    detected_host=""
    if [[ -n "${SSH_CLIENT:-}" ]]; then
        detected_host=$(printf '%s\n' "$SSH_CLIENT" | awk '{print $1}')
    fi

    cat > "$env_file" <<EOF
# Windows SSH target for session metadata push.
# Fill WINDOWS_USER after confirming the Windows SSH login user.
WINDOWS_HOST=${detected_host}
WINDOWS_USER=
WINDOWS_REPO_ROOT=D:/elevator_ai/elevator_ai
SSH_PORT=22
FALLBACK_WINDOWS_HOST=127.0.0.1
FALLBACK_SSH_PORT=10023
IDENTITY_FILE=/home/ywj/.ssh/id_ed25519_windows_session_pusher
SESSION_FILTER=all
SYNC_INTERVAL=10
RETRY_INTERVAL=15
EOF
fi

systemctl --user daemon-reload
systemctl --user enable --now elevator_ai-session-pusher.service
systemctl --user --no-pager --full status elevator_ai-session-pusher.service
