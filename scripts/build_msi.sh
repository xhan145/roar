#!/usr/bin/env bash
# Build dist/ROAR-<version>.msi from the PyInstaller one-dir output.
# Downloads WiX 3.14 portable binaries to build/wix on first run.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(venv/Scripts/python.exe -c "import paths; print(paths.APP_VERSION)" | tr -d '\r')
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
# half-written MSI mid-build. Then keep only the newest TWO (see below).
# CABs are external (an .msi file is hard-capped at 2 GB) and land next to
# the -out target; clear stale ones so the set always matches this msi.
rm -f dist/roar*.cab
"$WIX/light.exe" -nologo -b dist/ROAR -sval \
  -out "dist/ROAR-$VERSION.msi.building" build/harvest.wixobj build/roar.wixobj
mv -f "dist/ROAR-$VERSION.msi.building" "dist/ROAR-$VERSION.msi"
# Keep the current AND the immediately-previous MSI. Windows Installer needs
# the OLD version's .msi to remove that product during a major upgrade — it
# looks in the InstallSource it recorded, i.e. this dist/ dir. Deleting it
# makes the next in-place upgrade die with Error 1714 / System Error 1612
# while STILL reporting exit code 0: a silent no-op install (hit for real on
# the 0.34.0 -> 0.35.0 upgrade, 2026-08-02). The *clickable* installer is the
# Setup .exe, and build_setup.sh still keeps exactly one of those.
ls -1 dist/ROAR-*.msi 2>/dev/null | sort -V | head -n -2 | xargs -r rm -f
find dist -maxdepth 1 -name "FlowLocal-*.msi*" -delete  # pre-rename leftovers
echo "built dist/ROAR-$VERSION.msi"
