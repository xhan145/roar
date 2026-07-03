# FlowLocal

Local, free voice-to-text dictation for Windows — a [Wispr Flow](https://wisprflow.ai)-style experience with zero cloud. Hold a hotkey, speak, release: your words are typed into whatever app has focus (browser, DAW, Discord, VS Code, games in windowed mode, anything).

**Everything runs on your machine.** No cloud APIs, no API keys, no subscription, no telemetry. Audio never leaves your computer. Transcription is [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI Whisper via CTranslate2).

## Install

1. Install [Python 3.11+](https://www.python.org/downloads/) (tested on 3.14).
2. Clone or download this repo, then open a terminal in the `flowlocal` folder.
3. `python -m venv venv`
4. `venv\Scripts\python.exe -m pip install -r requirements.txt` (Git Bash: `venv/Scripts/python.exe`)
5. *(Optional, NVIDIA GPU)* `venv\Scripts\python.exe -m pip install -r requirements-gpu.txt` — enables CUDA for ~5-10× faster, higher-quality transcription.
6. `venv\Scripts\python.exe app.py`
7. First run downloads the Whisper model to `models/` (small.en ~460 MB on CPU, distil-large-v3 ~1.5 GB on GPU). Wait for the tray icon to turn from gray "loading" to gray "idle".
8. Hold **Ctrl+Win**, speak, release. Your words appear at the cursor.

## Hotkeys

| Hotkey | Action |
|---|---|
| **Ctrl+Win** (hold) | Push-to-talk: record while held, transcribe + type on release |
| **Ctrl+Win+Space** | Toggle: start a longer dictation session; press again to stop |

Both are configurable in `config.json` (`hotkey_ptt`, `hotkey_toggle`), using [`keyboard`](https://github.com/boppreh/keyboard) key names.

> **Note:** Win+Ctrl+Space is also the Windows shortcut to switch input methods. If you use multiple input languages, change `hotkey_toggle`.

## Settings

Tray icon → **Settings…** opens the settings window (dark "Deep Focus" UI):

- **Instant apply:** start with Windows, tones, paste fallback, silence sensitivity, microphone.
- **Apply button:** hotkeys (click *Set*, hold the combo you want) and model — the tray app picks changes up within a couple of seconds, no restart.
- **Privacy** and **History** tabs are placeholders for upcoming features.

Settings write to the same `config.json` — hand edits also hot-apply while the app runs.

### History & Privacy

- **History tab:** every dictation is saved locally (on by default) — reverse-chronological list with copy and per-item delete, plus Clear all.
- **Privacy tab:** turn history off entirely; choose how long to keep the **audio** of each dictation (Off / 1 / 7 / 30 / 90 days — Off deletes audio the instant it's transcribed, which is the default); a live storage stat; and a Delete-all-history-&-audio button.
- Data lives in `%LOCALAPPDATA%\FlowLocal` (`history.db` + `audio\`). It is **kept when you uninstall the MSI** — delete that folder by hand if you want it gone. Nothing is ever uploaded.

## Tray icon

The microphone icon shows state by color **and** shape: gray = idle, gray + arc = loading, red + dot = recording, blue + arc = transcribing, amber + ! = error. Menu:

- **Status line** — current state, model, device (cpu/cuda)
- **Copy last transcript** — puts the last dictation on the clipboard
- **Model** — switch between tiny.en / base.en / small.en / medium.en / distil-large-v3 / auto
- **Input device** — pick a microphone
- **Fallback paste mode** — paste via clipboard (Ctrl+V) instead of typing, for apps that block synthetic keystrokes; your previous clipboard is restored
- **Open config** — opens `config.json` in Notepad (restart FlowLocal to apply edits)
- **Quit**

## Models

`"model": "auto"` (default) picks by hardware: NVIDIA GPU → **distil-large-v3** (float16), otherwise **small.en** (int8). Measured on an RTX 4060 Laptop / Ryzen laptop, ~4-second clip, warm model:

| Model | Device | Latency | Notes |
|---|---|---|---|
| distil-large-v3 | cuda | **~0.3 s** | best accuracy, needs `requirements-gpu.txt` |
| small.en | cpu | **~1.7-1.9 s** | good accuracy, default CPU pick |
| tiny.en / base.en | cpu | faster | quick notes, lower accuracy |
| medium.en | cpu | slower | only if CPU accuracy matters more than speed |

## Spoken commands

Say **"new line"** for Enter, **"new paragraph"** for a blank line. Edit or add your own in `config.json` under `"replacements"` (spoken phrase → replacement text).

## config.json reference

Generated next to `app.py` on first run:

| Key | Default | Meaning |
|---|---|---|
| `hotkey_ptt` | `"ctrl+windows"` | push-to-talk chord (hold) |
| `hotkey_toggle` | `"ctrl+windows+space"` | toggle-session hotkey |
| `model` | `"auto"` | Whisper model, or `auto` for hardware pick |
| `input_device` | `null` | sounddevice input index; `null` = system default |
| `paste_fallback` | `false` | inject via clipboard paste instead of typing |
| `silence_rms_threshold` | `0.005` | recordings quieter than this are discarded |
| `min_duration_s` | `0.3` | recordings shorter than this are discarded |
| `tones_enabled` | `true` | start/stop/error beeps |
| `language` | `"en"` | transcription language hint |
| `replacements` | new line / new paragraph | spoken-command map |

## Troubleshooting

- **"No microphone found"** — plug one in or pick another device in the tray menu.
- **Nothing typed in some app** — that app blocks synthetic keystrokes (some games, admin windows). Enable **Fallback paste mode** in the tray menu. For admin windows, run FlowLocal as administrator.
- **"loading … on cuda" then falls back to CPU** — install the GPU extras: `pip install -r requirements-gpu.txt`.
- **Dictation is cut off / ignored** — clips under 0.3 s or near-silence are dropped by design; lower `silence_rms_threshold` if your mic is very quiet.
- **"already running — exiting"** — FlowLocal is single-instance; check the tray for the existing icon.
- **Hotkey conflicts** — change `hotkey_ptt` / `hotkey_toggle` in `config.json` and restart.

## Packaged app (no Python needed)

Build a standalone `FlowLocal.exe` (one-dir bundle, ~1.5 GB with GPU support included):

```
venv\Scripts\python.exe -m pip install -r requirements-build.txt
venv\Scripts\python.exe scripts\make_icon.py
venv\Scripts\python.exe -m PyInstaller flowlocal.spec --noconfirm
```

The app lands in `dist\FlowLocal\FlowLocal.exe` — copy or zip the whole `dist\FlowLocal` folder; it runs on machines without Python. Notes:

- The exe is **windowed** (no console). Logs go to `%LOCALAPPDATA%\FlowLocal\flowlocal.log`.
- Config lives at `%APPDATA%\FlowLocal\config.json`; models download to `%LOCALAPPDATA%\FlowLocal\models` on first run.
- CUDA DLLs are bundled (spec prunes ~780 MB of cuDNN kernels Whisper doesn't use). On machines without an NVIDIA GPU it falls back to CPU automatically.
- One-dir (not one-file) is deliberate: a one-file exe would re-extract the GB-scale bundle on every launch.

### MSI installer

`bash scripts/build_msi.sh` builds `dist/FlowLocal-0.2.0.msi` (WiX 3.14 downloads automatically on first run). Per-user install — no admin needed: files go to `%LOCALAPPDATA%\Programs\FlowLocal` with a Start Menu shortcut; uninstall from Windows Settings → Apps.

## Development

Run the test suite (65 tests: unit + real-speech transcription + focused-window injection + history/capture integration + app and settings smoke tests). The injection tests type into a small window they open — they skip with a notice if the desktop is busy:

```
venv\Scripts\python.exe -m pytest tests/ -v
```
