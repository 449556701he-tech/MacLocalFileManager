#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SPEC_FILE="${1:-MacLocalFileManager.spec}"
APP_NAME="${2:-MacLocalFileManager}"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$(pwd)/build/pyinstaller-cache}"
mkdir -p "$PYINSTALLER_CONFIG_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install pyinstaller

rm -rf "build/$APP_NAME" "dist/$APP_NAME" "dist/$APP_NAME.app"
.venv/bin/pyinstaller --clean --noconfirm "$SPEC_FILE"

echo "Built: $(pwd)/dist/$APP_NAME.app"
