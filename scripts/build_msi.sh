#!/usr/bin/env bash
# Build dist/ROAR-<version>.msi from the PyInstaller one-dir output.
# Downloads WiX 3.14 portable binaries to build/wix on first run.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(venv/Scripts/python.exe -c "import paths; print(paths.APP_VERSION)")
WIX=build/wix
[ -d dist/ROAR ] || { echo "run PyInstaller first"; exit 1; }
if [ ! -f "$WIX/heat.exe" ]; then
  mkdir -p "$WIX"
  curl -L -o "$WIX/wix314.zip" \
    https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip
  (cd "$WIX" && unzip -oq wix314.zip && rm wix314.zip)
fi
"$WIX/heat.exe" dir dist/ROAR -cg AppFiles -dr INSTALLDIR \
  -srd -sreg -scom -ag -sfrag -template fragment -out build/harvest.wxs
"$WIX/candle.exe" -nologo -arch x64 -dAppVersion="$VERSION" -out build/ \
  build/harvest.wxs installer/roar.wxs
# Build to a temp name and rename atomically: nobody can double-click a
# half-written MSI mid-build. Then purge superseded versions so the only
# clickable installer in dist/ is the current one.
"$WIX/light.exe" -nologo -b dist/ROAR -sval \
  -out "dist/ROAR-$VERSION.msi.building" build/harvest.wixobj build/roar.wixobj
mv -f "dist/ROAR-$VERSION.msi.building" "dist/ROAR-$VERSION.msi"
find dist -maxdepth 1 -name "ROAR-*.msi" ! -name "ROAR-$VERSION.msi" -delete
echo "built dist/ROAR-$VERSION.msi"
