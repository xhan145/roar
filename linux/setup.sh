#!/usr/bin/env bash
# ROAR setup for Ubuntu 24.04 (X11). Installs system deps, creates a venv with
# --system-site-packages (so PyGObject/webkit2gtk are visible), pip-installs the
# rest, and writes the launcher. Re-runnable.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== ROAR setup (Ubuntu 24.04, X11) =="

SYS_PKGS="python3-venv python3-dev python3-tk python3-gi \
gir1.2-webkit2-4.1 gir1.2-appindicator3-0.1 libportaudio2 xclip xdotool \
libnotify-bin"
echo "System packages needed: $SYS_PKGS"
if command -v apt >/dev/null; then
  sudo apt update
  sudo apt install -y $SYS_PKGS
else
  echo "apt not found — install the above manually" >&2
fi

python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-linux.txt

if command -v nvidia-smi >/dev/null; then
  echo "NVIDIA GPU detected — CUDA acceleration will be used."
  nvidia-smi -L || true
else
  echo "No nvidia-smi found — ROAR will run on CPU (still fully functional)."
fi

mkdir -p "$HOME/.local/bin"
install -m 755 linux/roar "$HOME/.local/bin/roar"
echo "Done. Run:  ~/.local/bin/roar   (or 'roar' if ~/.local/bin is on PATH)"
