#!/usr/bin/env bash
# Build and smoke-test the canonical ROAR Linux AppImage.
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo_root"

if [[ "$(uname -s)" != "Linux" ]]; then
  printf 'error: Linux is required to build the ROAR AppImage\n' >&2
  exit 1
fi
if [[ "$(uname -m)" != "x86_64" ]]; then
  printf 'error: x86_64 is required to build the ROAR AppImage\n' >&2
  exit 1
fi
if [[ -z "${APPIMAGETOOL:-}" ]]; then
  printf 'error: set APPIMAGETOOL to a trusted appimagetool executable\n' >&2
  exit 1
fi

python_cmd=("${ROAR_LINUX_PYTHON:-.venv/bin/python}")
appimagetool_cmd=("$APPIMAGETOOL")
if [[ "$APPIMAGETOOL" == */* ]]; then
  if [[ ! -x "$APPIMAGETOOL" ]]; then
    printf 'error: APPIMAGETOOL is not executable: %s\n' "$APPIMAGETOOL" >&2
    exit 1
  fi
elif ! command -v "$APPIMAGETOOL" >/dev/null 2>&1; then
  printf 'error: APPIMAGETOOL was not found: %s\n' "$APPIMAGETOOL" >&2
  exit 1
fi

version="$("${python_cmd[@]}" -c 'from paths import APP_VERSION; print(APP_VERSION)')"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf 'error: invalid paths.APP_VERSION: %s\n' "$version" >&2
  exit 1
fi

build_root="build/linux"
frozen_root="$build_root/frozen"
frozen_tree="$frozen_root/ROAR-linux"
appdir="$build_root/ROAR.AppDir"
dist_dir="dist"
artifact_name="ROAR-Linux-${version}-x86_64.AppImage"
artifact="$dist_dir/$artifact_name"
building="$artifact.building"
sidecar="$artifact.sha256"

rm -rf -- "$build_root"
mkdir -p -- "$appdir/usr/bin/ROAR" "$dist_dir"

shopt -s nullglob
old_linux_artifacts=(
  "$dist_dir"/ROAR-Linux-*-x86_64.AppImage
  "$dist_dir"/ROAR-Linux-*-x86_64.AppImage.sha256
  "$dist_dir"/ROAR-Linux-*-x86_64.AppImage.building
)
if ((${#old_linux_artifacts[@]})); then
  rm -f -- "${old_linux_artifacts[@]}"
fi
shopt -u nullglob

completed=0
cleanup_failed_build() {
  if ((completed == 0)); then
    rm -f -- "$building" "$artifact" "$sidecar"
  fi
}
trap cleanup_failed_build EXIT

"${python_cmd[@]}" -m PyInstaller \
  --noconfirm \
  --clean \
  --workpath "$build_root/pyinstaller" \
  --distpath "$frozen_root" \
  roar-linux.spec

if [[ ! -x "$frozen_tree/ROAR-linux" ]]; then
  printf 'error: PyInstaller did not produce %s\n' "$frozen_tree/ROAR-linux" >&2
  exit 1
fi

cp -a -- "$frozen_tree/." "$appdir/usr/bin/ROAR/"
cp -- "linux/roar.desktop" "$appdir/ROAR.desktop"
cp -- "assets/roar-logo-purple.png" "$appdir/roar.png"
cp -- "assets/roar-logo-purple.png" "$appdir/.DirIcon"

cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export ROAR_APPIMAGE=1
exec "$HERE/usr/bin/ROAR/ROAR-linux" "$@"
EOF
chmod +x -- "$appdir/AppRun"

bash linux/verify_appimage.sh --frozen "$appdir/usr/bin/ROAR/ROAR-linux"
ARCH=x86_64 "${appimagetool_cmd[@]}" "$appdir" "$building"
mv -- "$building" "$artifact"
(
  cd "$dist_dir"
  sha256sum "$artifact_name" > "$artifact_name.sha256"
)
bash linux/verify_appimage.sh "$artifact"

completed=1
trap - EXIT
printf 'Built %s\n' "$artifact"
printf 'SHA-256 %s\n' "$sidecar"
