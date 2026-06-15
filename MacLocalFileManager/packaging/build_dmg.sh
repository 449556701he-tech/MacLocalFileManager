#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_PATH="dist/MacLocalFileManager.app"
DMG_PATH="dist/MacLocalFileManager.dmg"
STAGING_DIR="dist/dmg-staging"

if [[ ! -d "$APP_PATH" ]]; then
  packaging/build_macos_app.sh
fi

rm -rf "$STAGING_DIR" "$DMG_PATH"
mkdir -p "$STAGING_DIR"
cp -R "$APP_PATH" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

hdiutil create \
  -volname "MacLocalFileManager" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

rm -rf "$STAGING_DIR"
echo "Built: $(pwd)/$DMG_PATH"
