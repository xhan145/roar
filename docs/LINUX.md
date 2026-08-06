# ROAR on Linux (Preview — Ubuntu 24.04, X11)

Linux is a **Preview**, not a published release channel. ROAR supports an
x86_64 AppImage build on Ubuntu 24.04 and is intended for an X11/Xorg session.
Wayland is not supported by the current global-hotkey and cross-app injection
implementation; use Xorg for those capabilities.

## Prerequisites

- **Ubuntu 24.04 LTS**, logged into an **X11 ("Ubuntu on Xorg") session**,
  not the default Wayland session. At the GDM login screen, select the gear
  icon and choose **Ubuntu on Xorg** before signing in. `echo
  $XDG_SESSION_TYPE` should print `x11`.
- Python 3.12 (included with Ubuntu 24.04).

## Setup and running from source

From the repository root:

```bash
bash linux/setup.sh
~/.local/bin/roar
```

The setup script installs the Ubuntu package dependencies, creates `.venv`
with system PyGObject/WebKitGTK bindings, installs `requirements-linux.txt`,
and adds `~/.local/bin/roar`.

## Injection escape hatch

Text injection normally uses `pynput`, with a clipboard-paste fallback. If a
particular application mishandles that input, select the `xdotool` backend:

```bash
ROAR_INJECT_BACKEND=xdotool ~/.local/bin/roar
```

## Build and verify the AppImage

The package architecture is **x86_64**. On Ubuntu 24.04, install the build
requirements and use the pinned AppImageTool before building:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-linux.txt -r requirements-linux-build.txt
mkdir -p .tools
curl --fail --location --silent --show-error \
  https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage \
  --output .tools/appimagetool
echo "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0  .tools/appimagetool" | sha256sum --check --status -
chmod +x .tools/appimagetool
APPIMAGETOOL="$PWD/.tools/appimagetool" bash linux/build_appimage.sh
```

Verify the produced package and its sidecar checksum (substitute its version):

```bash
bash linux/verify_appimage.sh dist/ROAR-Linux-<version>-x86_64.AppImage
sha256sum --check <file>.sha256
```

GitHub Actions runs this package build on Ubuntu 24.04 and performs an
automated Xvfb launch smoke. That smoke is not proof of a real microphone,
physical global-hotkey, or cross-app text injection. Those checks remain the
manual release gate on a physical Ubuntu 24.04/Xorg machine.

No Linux release exists until a human creates a draft or prerelease and runs
the manual upload path with its tag; normal CI produces only a verified
workflow artifact.

## Where things live (XDG)

- Config + license: `~/.config/ROAR` (`config.json`, `license.json`)
- Data, history, audio, models, log: `~/.local/share/ROAR`
  (`history.db`, `audio/`, `models/`, `roar.log`)
- Autostart entry: `~/.config/autostart/ROAR.desktop`

## Manual release checklist (Ubuntu 24.04 / X11)

These physical-machine checks are required before calling any Linux package a
release. Report failures with relevant lines from
`~/.local/share/ROAR/roar.log`.

1. `linux/setup.sh` completes; `linux/roar` launches; tray icon appears.
2. **Hotkey:** press push-to-talk, speak, release, and confirm text types into
   **gedit**. Confirm toggle mode and double-tap hands-free also work.
3. **Cross-app injection:** repeat into a browser field and a terminal.
4. **Microphone:** make a real recording and confirm its transcript is typed.
5. Overlay pill shows recording state.
6. Settings render and persist a changed value to `~/.config/ROAR/config.json`.
7. History records entries; deletion and retention toggles work.
8. Enable autostart; confirm `~/.config/autostart/ROAR.desktop` and a log-out/
   log-in launch.
