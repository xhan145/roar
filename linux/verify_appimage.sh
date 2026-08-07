#!/usr/bin/env bash
# Smoke-test a frozen ROAR tree or a completed AppImage in isolated XDG dirs.
set -euo pipefail

usage() {
  printf 'usage: %s [--frozen] PATH_TO_APPIMAGE_OR_BINARY\n' "$0" >&2
  exit 2
}

mode="appimage"
if [[ "${1:-}" == "--frozen" ]]; then
  mode="frozen"
  shift
fi
[[ "$#" == 1 ]] || usage
target="$1"
[[ -f "$target" ]] || {
  printf 'error: package target does not exist: %s\n' "$target" >&2
  exit 1
}

verify_root="$(mktemp -d "${TMPDIR:-/tmp}/roar-appimage-verify.XXXXXX")"
cleanup() {
  rm -rf -- "$verify_root"
}
trap cleanup EXIT HUP INT TERM

export XDG_CONFIG_HOME="$verify_root/config"
export XDG_DATA_HOME="$verify_root/data"
export XDG_RUNTIME_DIR="$verify_root/runtime"
mkdir -p -- "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_RUNTIME_DIR"
chmod 700 -- "$XDG_RUNTIME_DIR"

if [[ "$mode" == "appimage" ]]; then
  sidecar="$target.sha256"
  [[ -f "$sidecar" ]] || {
    printf 'error: SHA-256 sidecar does not exist: %s\n' "$sidecar" >&2
    exit 1
  }
  target_dir="$(CDPATH= cd -- "$(dirname -- "$target")" && pwd)"
  target_name="$(basename -- "$target")"
  (
    cd "$target_dir"
    sha256sum --check "$target_name.sha256"
  )
fi

smoke_log="$verify_root/smoke.log"
smoke_timeout="${ROAR_SMOKE_TIMEOUT:-300}"
set +e
if [[ "$mode" == "frozen" ]]; then
  timeout --kill-after=10 "$smoke_timeout" \
    xvfb-run -a "$target" --smoke >"$smoke_log" 2>&1
  smoke_status=$?
else
  APPIMAGE_EXTRACT_AND_RUN=1 timeout --kill-after=10 "$smoke_timeout" \
    xvfb-run -a "$target" --smoke >"$smoke_log" 2>&1
  smoke_status=$?
fi
set -e
cat "$smoke_log"
app_log="$XDG_DATA_HOME/ROAR/roar.log"
if [[ -f "$app_log" ]]; then
  cat "$app_log"
  cat "$app_log" >> "$smoke_log"
fi

if ((smoke_status != 0)); then
  if ((smoke_status == 124)); then
    printf 'error: ROAR smoke test timed out after %s seconds\n' \
      "$smoke_timeout" >&2
    exit 124
  fi
  printf 'error: ROAR smoke test exited with status %s\n' "$smoke_status" >&2
  exit "$smoke_status"
fi
if grep -Fq 'ROAR: already running' "$smoke_log"; then
  printf 'error: ROAR smoke test hit the single-instance guard\n' >&2
  exit 1
fi
if ! grep -Fq 'ROAR: hotkeys registered' "$smoke_log"; then
  printf 'error: ROAR smoke test did not register hotkeys\n' >&2
  exit 1
fi
if ! grep -Fq 'ROAR: clean exit' "$smoke_log"; then
  printf 'error: ROAR smoke test did not exit cleanly\n' >&2
  exit 1
fi

printf 'Verified %s\n' "$target"
