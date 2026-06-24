#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SPEC_FILE="${1:-MacLocalFileManager.spec}"
APP_NAME="${2:-MacLocalFileManager}"
VOL_NAME="${3:-$APP_NAME}"
VERSION="${MACLOCALFILEMANAGER_VERSION:-1.1.0}"
APP_PATH="dist/$APP_NAME.app"
DMG_PATH="dist/$APP_NAME.dmg"
VERSIONED_DMG_PATH="dist/$APP_NAME-v$VERSION.dmg"
STAGING_DIR="dist/$APP_NAME-dmg-staging"

packaging/build_macos_app.sh "$SPEC_FILE" "$APP_NAME"

rm -rf "$STAGING_DIR" "$DMG_PATH" "$VERSIONED_DMG_PATH"
trap 'rm -rf "$STAGING_DIR"' EXIT
mkdir -p "$STAGING_DIR"
cp -R "$APP_PATH" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

hdiutil create \
  -volname "$VOL_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

cp "$DMG_PATH" "$VERSIONED_DMG_PATH"

rm -rf "$STAGING_DIR"
trap - EXIT
echo "Built: $(pwd)/$DMG_PATH"
echo "Built: $(pwd)/$VERSIONED_DMG_PATH"
