#!/usr/bin/env bash
# Build dist/FlowLocal-<version>.msi from the PyInstaller one-dir output.
# Downloads WiX 3.14 portable binaries to build/wix on first run.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(venv/Scripts/python.exe -c "import paths; print(paths.APP_VERSION)")
WIX=build/wix
[ -d dist/FlowLocal ] || { echo "run PyInstaller first"; exit 1; }
if [ ! -f "$WIX/heat.exe" ]; then
  mkdir -p "$WIX"
  curl -L -o "$WIX/wix314.zip" \
    https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip
  (cd "$WIX" && unzip -oq wix314.zip && rm wix314.zip)
fi
"$WIX/heat.exe" dir dist/FlowLocal -cg AppFiles -dr INSTALLDIR \
  -srd -sreg -scom -ag -sfrag -template fragment -out build/harvest.wxs
"$WIX/candle.exe" -nologo -arch x64 -dAppVersion="$VERSION" -out build/ \
  build/harvest.wxs installer/flowlocal.wxs
# Build to a temp name and rename atomically: nobody can double-click a
# half-written MSI mid-build. Then purge superseded versions so the only
# clickable installer in dist/ is the current one.
"$WIX/light.exe" -nologo -b dist/FlowLocal -sval \
  -out "dist/FlowLocal-$VERSION.msi.building" build/harvest.wixobj build/flowlocal.wixobj
mv -f "dist/FlowLocal-$VERSION.msi.building" "dist/FlowLocal-$VERSION.msi"
find dist -maxdepth 1 -name "FlowLocal-*.msi" ! -name "FlowLocal-$VERSION.msi" -delete
echo "built dist/FlowLocal-$VERSION.msi"
