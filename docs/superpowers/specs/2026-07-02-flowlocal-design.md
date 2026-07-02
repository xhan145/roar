# FlowLocal — Design Spec

**Date:** 2026-07-02
**Status:** Approved (user pre-approved all decisions via autonomy directive)
**Goal:** Windows desktop voice-to-text dictation app replicating Wispr Flow's core loop — press hotkey, speak, transcribed text is typed into whatever app has focus — 100% local, free, no telemetry.

## Verified environment facts (2026-07-02)

- Windows 11 Home, Git Bash (MINGW64) shell.
- Python 3.14.5 at `C:\Python314\python.exe` (only interpreter installed; spec's "3.11+" satisfied).
- `faster-whisper 1.2.1` + `ctranslate2 4.8.0` already installed in user site-packages and importable; `ctranslate2.get_cuda_device_count()` returns 1 (NVIDIA GeForce RTX 4060 Laptop GPU).
- `keyboard 0.13.5`, `pystray 0.19.5`, `sounddevice 0.5.5`, `pillow`, `cffi 2.0.0` all resolve for cp314 win_amd64 (pip dry-run verified).
- `gh 2.93.0` authenticated as `xhan145` → private repo creation + push will work.
- Project location: `C:\Users\xhan1\flowlocal`, its own git repo.

## Approach

Python threaded tray app on faster-whisper (spec's stack; chosen over whisper.cpp-native and Tauri because the full dependency chain is already proven working on this machine).

## Architecture

State machine coordinated by `app.py`:

```
IDLE --hotkey down / toggle on--> RECORDING --hotkey up / toggle off--> TRANSCRIBING --inject--> IDLE
                                       |                                     |
                                       +--silence gate reject---------------> IDLE (no injection)
Errors at any point -> tray notification + return to IDLE (never crash)
```

Threads:
1. **Main thread** — pystray icon loop (`icon.run()` blocks; all state changes update the icon via `icon.icon = ...` + `icon.update_menu()`).
2. **keyboard hook thread** — managed by the `keyboard` lib; fires press/release callbacks.
3. **sounddevice callback thread** — appends float32 blocks to the active recording buffer.
4. **Transcription worker thread** — owns the WhisperModel (loaded once at startup, kept warm), consumes a `queue.Queue` of recordings, runs gate → transcribe → command replacement → injection.

## Modules

```
flowlocal/
  app.py            # entry point: single-instance lock, config load, model warmup, tray, hotkey wiring, state machine
  recorder.py       # sounddevice InputStream capture (16 kHz mono float32), RMS energy gate, tone playback
  transcriber.py    # faster-whisper wrapper: device autodetect, model load/reload, transcribe()
  injector.py       # keyboard.write (SendInput unicode) primary; clipboard-paste fallback mode
  commands.py       # spoken-command replacement map + text normalization (pure functions)
  config.py         # load/save config.json with defaults; deep-merge user config over defaults
  tray_icons.py     # Pillow-drawn state icons (no bundled assets)
  tests/
    test_transcriber.py   # SAPI-TTS-generated WAV -> transcribe -> assert words present
    test_gate.py          # zeros buffer rejected; real signal passes
    test_commands.py      # replacement map + normalization
    smoke_app.py          # launches app, asserts startup lines, clean quit
  requirements.txt  # pinned versions
  README.md         # setup <10 steps, hotkeys, models, troubleshooting
  .gitignore        # models/, __pycache__/, venv/, *.wav scratch
  config.json       # generated at first run, gitignored (user-local state)
```

## Key decisions

### Hotkeys
- **Push-to-talk (default `ctrl+windows`):** `keyboard.add_hotkey` can't observe chord *release*, so PTT uses `keyboard.on_press_key`/`on_release_key` low-level tracking: recording starts when both Ctrl and Win are down, stops when either goes up. Debounce: ignore re-press within 150 ms.
- **Toggle (default `ctrl+windows+space`):** standard `keyboard.add_hotkey`. Documented conflict: Win+Ctrl+Space is Windows' input-method-switch shortcut for users with multiple input languages.
- Both hotkeys are strings in config.json; re-registered on config reload.
- No key suppression (suppress=False) — passing Ctrl+Win through to Windows is harmless (no default binding) and suppression risks sticky-modifier bugs.

### Transcription
- Device autodetect at startup: if `ctranslate2.get_cuda_device_count() > 0`, attempt `WhisperModel(model, device="cuda", compute_type="float16")` with default model `distil-large-v3`; on **any** exception (missing cuDNN, OOM), fall back to `device="cpu", compute_type="int8"`, model `small.en`, and notify via tray. GPU fallback also wraps the *first inference*, since some CUDA failures only appear at run time.
- `download_root="models/"` (project-local cache), auto-download on first use.
- Model switch from tray menu re-loads in the worker thread (state → transcribing icon while loading, notification when ready).
- Model menu options: `tiny.en`, `base.en`, `small.en`, `medium.en`, `distil-large-v3`.
- English-only assumption for v0.1 (`.en` models + distil-large-v3 which is multilingual but used with `language="en"`); `language` is a config key for later.

### Injection
- Primary: `keyboard.write(text, delay=0)` — SendInput with KEYEVENTF_UNICODE, works in Electron/browsers/most games.
- Fallback paste mode (config + tray toggle): save clipboard via ctypes (`OpenClipboard`/`GetClipboardData` CF_UNICODETEXT), set transcript, send Ctrl+V, restore prior clipboard after 300 ms.
- Never inject when transcript is empty/whitespace-only.
- A trailing space is appended after every injection.

### Text pipeline (commands.py — pure)
1. Whisper output → `strip()`.
2. Replacement map (case-insensitive, word-boundary): defaults `"new line" → "\n"`, `"new paragraph" → "\n\n"`; user-editable under `config.json:"replacements"`. `keyboard.write` sends `\n` as Enter.
3. Capitalize first alphabetical character if lowercase (Whisper already punctuates).
4. Empty-after-processing → no injection.

### Silence gate (recorder.py)
- Reject if RMS < `0.005` (config: `silence_rms_threshold`) or duration < `0.3 s`.
- Rejected recordings return to IDLE silently (stop tone already played; no error notification).

### Tray UX (per ui-ux-pro-max: state by shape AND color, feedback <100 ms, error = cause + fix, destructive separation)
- Icons drawn by Pillow at 64×64: **idle** gray mic; **recording** red `#DC2626` mic + filled dot; **transcribing** blue `#2563EB` mic + arc; **error** amber `#D97706` mic + exclamation. Error state auto-reverts to idle after notification.
- Menu (top→bottom): status line (disabled, e.g. `Idle — small.en (CPU)`), `Copy last transcript`, `Model ▸` (radio), `Input device ▸` (radio), `Fallback paste mode` (checkbox), `Open config`, separator, `Quit`.
- Tones (recorder.py, sounddevice playback of generated numpy sine, amplitude 0.1): start 880 Hz/80 ms, stop 440 Hz/80 ms, error 220 Hz double-blip. Start tone plays immediately on hotkey press (<100 ms feedback).
- Notifications via `icon.notify(...)`: model fallback, mic missing ("No microphone found — plug one in or pick a device in the tray menu"), single-instance refusal, injection fallback errors.

### Robustness
- **Single instance:** ctypes `CreateMutexW(None, False, "Global\\FlowLocalSingleton")`; if `GetLastError() == ERROR_ALREADY_EXISTS` (183), print + toast + exit 1.
- **No mic / device change:** enumerate devices at record start; failures → error notification, state → IDLE. Device list menu rebuilt on open.
- **All worker exceptions** caught → error icon + notification → IDLE. App never dies from a transcription/injection error.
- **Clean shutdown:** Quit unhooks keyboard, stops stream, stops tray, joins worker (timeout 5 s), releases mutex.

### config.json defaults
```json
{
  "hotkey_ptt": "ctrl+windows",
  "hotkey_toggle": "ctrl+windows+space",
  "model": "auto",
  "input_device": null,
  "paste_fallback": false,
  "silence_rms_threshold": 0.005,
  "min_duration_s": 0.3,
  "tones_enabled": true,
  "language": "en",
  "replacements": { "new line": "\n", "new paragraph": "\n\n" }
}
```
`"model": "auto"` = GPU/CPU autodetect policy above; a concrete model name pins it.

## Testing & verification (all headless-capable, run before done)
1. venv creation + `pip install -r requirements.txt` → zero errors.
2. `tests/test_transcriber.py`: generate speech WAV via PowerShell SAPI (`System.Speech.Synthesis`, no new deps), transcribe, assert expected words in output.
3. `tests/test_gate.py`: all-zeros buffer rejected; synthetic sine + speech passes.
4. `tests/test_commands.py`: replacements, capitalization, empty handling.
5. `tests/smoke_app.py`: launch `app.py` as subprocess, wait for startup markers ("hotkeys registered", "tray ready" on stdout), confirm still alive, terminate, assert clean exit.
6. Live checks on this machine: hotkey registration, tray icon visible, menu actions, real injection into a focused window.

## Git
- Own repo at `flowlocal/`; incremental commits per feature; final commit `flowlocal v0.1.0 — local voice-to-text, verified`; `gh repo create flowlocal --private --source=. --push`.

## Out of scope (v0.1)
- Packaging (PyInstaller), auto-start on login, streaming/partial transcription, multi-language UI, custom vocabulary, GUI settings window (config.json + tray only).
