#!/usr/bin/env bash
# Build a ROAR AppImage on Ubuntu 24.04. Unverified from the Windows dev box —
# run this on the target machine. Requires: the venv from setup.sh, pyinstaller,
# and appimagetool on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
pip install pyinstaller
pyinstaller --noconfirm --name ROAR --windowed app.py
APPDIR=dist/ROAR.AppDir
rm -rf "$APPDIR"; mkdir -p "$APPDIR/usr/bin"
cp -r dist/ROAR/* "$APPDIR/usr/bin/"
cp linux/roar.desktop "$APPDIR/ROAR.desktop"
cp assets/roar-logo-purple.png "$APPDIR/roar.png" 2>/dev/null || true
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/ROAR" "$@"
EOF
chmod +x "$APPDIR/AppRun"
appimagetool "$APPDIR" dist/ROAR-x86_64.AppImage
echo "Built dist/ROAR-x86_64.AppImage"
