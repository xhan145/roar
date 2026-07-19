# ROAR on Linux (experimental — Ubuntu 24.04, X11)

ROAR runs from the same codebase on Ubuntu 24.04 with an X11/Xorg session:
global hotkey, local transcription, and text injection into the focused
window, plus the tray, overlay, settings window, history, and autostart. This
is **run-from-source** (a build recipe for a portable AppImage is included but
unverified by the author — see `linux/build_appimage.sh`).

**Not supported (this pass):** Wayland. X11/Xorg only — Wayland blocks global
hotkey capture and cross-app text injection without a root helper. Log in on
Xorg (see below).

## Prerequisites

- **Ubuntu 24.04 LTS**, logged into an **X11 ("Ubuntu on Xorg") session**, not
  the default Wayland session:
  - At the GDM login screen, click your username, then click the gear icon in
    the bottom-right corner of the password field and choose **"Ubuntu on
    Xorg"** before entering your password.
  - To confirm you're on X11 after logging in: `echo $XDG_SESSION_TYPE` should
    print `x11`.
- Python 3.12 (Ubuntu 24.04 ships this by default).
- An NVIDIA GPU is optional but recommended — `setup.sh` uses it automatically
  if present (CUDA is first-class on Linux; Vulkan is Windows-only and is not
  offered here).

## Setup

From the repo root:

```bash
bash linux/setup.sh
```

This is idempotent and will:
- apt-install system dependencies (prompts for `sudo`): `python3-venv
  python3-dev python3-tk python3-gi gir1.2-webkit2-4.1
  gir1.2-appindicator3-0.1 libportaudio2 xclip xdotool libnotify-bin`
- create a venv at `.venv` with `--system-site-packages` (so the system
  PyGObject/WebKitGTK bindings are visible to it)
- pip-install `requirements-linux.txt` into that venv, including the CUDA
  runtime wheels (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) needed for
  GPU transcription
- check for `nvidia-smi` and report whether GPU acceleration will be used
- install the launcher to `~/.local/bin/roar`

## Running

```bash
~/.local/bin/roar
```

(or just `roar` if `~/.local/bin` is on your `PATH`). The tray icon should
appear; use the hotkey to dictate.

## Injection escape hatch

Text injection normally uses `pynput` to type Unicode into the focused
window, with a clipboard-paste fallback. If a particular app mishandles
`pynput`'s typing (rare, app-specific), switch to the `xdotool` backend
without any code change:

```bash
ROAR_INJECT_BACKEND=xdotool ~/.local/bin/roar
```

## GPU note

- Check the driver is visible: `nvidia-smi` should list your GPU.
- Check ROAR picked it up: look for `device=cuda` in
  `~/.local/share/ROAR/roar.log`.
- If neither shows CUDA, ROAR has cleanly fallen back to CPU — dictation still
  works, just slower per clip.

## Where things live (XDG)

- Config + license: `~/.config/ROAR` (`config.json`, `license.json`)
- Data, history, audio, models, log: `~/.local/share/ROAR`
  (`history.db`, `audio/`, `models/`, `roar.log`)
- Autostart entry: `~/.config/autostart/ROAR.desktop`

## Smoke-test checklist (run on Ubuntu 24.04 / X11)

This is the human verification pass — the author builds on Windows and cannot
run, inject-test, or build a Linux artifact directly, so this checklist is the
final gate before calling Linux support solid. Report any failure with the
relevant lines from `~/.local/share/ROAR/roar.log`.

1. `linux/setup.sh` completes; `linux/roar` launches; tray icon appears.
2. **(MUST PASS) Hotkey:** press push-to-talk, speak, release → text types into
   **gedit**; toggle mode and double-tap hands-free both work; the hotkey keeps
   working after several dictations and after opening/closing Settings.
3. Injection works cross-app: repeat into a browser field and a terminal.
4. **GPU:** the log shows `device=cuda`; a clip transcribes markedly faster than
   CPU (confirm `nvidia-smi` shows the process). Force `device=cpu` still works.
5. Overlay pill shows recording state.
6. Open Settings (tray → Settings) — the pywebview window renders; change a
   setting; it persists to `~/.config/ROAR/config.json`.
7. History records entries; delete history and audio; retention toggles work.
8. Import a signed license (`issue_license.py` output) → edition activates.
9. Enable autostart → `~/.config/autostart/ROAR.desktop` exists; log out/in →
   ROAR starts.
