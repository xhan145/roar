# ROAR Ubuntu Port — Design Spec

**Date:** 2026-07-17
**Target:** Ubuntu 24.04 LTS, X11/Xorg session, Python 3.12
**Scope:** Full feature parity with the Windows app, shipped from the same repo
**Delivery:** Run-from-source (venv + launcher) plus an AppImage build recipe

## Goal

Run ROAR on Ubuntu 24.04 (X11) with the same behavior as Windows: a global
hotkey records speech, transcribes it locally, and types the result into the
focused application — with the tray, overlay, settings window, history,
insights, licensing, and autostart all working. One codebase serves both
operating systems.

## Non-goals (this pass)

- **Wayland.** X11/Xorg only. Wayland blocks global hotkey capture and cross-app
  injection; supporting it needs a root `ydotool` daemon and is deferred.
- **Vulkan GPU.** The Vulkan backend uses Windows-only prebuilt binaries and is
  cleanly unavailable on Linux, not broken. **CUDA is first-class on Linux** (the
  machine has an NVIDIA GPU) — see hardware_accel below; Vulkan is simply not the
  Linux GPU path.
- **A published Linux release / .deb / Flatpak.** Run-from-source + an AppImage
  recipe the owner builds on Ubuntu. No CI Linux build yet.

## Constraints (verbatim, project-wide)

- **Windows must not regress.** Every existing Windows test stays green; Windows
  code paths are unchanged. Platform selection is additive.
- **The settings process must stay ML-free** (existing invariant): the settings
  window runs in a separate process that never imports the transcription stack.
- Privacy model is unchanged: no network except the user-initiated update check
  and first-run model download; licensing never touches transcript/audio/etc.
- The build machine is Windows. The author cannot run, inject-test, or build a
  Linux artifact. Linux-only behavior is verified by the user on Ubuntu against
  a documented checklist; portable *logic* is unit-tested on Windows by mocking
  `sys.platform`.

## Architecture: one codebase, a thin platform seam

ROAR is a set of flat top-level Python modules. Five of them are Windows-coupled.
Rather than fork, each grows a Linux path selected by `sys.platform` at import,
behind the *same* public function names the rest of the app already calls. No
caller changes. Windows imports the Windows backend exactly as today.

Where a platform's implementation is non-trivial (injection, hotkey capture), the
backend lives in its own module so each file has one clear job and can be read in
isolation:

```
injector.py            # public API: type_text(text, mode); picks a backend
  inject_windows.py    # keyboard-lib SendInput (existing behavior, extracted)
  inject_x11.py        # pynput Controller + clipboard-paste fallback (new)
hotkey_listener.py     # public API: start(on_event)/stop(); picks a backend
  hotkeys_windows.py   # keyboard-lib global listener (existing behavior)
  hotkeys_x11.py       # pynput global listener (new)
```

`paths.py`, `autostart.py`, and `hardware_accel.py` are small enough to hold both
platforms in one file with a top-level branch; they stay single files.

`gestures.py` (double-tap / hold timing) is pure logic and is reused unchanged —
only the *source* of key events changes, not the interpretation.

### Backend selection

A single helper decides the platform once:

```python
# platform_id.py
import sys
def is_windows(): return sys.platform.startswith("win")
def is_linux():   return sys.platform.startswith("linux")
```

Each dispatching module imports this and selects its backend. Selection is
overridable by an env var `ROAR_INJECT_BACKEND` (`pynput` | `xdotool`) so the
user can switch injection method without a code change if pynput misbehaves.

## Component designs

### 1. paths.py — XDG directories

Add a Linux branch to every path function. Windows branch untouched.

| Purpose | Windows | Linux (XDG, 24.04) |
|---|---|---|
| config.json | `%APPDATA%\ROAR` | `$XDG_CONFIG_HOME/ROAR` else `~/.config/ROAR` |
| license.json | `%APPDATA%\ROAR` (beside config) | `~/.config/ROAR` (beside config) |
| legacy_grant.json | `%APPDATA%\ROAR` | `~/.config/ROAR` |
| data root (history, audio, log) | `%LOCALAPPDATA%\ROAR` | `$XDG_DATA_HOME/ROAR` else `~/.local/share/ROAR` |
| models | `%LOCALAPPDATA%\ROAR\models` | `~/.local/share/ROAR/models` |

The invariant that the **license lives beside config, NOT in the data dir that
history/audio clears touch**, is preserved: on Linux config dir = `~/.config/ROAR`,
data dir = `~/.local/share/ROAR`, and they are distinct.

`os.makedirs(..., exist_ok=True)` on first use (already the pattern). No
migration needed — Linux is a fresh install with no prior `%APPDATA%`.

