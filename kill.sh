#!/bin/bash
# Force-stop ArcheryCamPiRunner instances when graceful shutdown fails.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
APP_ENTRY="server3.py"
PID_FILE="$APP_DIR/.kiosk.pid"

kill_group_forcefully() {
    local pid="$1"

    if kill -0 "$pid" >/dev/null 2>&1; then
        echo "Force-killing process group for PID $pid (SIGKILL)..."
        kill -KILL -- "-$pid" >/dev/null 2>&1 || kill -KILL "$pid" >/dev/null 2>&1 || true
    fi
}

# Kill tracked PID first.
if [ -f "$PID_FILE" ]; then
    tracked_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$tracked_pid" ] && [[ "$tracked_pid" =~ ^[0-9]+$ ]]; then
        kill_group_forcefully "$tracked_pid"
    fi
    rm -f "$PID_FILE"
fi

# Kill any stray server3.py processes.
pids="$(pgrep -f "python(3)? .*${APP_ENTRY}" || true)"
if [ -n "$pids" ]; then
    echo "Force-killing stray $APP_ENTRY process(es): $pids"
    for pid in $pids; do
        kill_group_forcefully "$pid"
    done
fi

echo "Kill script complete."
