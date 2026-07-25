#!/usr/bin/env bash
# Wrap dist/ROAR-<version>.msi + roar*.cab into a single self-extracting
# dist/ROAR-Setup-<version>.exe: 7zSD stub extracts to temp, ExecuteFile runs
# the bundled install.cmd, which launches msiexec /qb on the extracted MSI.
# Run AFTER scripts/build_msi.sh. Self-contained: downloads portable 7-Zip
# tooling to build/7zsd on first run (no installed 7-Zip required).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(venv/Scripts/python.exe -c "import paths; print(paths.APP_VERSION)" | tr -d '\r')
TOOLS=build/7zsd
SFX=$TOOLS/7zSD.sfx
SEVENZA=$TOOLS/7za.exe

[ -f "dist/ROAR-$VERSION.msi" ] || { echo "dist/ROAR-$VERSION.msi missing — run build_msi.sh first"; exit 1; }
ls dist/roar*.cab >/dev/null 2>&1 || { echo "dist/roar*.cab missing — run build_msi.sh first"; exit 1; }

mkdir -p "$TOOLS"
if [ ! -f "$SEVENZA" ]; then
  # bootstrap: 7zr.exe is a standalone extractor that can open the -extra pkg
  curl -L -o "$TOOLS/7zr.exe" https://www.7-zip.org/a/7zr.exe
  curl -L -o "$TOOLS/7z-extra.7z" https://www.7-zip.org/a/7z2301-extra.7z
  "$TOOLS/7zr.exe" e -y -o"$TOOLS" "$TOOLS/7z-extra.7z" x64/7za.exe
  rm -f "$TOOLS/7z-extra.7z"
fi
if [ ! -f "$SFX" ]; then
  # LZMA SDK 19.00 is the last release with the prebuilt installer stub;
  # it reads modern 7z archives fine
  curl -L -o "$TOOLS/lzma1900.7z" https://www.7-zip.org/a/lzma1900.7z
  "$SEVENZA" e -y -o"$TOOLS" "$TOOLS/lzma1900.7z" bin/7zSD.sfx
  rm -f "$TOOLS/lzma1900.7z"
fi

# Stage a FLAT payload: 7za preserves relative dir prefixes, and a stored
# "dist\" prefix strands the msi in a subfolder the stub's install.cmd can't
# see (msiexec 1619). Archiving from inside the staging dir stores bare names.
STAGE=build/setup-stage
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp "dist/ROAR-$VERSION.msi" dist/roar*.cab "$STAGE/"
# install.cmd travels INSIDE the archive: the 7zSD stub launches in-archive
# files reliably (ExecuteFile/ShellExecute); bare program names like
# "msiexec" fail its CreateProcess path. %~dp0 = the extraction temp dir.
#
# Never replace the one-dir PyInstaller runtime while ROAR is running. In
# particular, a same-version major upgrade can otherwise remove an in-use
# base_library.zip without successfully putting it back, leaving the next
# launch unable to import Python's encodings module.
printf '%s\r\n' \
  '@echo off' \
  'tasklist /FI "IMAGENAME eq ROAR.exe" /NH 2>NUL | find /I "ROAR.exe" >NUL' \
  'if ERRORLEVEL 1 goto install' \
  'echo.' \
  'echo ROAR is currently running. Please exit ROAR from its tray icon, then run this installer again.' \
  'echo.' \
  'pause' \
  'exit /b 1618' \
  ':install' \
  "msiexec /i \"%~dp0ROAR-$VERSION.msi\" /qb" \
  'exit /b %ERRORLEVEL%' > "$STAGE/install.cmd"

# store-mode archive: the cabs are already mszip-compressed
rm -f build/setup-payload.7z
(cd "$STAGE" && "../7zsd/7za.exe" a -t7z -mx0 ../setup-payload.7z ./*)
rm -rf "$STAGE"

printf '%s\r\n' \
  ';!@Install@!UTF-8!' \
  "Title=\"ROAR $VERSION\"" \
  'ExecuteFile="install.cmd"' \
  ';!@InstallEnd@!' > build/setup-config.txt

cat "$SFX" build/setup-config.txt build/setup-payload.7z \
  > "dist/ROAR-Setup-$VERSION.exe.building"
mv -f "dist/ROAR-Setup-$VERSION.exe.building" "dist/ROAR-Setup-$VERSION.exe"
find dist -maxdepth 1 \( -name "ROAR-Setup-*.exe" ! -name "ROAR-Setup-$VERSION.exe" \) -delete
rm -f build/setup-payload.7z build/setup-config.txt build/install.cmd
echo "built dist/ROAR-Setup-$VERSION.exe"
