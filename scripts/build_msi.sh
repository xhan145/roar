#!/usr/bin/env bash
# Build dist/FlowLocal-<version>.msi from the PyInstaller one-dir output.
# Downloads WiX 3.14 portable binaries to build/wix on first run.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="0.2.0"
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
"$WIX/candle.exe" -nologo -arch x64 -out build/ \
  build/harvest.wxs installer/flowlocal.wxs
"$WIX/light.exe" -nologo -b dist/FlowLocal -sval \
  -out "dist/FlowLocal-$VERSION.msi" build/harvest.wixobj build/flowlocal.wixobj
echo "built dist/FlowLocal-$VERSION.msi"
