# Context-Aware Formatting (SP13) — Design

**Version:** v0.15.0 (also releases the built-but-unshipped v0.14.0 double-tap)
**Date:** 2026-07-04
**Status:** approved — deliberately small ("fast and short")

## Goal

The focused app decides how dictation is formatted: verbatim in code editors /
terminals, terser in chat apps, normal everywhere else. 100% local — the only
new input is the foreground process name, which ROAR already has access to.

## Scope (minimal)

Two built-in profiles that each do something distinct; everything else uses the
user's own settings. No per-app custom UI in v1.

| Profile | Apps (exe basename) | Overrides |
|---|---|---|
| `code` | code.exe, code - insiders.exe, devenv.exe, pycharm64.exe, idea64.exe, sublime_text.exe, windowsterminal.exe, cmd.exe, powershell.exe, pwsh.exe, conhost.exe, wezterm-gui.exe | `capitalize=False`, `cleanup=False` (exact words, no auto-cap — code/commands are case-sensitive) |
| `chat` | slack.exe, discord.exe, teams.exe, ms-teams.exe, telegram.exe, whatsapp.exe | `discourse_fillers=True` (force filler removal for terse messages) |
| _default_ | anything else | `{}` — use the user's cleanup/capitalize settings |

## Components

- **`context.py`** (pure): `profile_for(exe_name) -> dict` maps a lowercased exe
  basename to its override dict (or `{}`). No I/O.
- **`commands.process`**: gains `capitalize=True` param gating the first-letter
  uppercase pass (backward compatible; existing callers unaffected).
- **`app.py`**: new `_foreground_exe()` (ctypes: `GetForegroundWindow` →
  `GetWindowThreadProcessId` → `OpenProcess(0x1000)` →
  `QueryFullProcessImageNameW`; try/except → `""`). In `_handle_transcription`,
  after the scratch check, compute `prof = context.profile_for(self._foreground_exe())`
  when `context_aware` is on, and pass profile-overridden `cleanup` /
  `discourse_fillers` / `capitalize` into `commands.process`.
- **`config.py`**: `context_aware: True` default; bool-coerced on load; added to
  the settings bridge `INSTANT_KEYS`. (No settings-tab toggle in v1 — controllable
  via config / bridge; keeps this fast.)

## Testing

- `tests/test_context.py`: `profile_for` for a code exe, a chat exe, unknown,
  empty/None, case-insensitivity.
- `tests/test_commands.py`: `process(..., capitalize=False)` leaves case;
  default still capitalizes.
- `tests/test_capture_integration.py`: stub `_foreground_exe` → `code.exe`
  yields un-capitalized injected text; `context_aware=False` reverts to normal.

## Release

Bump to `0.15.0`; suite ×2; exe + MSI + setup; frozen + installed probes;
self-review (small pure feature — skip the heavy workflow review for speed);
upgrade over 0.13.0 (data intact); push; tag `v0.15.0`; relaunch; memory.
