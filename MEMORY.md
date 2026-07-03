# ROAR — Project Memory (for any AI assistant)

Read this first. It is the single source of accumulated context for this repo —
architecture, hard-won invariants, and exact recipes. Follow it literally;
every rule below exists because violating it already broke something once.

## Identity

- **Product: ROAR** — local, free Windows voice-to-text tray app (Wispr Flow
  style): hold a hotkey, speak, release → text is typed into the focused app.
  100% local (faster-whisper), no cloud, no telemetry.
- Renamed from "FlowLocal" at v0.6.0. Repo: **github.com/xhan145/roar**
  (old `flowlocal` URL redirects). Local folder is still
  `C:\Users\xhan1\flowlocal` — **never rename the folder**: the venv uses
  absolute paths and would break.
- Version history: v0.1.0 core app → v0.2.0 settings window → v0.3.0 history+
  privacy → v0.4.0 insights+profile+search → v0.5.0 custom vocabulary/hotwords
  → v0.6.0 product rename → v0.7.0 streaming preview + waveform pill + chimes.
  Tags exist for each.
- Roadmap (user wants all): **SP6 multilingual** remains.

## Environment

- Windows 11, Python **3.14.5**, venv at `venv/` — always invoke
  `venv/Scripts/python.exe` directly (never rely on activation).
- Git Bash quirks: `cd /c/Users/xhan1/flowlocal` does NOT persist between tool
  invocations; msiexec flags need `//i` `//x` `//qn` (double slash) in Git
  Bash, or use PowerShell `Start-Process msiexec -ArgumentList '/i',...`.
- Key pins: faster-whisper 1.2.1, ctranslate2 4.8.0, pywebview 6.2.1,
  PyInstaller 6.21.0, pytest 9.1.1 (see requirements*.txt; GPU DLLs in
  requirements-gpu.txt). WiX 3.14 auto-downloads to `build/wix/` on first
  MSI build.
- Machine has an RTX 4060 Laptop GPU: model policy "auto" = `distil-large-v3`
  float16 on cuda (~0.3 s/clip warm), CPU fallback `small.en` int8 (~1.7 s).

## Architecture

Two processes, one config file:

- **Tray app** (`app.py`, `ROAR.exe`): state machine IDLE→RECORDING→
  TRANSCRIBING→IDLE. Threads: pystray main loop; `keyboard` hook thread
  (PTT chord = press/release tracking, toggle = add_hotkey); sounddevice
  callback; ONE worker thread that owns the warm WhisperModel and consumes a
  job queue (`("transcribe", audio)` / `("reload", model)`); config-watcher
  thread (content-hash poll every 2 s + hourly audio purge + hotwords rebuild).
- **Settings window** (`app.py --settings` → `settings_ui.py` +
  `settings.html`): separate process, pywebview (WebView2), JS↔Python bridge
  (`SettingsAPI`). Writes config.json; the tray app hot-applies via
  `diff_config(old,new) -> [(action, arg)]` (rehook / reload_model /
  set_device / rebuild_hotwords; instant keys are read at use time).
- Module map: `recorder.py` (16 kHz mono capture, RMS gate, tones),
  `transcriber.py` (model mgmt, CUDA→CPU fallback, `.hotwords` attr),
  `injector.py` (SendInput typing; clipboard-paste fallback restores clipboard
  after 0.8 s), `commands.py` (pure text pipeline: replacements→capitalize),
  `history.py` (SQLite WAL store + retained WAVs), `insights.py` (pure
  analytics: totals/activity/WPM/top+signature words/profile sentences),
  `vocabulary.py` (pure merge/validate), `hotkeys.py` (chord parsing — exists
  so the settings process NEVER imports the ML stack), `paths.py` (identity,
  frozen paths, legacy migration), `autostart.py` (HKCU Run key),
  `tray_icons.py` (Pillow state icons: state = shape AND color).

## Data locations