**Tests (Windows-runnable):** monkeypatch `sys.platform="linux"` and the XDG env
vars; assert each path resolves under `~/.config/ROAR` or `~/.local/share/ROAR`,
that `$XDG_CONFIG_HOME`/`$XDG_DATA_HOME` override the defaults, and that license
path is under the config dir, never the data dir.

### 2. injector.py — typing into the focused app

Public API stays `type_text(text, mode=...)`. On Linux:

- **Primary — pynput:** `pynput.keyboard.Controller().type(text)` sends Unicode to
  the focused X11 window without root. Mirrors the Windows unicode-typing path.
- **Fallback — clipboard paste:** `pyperclip.copy(text)` then pynput
  `Ctrl+V`, then restore the previous clipboard after a short delay (same shape
  as the Windows fallback). pyperclip uses `xclip`/`xsel` on Linux.
- **Optional — xdotool:** if `ROAR_INJECT_BACKEND=xdotool` or pynput import
  fails, shell out to `xdotool type --clearmodifiers -- <text>`. Robust for
  Unicode edge cases.

Backend chosen at import; failures degrade (pynput → clipboard) and are logged,
never raised, so a stuck injection can't crash dictation.

**Tests:** backend *selection* logic (env var, platform) with the actual
injectors monkeypatched. Real typing is on the Ubuntu checklist (type into
gedit / a browser field).

### 3. hotkey_listener.py — global push-to-talk / toggle (RELIABILITY IS THE PRIORITY)

The global hotkey is the make-or-break of a dictation app; on Linux it must be
rock-solid. It is the **#1 must-pass** item on the Ubuntu checklist.

Extract the global-key listener currently inline in `app.py` behind
`start(on_event)` / `stop()`. Windows backend wraps the `keyboard` lib (today's
behavior). Linux backend uses `pynput.keyboard.Listener`, which captures global
key events on X11 without root. Events feed the existing `gestures.py` timing
logic unchanged, preserving push-to-talk, toggle, and double-tap hands-free.

Reliability requirements for the X11 backend:

- **Never miss or wedge the key.** The listener runs on its own thread; a slow
  transcription must not block key events. Key-down/up are delivered to
  `gestures.py` promptly so hold/double-tap timing stays accurate.
- **Clean start/stop and restart.** `stop()` fully tears down the pynput listener
  (no leaked X grabs); the listener can be restarted (e.g. after a settings
  change) without a process restart.
- **Self-heal.** If the pynput listener thread dies, log it and attempt one
  restart rather than silently going deaf; surface a tray/notification if it
  can't recover, so the user is never left with a dead hotkey and no signal.
- **Modifier hygiene.** Release-all-modifiers semantics match Windows so a held
  modifier from the trigger never leaks into the injected text.

`app.py` changes from calling `keyboard` directly to calling `hotkey_listener`.
This is the one shared-file edit; it must keep Windows behavior identical
(verified by the existing Windows hotkey/gesture tests).

**Tests:** existing gesture tests unchanged (pure logic). Add tests that `app.py`
drives `hotkey_listener.start/stop` via the seam (fake backend), that `stop()`
after `start()` releases the backend, and that a simulated backend-thread death
triggers exactly one restart attempt.

### 4. autostart.py — login autostart

Windows: `winreg` Run key (unchanged). Linux: write / remove
`~/.config/autostart/roar.desktop` (XDG autostart spec). The `.desktop` contents:

```
[Desktop Entry]
Type=Application
Name=ROAR
Exec=<launcher path>
X-GNOME-Autostart-enabled=true
```

`is_enabled()` checks file existence; enable writes it; disable removes it.

**Tests (Windows-runnable):** generate the `.desktop` text and assert its fields
and the target path; assert enable-then-disable round-trips using a temp HOME.

### 5. hardware_accel.py — device selection (CUDA is first-class)

The Ubuntu machine has an **NVIDIA GPU**, so CUDA is a first-class supported
backend on Linux, not a best-effort auto-detect:

- **Backend selection:** on Linux, probe for CUDA (CTranslate2 `device="cuda"`
  usable — the NVIDIA runtime libs are importable and `nvidia-smi` present) and
  **prefer GPU** when available, exactly like the Windows CUDA fast path. Fall
  back to tuned CPU if the probe fails, logged clearly.
- **How CUDA reaches CTranslate2 on Linux:** faster-whisper/CTranslate2 need the
  CUDA 12 cuBLAS + cuDNN runtime. Rather than depend on a system CUDA install,
  `setup.sh` pip-installs the `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` wheels
  into the venv (the vendor-supported recipe), and CTranslate2 loads them. The
  host only needs a recent **NVIDIA driver** (`setup.sh` checks `nvidia-smi` and
  warns if absent, continuing with CPU).
- **No Vulkan on Linux** — filtered out of `available_backends()` so the settings
  UI never offers it. CPU threading tuning still applies as the fallback.

