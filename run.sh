#!/bin/bash
# Start ArcheryCamPiRunner after cleanly stopping any existing instance.
#
# Usage:
#   ./run.sh                # stop old instance, then launch in background
#   ./run.sh --foreground   # stop old instance, then run in foreground
#
# Optional environment variables:
#   PYTHON_BIN=<python executable>
#   VENV_DIR=<virtualenv directory to prefer, default: .venv>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
APP_ENTRY="server3.py"
PID_FILE="$APP_DIR/.kiosk.pid"
LOG_FILE="$APP_DIR/kiosk.log"
STOP_TIMEOUT_SECONDS=15
VENV_DIR="${VENV_DIR:-$APP_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-}"
DISPLAY_VALUE="${DISPLAY:-:0}"
XAUTHORITY_VALUE="${XAUTHORITY:-$HOME/.Xauthority}"
WAYLAND_DISPLAY_VALUE="${WAYLAND_DISPLAY:-}"
XDG_RUNTIME_DIR_VALUE="${XDG_RUNTIME_DIR:-}"

resolve_python_bin() {
    if [ -n "$PYTHON_BIN" ]; then
        return 0
    fi

    if [ -x "$VENV_DIR/bin/python" ]; then
        PYTHON_BIN="$VENV_DIR/bin/python"
    else
        PYTHON_BIN="python3"
    fi
}

is_running() {
    local pid="$1"
    kill -0 "$pid" >/dev/null 2>&1
}

wait_for_exit() {
    local pid="$1"
    local timeout="$2"
    local elapsed=0
    while is_running "$pid"; do
        if [ "$elapsed" -ge "$timeout" ]; then
            return 1
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 0
}

stop_process_group_gracefully() {
    local pid="$1"

    if ! is_running "$pid"; then
        return 0
    fi

    echo "Stopping existing process group for PID $pid (SIGTERM)..."
    kill -TERM -- "-$pid" >/dev/null 2>&1 || kill -TERM "$pid" >/dev/null 2>&1 || true

    if wait_for_exit "$pid" "$STOP_TIMEOUT_SECONDS"; then
        echo "Existing instance stopped."
        return 0
    fi

    echo "Graceful stop timed out for PID $pid."
    return 1
}

stop_existing_instances() {
    local had_timeout=0

    # Stop the tracked process group first.
    if [ -f "$PID_FILE" ]; then
        local tracked_pid
        tracked_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
        if [ -n "$tracked_pid" ] && [[ "$tracked_pid" =~ ^[0-9]+$ ]]; then
            if ! stop_process_group_gracefully "$tracked_pid"; then
                had_timeout=1
            fi
        fi
        rm -f "$PID_FILE"
    fi

    # Also stop any stray server3.py instances not in pid file.
    local pids
    pids="$(pgrep -f "python(3)? .*${APP_ENTRY}" || true)"
    if [ -n "$pids" ]; then
        echo "Stopping stray $APP_ENTRY process(es): $pids"
        for pid in $pids; do
            if ! stop_process_group_gracefully "$pid"; then
                had_timeout=1
            fi
        done
    fi

    if [ "$had_timeout" -ne 0 ]; then
        echo "One or more processes did not exit gracefully."
        echo "Run ./kill.sh to force-stop remaining processes."
        return 1
    fi

    return 0
}

start_background() {
    cd "$APP_DIR"
    echo "Starting $APP_ENTRY in background..."
    echo "Using python: $PYTHON_BIN"
    echo "DISPLAY=$DISPLAY_VALUE"
    if [ -n "$WAYLAND_DISPLAY_VALUE" ]; then
        echo "WAYLAND_DISPLAY=$WAYLAND_DISPLAY_VALUE"
    fi

    if [ -f "$XAUTHORITY_VALUE" ]; then
        echo "XAUTHORITY=$XAUTHORITY_VALUE"
    else
        echo "XAUTHORITY file not found at $XAUTHORITY_VALUE (GUI startup may fail)"
    fi

    # Start in a dedicated session so we can stop all spawned processes as a group.
    if [ -n "$WAYLAND_DISPLAY_VALUE" ] || [ -n "$XDG_RUNTIME_DIR_VALUE" ]; then
        DISPLAY="$DISPLAY_VALUE" XAUTHORITY="$XAUTHORITY_VALUE" WAYLAND_DISPLAY="$WAYLAND_DISPLAY_VALUE" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR_VALUE" setsid "$PYTHON_BIN" "$APP_ENTRY" >> "$LOG_FILE" 2>&1 &
    else
        DISPLAY="$DISPLAY_VALUE" XAUTHORITY="$XAUTHORITY_VALUE" setsid "$PYTHON_BIN" "$APP_ENTRY" >> "$LOG_FILE" 2>&1 &
    fi
    local pid=$!
    echo "$pid" > "$PID_FILE"

    # Verify process stayed alive long enough to indicate successful startup.
    sleep 2
    if ! is_running "$pid"; then
        echo "Startup failed. Last 50 log lines:"
        tail -n 50 "$LOG_FILE" || true
        rm -f "$PID_FILE"
        return 1
    fi

    echo "Started with PID $pid"
    echo "Logs: $LOG_FILE"
}

start_foreground() {
    cd "$APP_DIR"
    echo "Starting $APP_ENTRY in foreground..."
    echo "Using python: $PYTHON_BIN"
    echo "DISPLAY=$DISPLAY_VALUE"
    if [ -n "$WAYLAND_DISPLAY_VALUE" ]; then
        echo "WAYLAND_DISPLAY=$WAYLAND_DISPLAY_VALUE"
    fi
    if [ -f "$XAUTHORITY_VALUE" ]; then
        echo "XAUTHORITY=$XAUTHORITY_VALUE"
    else
        echo "XAUTHORITY file not found at $XAUTHORITY_VALUE (GUI startup may fail)"
    fi
    if [ -n "$WAYLAND_DISPLAY_VALUE" ] || [ -n "$XDG_RUNTIME_DIR_VALUE" ]; then
        exec env DISPLAY="$DISPLAY_VALUE" XAUTHORITY="$XAUTHORITY_VALUE" WAYLAND_DISPLAY="$WAYLAND_DISPLAY_VALUE" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR_VALUE" "$PYTHON_BIN" "$APP_ENTRY"
    else
        exec env DISPLAY="$DISPLAY_VALUE" XAUTHORITY="$XAUTHORITY_VALUE" "$PYTHON_BIN" "$APP_ENTRY"
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but not installed"
    exit 1
fi

if ! command -v pgrep >/dev/null 2>&1; then
    echo "pgrep is required but not installed"
    exit 1
fi

MODE="background"
if [ "${1:-}" = "--foreground" ]; then
    MODE="foreground"
fi

resolve_python_bin

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Python executable not found: $PYTHON_BIN"
    exit 1
fi

stop_existing_instances

if [ "$MODE" = "foreground" ]; then
    start_foreground
else
    start_background
fi
