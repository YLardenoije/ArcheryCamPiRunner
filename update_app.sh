#!/bin/bash
# Update ArcheryCamPiRunner from git and refresh dependencies.
# Optional behavior is controlled by env vars:
#   RESTART_SERVICE=1|0 (default: 1)
#   SERVICE_NAME=<systemd service name> (default: kiosk.service)
#   VENV_DIR=<virtualenv directory> (default: .venv)
#   FALLBACK_TO_RUN_SCRIPT=1|0 (default: 1)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR}"
RESTART_SERVICE="${RESTART_SERVICE:-1}"
SERVICE_NAME="${SERVICE_NAME:-kiosk.service}"
VENV_DIR="${VENV_DIR:-.venv}"
FALLBACK_TO_RUN_SCRIPT="${FALLBACK_TO_RUN_SCRIPT:-1}"

cd "$REPO_DIR"

if ! command -v git >/dev/null 2>&1; then
    echo "git is required but not installed"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but not installed"
    exit 1
fi

if ! python3 -m venv -h >/dev/null 2>&1; then
    echo "python3 venv support is required. Install with: sudo apt-get install python3-venv"
    exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Not a git repository: $REPO_DIR"
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Working tree is not clean. Commit or stash changes before updating."
    exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "Updating branch: $BRANCH"

git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "Ensuring virtual environment exists at $VENV_DIR"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "Virtualenv python not found at $VENV_PYTHON"
    exit 1
fi

echo "Installing/updating Python dependencies in virtualenv"
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt

if [ "$RESTART_SERVICE" = "1" ]; then
    restart_done=0
    if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q "^${SERVICE_NAME}"; then
        echo "Restarting service: $SERVICE_NAME"
        if [ "$EUID" -eq 0 ]; then
            if systemctl restart "$SERVICE_NAME"; then
                restart_done=1
            else
                echo "Service restart failed as root."
            fi
        else
            if command -v sudo >/dev/null 2>&1 && sudo -n systemctl restart "$SERVICE_NAME"; then
                restart_done=1
            else
                echo "Service restart not permitted for non-root user without passwordless sudo."
            fi
        fi
    else
        echo "Service $SERVICE_NAME not found."
    fi

    if [ "$restart_done" -eq 0 ]; then
        if [ "$FALLBACK_TO_RUN_SCRIPT" = "1" ] && [ -x "./run.sh" ]; then
            echo "Falling back to ./run.sh"
            ./run.sh
        else
            echo "Skipping restart."
        fi
    fi
else
    echo "Service restart disabled (RESTART_SERVICE=$RESTART_SERVICE)"
fi

echo "Update complete."