**Tests (Windows-runnable):** on Linux, `available_backends()` excludes Vulkan,
includes CPU, and includes CUDA when the probe succeeds (probe monkeypatched);
device preference resolves to `cuda` when CUDA is present and `cpu` otherwise.

### 6. Shared UI — code reused, system deps added

No code fork for these; they need Linux system packages:

- **overlay.py** (tkinter status pill): needs `python3-tk`. Borderless
  always-on-top window works on X11. Risk: some GNOME setups mishandle
  always-on-top — noted, fallback is the tray.
- **tray** (pystray): uses the AppIndicator backend on Linux; needs
  `gir1.2-appindicator3-0.1` + `libappindicator`. Menu updates go through the GTK
  main loop.
- **settings window** (pywebview, separate ML-free process): on 24.04 needs the
  **GTK 4.1** stack — `python3-gi`, `gir1.2-webkit2-4.1`, `libwebkit2gtk-4.1`. Use
  `pywebview>=5` (supports webkit2gtk-4.1). This is the highest-risk dependency
  and the setup script handles it explicitly.
- **recorder.py** (sounddevice): needs `libportaudio2`.

## Dependencies

**pip (into the venv):** the existing requirements plus `pynput` and `pyperclip`;
`pywebview>=5`; `PyGObject` (if not using system `python3-gi`); existing
`sounddevice`, `faster-whisper`, `pystray`, `pillow`, `numpy`.

**apt (system):** `python3-venv python3-dev python3-tk python3-gi
gir1.2-webkit2-4.1 gir1.2-appindicator3-0.1 libportaudio2 xclip xdotool
libnotify-bin`.

Pip vs system split for PyGObject/webkit is the classic Linux friction point;
`linux/setup.sh` prefers system `python3-gi` and creates the venv with
`--system-site-packages` so the GI bindings are visible, which is the reliable
recipe on 24.04.

## Packaging & delivery

New `linux/` directory:

- **`setup.sh`** — verifies/apt-installs system deps (prompts before sudo),
  creates the venv (`--system-site-packages`), pip-installs requirements, prints
  the run command. Idempotent.
- **`roar`** — launcher script: activates the venv, `exec python app.py "$@"`.
- **`roar.desktop`** — menu/desktop entry pointing at the launcher (also the
  template autostart.py writes).
- **`build_appimage.sh`** — PyInstaller onedir build + `appimagetool` recipe,
  run by the owner on Ubuntu when a portable artifact is wanted. Documented as
  unverified-from-Windows.
- **`icon` assets** — reuse existing brand PNGs for the desktop entry / tray.

`docs/LINUX.md` — prerequisites, `setup.sh` usage, the run command, and the
**smoke-test checklist** (below).

## Testing strategy

**Author, on Windows — must all pass before handoff:**
- The full existing suite (485 pass, 1 skip) stays green — Windows untouched.
- New unit tests for portable logic, all via mocked `sys.platform`/env:
  XDG path resolution, `.desktop` generation + round-trip, backend-selection for
  injector/hotkey/hardware_accel, Vulkan-excluded-on-Linux.

**User, on Ubuntu 24.04 (X11) — the smoke checklist in docs/LINUX.md:**
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
9. Enable autostart → `~/.config/autostart/roar.desktop` exists; log out/in →
   ROAR starts.

## Risks (build-blind)

| Risk | Likelihood | Mitigation |
|---|---|---|
| pywebview/webkit2gtk-4.1 binding mismatch | High | `--system-site-packages` venv + system `python3-gi`/`gir1.2-webkit2-4.1`; documented fallback to the Qt backend |
| pynput `.type()` Unicode quirks | Medium | clipboard-paste + `xdotool` backends via `ROAR_INJECT_BACKEND` |
| pynput global listener misses keys / thread dies | Medium | dedicated listener thread; one-shot self-heal restart; tray/notify on unrecoverable — hotkey is the #1 must-pass |
| CUDA libs/driver mismatch on Linux | Medium | pip `nvidia-cublas-cu12`+`nvidia-cudnn-cu12` into venv; `setup.sh` checks `nvidia-smi`; clean CPU fallback |
| pystray AppIndicator menu refresh quirks | Medium | GTK main-loop threading care; tray is non-critical vs the hotkey path |
| tkinter overlay not staying on top on GNOME | Low–Med | overlay is cosmetic; tray + sounds remain |
| Author cannot verify Linux runtime | Certain | tight checklist + logged, non-fatal failures + env-var backend switches |

## Rollout

Land behind the platform seam so Windows ships unchanged. No version bump gating
required for Windows; the Linux support is a new capability of the same codebase.
A `linux`-tagged section in CHANGELOG documents it as experimental / test-on-24.04.
