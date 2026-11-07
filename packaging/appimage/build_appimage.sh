#!/usr/bin/env bash
# Monta AssetDeck-x86_64.AppImage a partir de dist/assetdeck (saida do PyInstaller).
# Uso (na raiz do repo): packaging/appimage/build_appimage.sh
set -euo pipefail

APPDIR="AssetDeck.AppDir"
OUT="AssetDeck-x86_64.AppImage"

rm -rf "$APPDIR" "$OUT"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a dist/assetdeck/. "$APPDIR/usr/bin/"
cp packaging/appimage/AssetDeck.desktop "$APPDIR/AssetDeck.desktop"
cp packaging/appimage/AssetDeck.desktop "$APPDIR/usr/share/applications/AssetDeck.desktop"
cp assetdeck/ui/icons/app-icon.png "$APPDIR/assetdeck.png"
cp assetdeck/ui/icons/app-icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/assetdeck.png"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/assetdeck" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# appimagetool precisa de FUSE; no CI usamos --appimage-extract-and-run.
APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "Gerado: $OUT"
