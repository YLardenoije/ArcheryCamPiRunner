#!/bin/bash
# Update ArcheryCamPiRunner from git and refresh dependencies.
# Optional behavior is controlled by env vars:
#   RESTART_SERVICE=1|0 (default: 1)
#   SERVICE_NAME=<systemd service name> (default: kiosk.service)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR}"
RESTART_SERVICE="${RESTART_SERVICE:-1}"
SERVICE_NAME="${SERVICE_NAME:-kiosk.service}"

cd "$REPO_DIR"

if ! command -v git >/dev/null 2>&1; then
    echo "git is required but not installed"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but not installed"
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

echo "Installing/updating Python dependencies"
python3 -m pip install -r requirements.txt

if [ "$RESTART_SERVICE" = "1" ]; then
    if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q "^${SERVICE_NAME}"; then
        echo "Restarting service: $SERVICE_NAME"
        if [ "$EUID" -eq 0 ]; then
            systemctl restart "$SERVICE_NAME"
        else
            sudo systemctl restart "$SERVICE_NAME"
        fi
    else
        echo "Service $SERVICE_NAME not found. Skipping restart."
    fi
else
    echo "Service restart disabled (RESTART_SERVICE=$RESTART_SERVICE)"
fi

echo "Update complete."
