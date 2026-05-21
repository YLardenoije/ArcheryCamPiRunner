#!/bin/bash
# Update ArcheryCamPiRunner from git and refresh dependencies.
# Optional behavior is controlled by env vars:
#   VENV_DIR=<virtualenv directory> (default: .venv)
#   START_AFTER_UPDATE=1|0 (default: 1)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR}"
VENV_DIR="${VENV_DIR:-.venv}"
START_AFTER_UPDATE="${START_AFTER_UPDATE:-1}"

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

if [ -x "./kill.sh" ]; then
    echo "Stopping any existing kiosk instance with kill.sh"
    ./kill.sh
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

if [ "$START_AFTER_UPDATE" = "1" ]; then
    if [ -x "./run.sh" ]; then
        echo "Starting kiosk with run.sh"
        ./run.sh
    else
        echo "run.sh not found or not executable. Skipping restart."
    fi
else
    echo "Post-update start disabled (START_AFTER_UPDATE=$START_AFTER_UPDATE)"
fi

echo "Update complete."