- Source mode: everything project-local (config.json, history.db, models/).
- Frozen (installed/dist exe): config `%APPDATA%\ROAR\config.json`; data
  `%LOCALAPPDATA%\ROAR\` → `history.db` (schema `user_version=2`), `audio/`,
  `models/` (~1.9 GB), `roar.log` (windowed exe has no stdout — all markers
  go here). User data SURVIVES MSI uninstall by design.
- Legacy FlowLocal data preserved at `FlowLocal.pre-roar-backup*` in both
  AppData roots — never delete.
- The user's real config: custom hotkey `ctrl+shift`, input_device 8, tuned
  silence threshold, 7-day audio retention, vocabulary. **Never clobber the
  live config with defaults.**

## Invariants (violations have already caused real bugs)

1. **Path getters in `paths.py` are PURE** — they never create directories;
   only writers create (config.save, redirect log open, History._open, audio
   write). Reason: `config.py` computes `PATH` at IMPORT time; a dir-creating
   getter pre-created `%APPDATA%\ROAR` and silently defeated
   `migrate_legacy_data` ("both dirs exist"). Regression-tested.
2. **`migrate_legacy_data()` runs FIRST in `main()`** — before
   `redirect_output_when_frozen()` (which opens the log = creates the dir).
3. **`os._exit(0)` after `app.run()` is mandatory** — ctranslate2/onnxruntime/
   PortAudio native threads crash interpreter finalization ~1/3 runs
   (0xC000041D, no Python frame). Orderly cleanup happens in `_quit` first.
4. **Config watcher compares file CONTENT (sha1), not mtime** — this
   filesystem's mtime granularity (~10 ms) swallowed back-to-back writes.
5. Locks: `state_lock` (RLock) guards state transitions incl. `_set_state`;
   `cfg_lock` (RLock) serializes menu-handler vs watcher config writes;
   settings bridge `_cfg_lock` serializes read-modify-write (pywebview runs
   EACH JS call on its own thread); History has an internal lock,
   `check_same_thread=False`, WAL for cross-process reads.
6. History semantics: transcripts are ALWAYS kept; `audio_retention_days` 0 =
   never write audio + purge existing; purge nulls `audio_path`, never deletes
   rows; `record()` is failure-isolated (a DB/disk error must never break
   dictation); corrupt DB → moved aside `.corrupt-<ts>`, never deleted.
7. Hotwords: merged string = custom first + top-10 signature words, cap 60,
   case-insensitive dedupe, `None` when empty. **Phrases are allowed** —
   faster-whisper injects hotwords as prompt text (they are NOT split on
   spaces; a past reviewer claimed otherwise and was wrong). Rebuilt at model
   load, every 25th dictation, and on config change.
8. `config.load()` sanitizes: `replacements` = str→str only;
   `custom_vocabulary` = list of non-empty strings only (a hand-edited bare
   string must not become per-character hotwords). Corrupt JSON → defaults,
   user file left untouched.
9. Settings UI: all dynamic text via `textContent` (never innerHTML with
   data); **Cinema Dark tokens since v0.8.0**: body gradient #0a0a0f→#020203,
   surface rgba(255,255,255,.05), border rgba(255,255,255,.08), text #EDEDEF
   / muted #8A8F98 / disabled #6A7080 (≥3:1), accent #5E6AD2 (indigo,
   app-wide incl. tray + app icon; recording red / error amber stay
   semantic), chart bars #7B85E2 at FULL opacity (opacity composites broke
   3:1 — computed, not guessed), radius 16 cards / 24 pill, inline SVG
   sidebar icons (1.5px stroke), no emoji-as-icon. pywebview window chrome
   `background_color` must match bg-deep #020203. Sidebar has 8 nav entries.
   ALSO: the user edits this repo from GitHub web — `git fetch` before
   pushing, and MERGE (never rebase) when a tag already points at a local
   commit.
10. Smoke-test stdout markers are EXACT strings — `ROAR: hotkeys registered`,
    `ROAR: tray ready`, `ROAR: model loaded`, `ROAR: clean exit`,
    `ROAR: settings window ready`, probe line
    `ROAR: settings probe navs=8 version=<v> priv=1 privnav=1 insnav=1 vocab=1`.
    The probe CLICKS tabs (existence checks once missed disabled nav buttons).
11. Version single-source: `paths.APP_VERSION`. MSI version is templated from
    it (`-dAppVersion`); tests assert it; bump it for every release.
12. Installer: UpgradeCode `a7a83e4a-83a0-4834-8edc-8dc058eb254f` — NEVER
    change it (upgrade continuity). `AllowSameVersionUpgrades` is on. Per-user
    scope, no admin. **KILL the installed app + its webviews BEFORE any MSI
    upgrade** — a running ROAR.exe holds pythonnet DLLs → Error 1304 → 1603
    with the old product already removed (no effective rollback; reinstall
    fresh after clearing + deleting the leftover Programs\ROAR tree).
13. Streaming/overlay (v0.7.0): the worker NEVER sleeps for pacing — partials
    self-reschedule via daemon `threading.Timer`; a session `_session_gen`
    counter (bumped in `_finish_recording`) makes stale partials no-ops; the
    worker's IDLE reset is skipped for `("partial", gen)` jobs (state must
    stay RECORDING). `overlay.py` is COSMETIC-ONLY: Tk on a dedicated thread,
    all Tk calls thread-confined via a command queue, adaptive tick (33 ms
    visible / 250 ms hidden), every public method exception-proof. `roar.spec`
    must NOT exclude tkinter (overlay needs it). TONES are `make_chime`
    envelopes (C5→E5 start, E5→C5 stop, double 165 Hz error), amp ≤ 0.08.
    When killing processes by command-line filter in PowerShell, exclude the
    current shell — the filter string itself matches (self-kill incident).

## Build & release recipes

- Tests: `venv/Scripts/python.exe -m pytest tests/ -q` (102 tests). Kill
  `ROAR.exe` first (single-instance mutex + keyboard hooks). Injection tests
  probe for desktop focus and SKIP (not fail) when the user is active; Tk
  init has a retry (transient Tcl race).
- Exe: `venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm` →
  `dist/ROAR/ROAR.exe`. Before building: kill ROAR.exe AND its
  `msedgewebview2.exe` children (they lock `dist/ROAR/_internal` DLLs —
  filter `Win32_Process` by CommandLine containing ROAR).
- MSI: `bash scripts/build_msi.sh` → `dist/ROAR-<ver>.msi` (~710 MB, ~7 min).
  Writes `.msi.building` then atomic rename; purges superseded MSIs.
  **NEVER run two MSI builds (or MSI + exe build) concurrently** — two
  710 MB light.exe compressions exhausted Windows commit memory (Win32 1455)
  and killed random processes.
- Verify per-user install state via COM `Installer.ProductsEx("","",2)` —
  the legacy `Installer.Products` API and naive HKCU Uninstall queries MISS
  per-user MSI registrations.
- Upgrade verification pattern: install over previous → exit 0 → exactly ONE
  product at the new version → old Programs dir gone → installed
  `--settings --smoke` probe green (read `%LOCALAPPDATA%\ROAR\roar.log`) →
  history rows + custom config keys preserved.
- Release train (established): suite ×2 (check EXIT CODES, `| tail` masks
  them) → exe → MSI → upgrade verify → adversarial review → fix → push →
  empty release commit + tag `vX.Y.Z` → push --tags → relaunch installed exe.
  `git status` before any `git add -A` (review agents leave scratch files).

## Testing aids

- Headless speech: generate WAVs via Windows SAPI PowerShell
  (`System.Speech.Synthesis`) — reliable. Speaker→mic loopback is UNRELIABLE
  on this machine (volume/routing) — don't gate releases on it; drive the
  transcriber directly with the WAV instead.
- Deterministic injection test: tkinter Entry + focus probe (see
  tests/test_injector.py).

## Process conventions

- Specs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`
  (dated). Cycle per feature: spec → plan → TDD implementation → adversarial
  review → release train. Incremental commits per task.
- The user prefers momentum: present a design with recommended defaults and
  proceed on approval ("yes"/"go"); pause only for genuinely user-owned
  choices or destructive actions.
