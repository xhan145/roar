# Scratch That + Update Check + Credits (SP10) — Design

**Version:** v0.12.0
**Date:** 2026-07-04
**Status:** approved

## Goal

Three additions: a spoken undo command ("scratch that"), a manual
check-for-updates button, and a credits line in About.

## 1. "Scratch that" — spoken undo

### Command detection

New pure module `editing.py`:

- `SCRATCH_PHRASES = frozenset({"scratch that", "scratch it", "undo that"})`
- `is_scratch(text) -> bool` — True only when the ENTIRE utterance, after
  lowercasing, collapsing whitespace, and stripping leading/trailing
  punctuation (`.,!?;: `), is one of the phrases. Standalone-only by design:
  dictating a sentence that merely contains "scratch that" is never hijacked.
- Detection runs on the RAW transcript in `_handle_transcription`, before
  cleanup/replacements/snippets. A matched command never reaches the pipeline
  and never injects text.

### Injection stack

`editing.InjectionStack` (pure logic; win32/injection dependencies injected):

- `push(typed, hwnd, history_id)` — `typed` is the PREPARED string actually
  sent (`injector.prepare()` adds a trailing space, so undo lengths must use
  it, not the pipeline text). Depth-capped at 10 (oldest dropped).
  Session-only; starts empty each run.
- `pop_if(hwnd) -> entry | None` — pops only when `hwnd` equals the entry's
  recorded handle; None (stack untouched) otherwise.

### Undo execution (app.py)

On a scratch command:

1. Get the current foreground window via
   `ctypes.windll.user32.GetForegroundWindow()`.
2. `pop_if(current_hwnd)`. Focus changed or stack empty → error tone + log
   ("nothing to scratch here"), NEVER backspace into the wrong window.
3. Else send `len(entry.typed)` backspace key presses through the `keyboard`
   lib, play the ok tone, log `scratched N chars`.
4. Delete the dictation's history row (`history.delete(entry.history_id)`)
   when one was recorded — history stays true to what remains on screen.
   `record_history` starts returning the row id (or None) to enable this.

Every injection in `_handle_transcription` pushes onto the stack (hwnd
captured immediately before injecting). Saying the command repeatedly walks
back through prior injections (up to depth 10, same-window only per entry).

Known limitations (documented in README): apps that transform typed text
(auto-indent, autocomplete, autocorrect) can make backspace counts imprecise;
paste-fallback injections undo the same way (backspaces).

## 2. Check for updates — manual only

- New bridge method `check_updates()` in `settings_ui.py`: fetches
  `https://api.github.com/repos/xhan145/roar/tags?per_page=1` with stdlib
  `urllib.request` (5 s timeout, `User-Agent: ROAR`), parses the first tag
  name (`v0.12.0` → `0.12.0`), numeric-tuple compares to `paths.APP_VERSION`.
  Returns `{ok: True, current, latest, newer: bool}` or `{error: <message>}`
  (offline/timeout/parse errors all degrade to a friendly error string).
- New bridge method `open_repo()` — `os.startfile` on the FIXED repo URL
  (`https://github.com/xhan145/roar`); no arbitrary-URL opening.
- About tab UI: "Check for updates" button + result line; when newer, the
  line includes an "open GitHub" link wired to `open_repo()`.
- NO background or automatic checking — the network is touched only by the
  click. stdlib-only; the settings process stays ML-free.

## 3. Credits

About tab gains the line: **Created, Coded, and Developed by Greg M and Ben Y**

## Testing

- `tests/test_editing.py`: `is_scratch` table (exact phrases, case/punct
  variants, embedded-phrase rejections, empty/None); `InjectionStack`
  push/pop_if semantics (depth cap, wrong-hwnd refusal, order).
- `tests/test_capture_integration.py` style: scratch command with a fake
  injector/hwnd — asserts backspace count = len(prepared), history row
  deleted, no injection, focus-mismatch refusal.
- `tests/test_settings_bridge.py`: `check_updates` with monkeypatched
  `urllib.request.urlopen` (newer / same / network-error cases);
  `open_repo` rejected paths N/A (fixed URL).
- Smoke probe asserts About has the update button (`b-check-updates`) and
  credits element (`a-credits`).

## Release

v0.12.0: suite ×2, exe, MSI + external cabs, setup exe, frozen + installed
probes, adversarial review, upgrade over 0.11.1 (data intact), fetch → push,
tag, relaunch, memory.
