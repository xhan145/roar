# Codex work order — ROAR expanded app profiles (v0.16.0)

You are working autonomously in the **ROAR** repo. Implement a richer,
user-configurable per-app formatting profile system and ship it as **v0.16.0**
through ROAR's standard release train. Everything below is authoritative — do
not invent scope beyond it, and do not weaken any stated constraint.

---

## 0. Mission (one line)

Expand ROAR's context-aware formatting from 2 hardcoded profiles to a richer,
user-overridable set: **verbatim** in code editors (VS Code, Visual Studio,
JetBrains, terminals…), **casual** (less terse, keep slang/fillers, texting
style) in WhatsApp / Facebook / Messenger / Instagram / Ableton / Discord, and
**formal** (polished) in email/word processors — plus a config key so users can
map any app to any profile, and browser-title detection so web apps (Facebook,
web WhatsApp, Gmail) are recognized too.

---

## 1. Environment & how to work

- Repo root: `C:\Users\xhan1\flowlocal` (Windows). Python 3.14 in a venv —
  **always** run Python as `venv/Scripts/python.exe`.
- Run tests: `venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_transcriber_gpu.py`
  (the gpu test needs CUDA; ignore it). Current suite: **222 passing**.
- TDD: write the failing test first, then the code. Commit in small steps with
  messages ending:
  `Co-Authored-By: Codex <noreply@openai.com>`
- ROAR is a **pure Python Windows tray app** — no web server, no npm. Ignore any
  dev-server/preview tooling.

## 2. Hard constraints (never violate)

- **100% local. No cloud, no telemetry, no account, no network** except the
  existing manual "Check for updates" button.
- **The settings process must never import the ML stack** (`faster_whisper`,
  `ctranslate2`). There is a regression test asserting this
  (`tests/test_settings_bridge.py::test_settings_process_never_imports_ml_stack`).
  Keep profile logic in a pure module; do not import anything heavy from it.
- **Preserve every existing behavior**: dictation, push-to-talk, double-tap
  hands-free, streaming preview, history + WAL durability + rolling backups,
  insights, milestones, vocabulary, snippets, speech cleanup, scratch-that,
  multilingual, the update check, and the current v0.15 context-aware formatting.
  This feature only *extends* the profile layer.
- **Do not touch** `history.py`'s WAL checkpoint / `_backup` code, `gestures.py`,
  or the installer packaging logic except the version bump.

## 3. What exists today (ground truth — read these files, don't trust memory)

`context.py` (the whole file):

```python
"""Per-app formatting profiles: the focused app decides how dictation is
formatted. Pure — app.py supplies the detected foreground exe basename."""

_PROFILES = {
    "code": {"capitalize": False, "cleanup": False},
    "chat": {"discourse_fillers": True},
}

_APP_MAP = {
    "code.exe": "code", "code - insiders.exe": "code", "devenv.exe": "code",
    "pycharm64.exe": "code", "idea64.exe": "code", "sublime_text.exe": "code",
    "windowsterminal.exe": "code", "cmd.exe": "code", "powershell.exe": "code",
    "pwsh.exe": "code", "conhost.exe": "code", "wezterm-gui.exe": "code",
    "slack.exe": "chat", "discord.exe": "chat", "teams.exe": "chat",
    "ms-teams.exe": "chat", "telegram.exe": "chat", "whatsapp.exe": "chat",
}

def profile_for(exe_name):
    if not exe_name:
        return {}
    prof = _PROFILES.get(_APP_MAP.get(str(exe_name).lower()))
    return dict(prof) if prof else {}
```

`commands.process(text, replacements, snippets=None, snippet_keyword="snippet",
cleanup=False, discourse_fillers=False, capitalize=True)` — the profile override
dict can set any of `cleanup`, `discourse_fillers`, `capitalize`. These are the
ONLY three formatting levers. (ROAR never invents slang; "keep slang" means
"don't strip conversational fillers / don't over-format" — i.e. leave the
casual voice alone.)

`app.py` already has a hardened `_foreground_exe()` (win32, explicit ctypes
signatures, returns lowercased exe basename or `""`). In `_handle_transcription`
it does, when `cfg["context_aware"]` is on:
`prof = context.profile_for(self._foreground_exe())` then passes
`cleanup/discourse_fillers/capitalize` (profile value, else the user's cfg) into
`commands.process`. `config.py` has `context_aware: True` (bool INSTANT_KEY in
`settings_ui.py`).

## 4. What to build

### 4a. Richer built-in profiles (`context.py`)

Define these profile → override dicts (tune only if a test proves a value wrong):

| Profile | Override dict | Feel |
|---|---|---|
| `code` | `{"capitalize": False, "cleanup": False}` | verbatim, case-sensitive, no munging |
| `casual` | `{"capitalize": False, "cleanup": True, "discourse_fillers": False}` | texting: lowercase, keep slang/fillers, still drop raw "um/uh" |
| `formal` | `{"capitalize": True, "cleanup": True, "discourse_fillers": True}` | polished full sentences |
| `chat` | keep as an alias of `casual` (back-compat with existing config/tests) OR fold existing chat apps into `casual` | — |

Expanded `_APP_MAP` (lowercased exe basenames). Add generously:

- **code**: everything currently there **plus** `rider64.exe`, `webstorm64.exe`,
  `clion64.exe`, `goland64.exe`, `rustrover64.exe`, `phpstorm64.exe`,
  `datagrip64.exe`, `studio64.exe` (Android Studio), `notepad++.exe`,
  `sublime_text.exe`, `zed.exe`, `cursor.exe`, `alacritty.exe`, `hyper.exe`,
  `wt.exe`. (Visual Studio = `devenv.exe`, already present — keep it.)
- **casual**: `whatsapp.exe`, `discord.exe`, `telegram.exe`, `signal.exe`,
  `instagram.exe`, `messenger.exe`, `slack.exe` (moved from chat→casual is fine),
  `ableton live 11 suite.exe`, `ableton live 12 suite.exe`, `ableton live 11 lite.exe`,
  `ableton.exe` — match Ableton robustly (see note below), plus `spotify.exe`.
- **formal**: `outlook.exe`, `winword.exe`, `thunderbird.exe`, `acrobat.exe`,
  `wps.exe`.

**Ableton exe caveat:** Ableton's exe name contains the edition/version
("Ableton Live 12 Suite.exe"). Rather than list every variant, ALSO support a
prefix/substring rule: if no exact map hit, check whether the basename
*startswith* any key in a small `_APP_PREFIX` map (e.g. `"ableton"` → `casual`).
Keep exact-match primary, prefix-match secondary.

### 4b. Browser-title detection (so web apps work)

Facebook, Messenger web, web WhatsApp, Gmail, etc. run inside a browser, so
`_foreground_exe()` returns the browser (`chrome.exe`, `msedge.exe`,
`firefox.exe`, `brave.exe`, `opera.exe`, `arc.exe`). Add a **second signal**:

- In `app.py`, add `_foreground_title()` — win32 `GetForegroundWindow` +
  `GetWindowTextW` (explicit ctypes signatures like `_foreground_exe`;
  try/except → `""`).
- `context.profile_for(exe_name, title=None, user_map=None)`:
  1. Resolve the exe via exact map, then prefix map.
  2. **Only when the exe is a known browser AND no user override applies**, scan
     the lowercased `title` against a `_TITLE_MAP` of keywords →
     profile: `whatsapp`/`messenger`/`facebook`/`instagram`/`discord` → `casual`;
     `gmail`/`outlook`/`google docs`/`- word` → `formal`;
     `github`/`stack overflow`/`localhost`/`codepen` → `code`. First keyword hit
     wins. This scoping (browser-only) prevents a Word doc titled
     "facebook plan" from being mis-profiled.
- `app.py` passes both signals:
  `context.profile_for(self._foreground_exe(), self._foreground_title(), self.cfg.get("app_profiles"))`.

### 4c. User-configurable overrides (`config.py`)

- New default: `"app_profiles": {}` — a dict mapping a lowercased exe basename
  **or** a `title:<keyword>` string to a profile name. Sanitize on load: keep
  only `str→str` entries whose value is a known profile name (`code`, `casual`,
  `formal`, `chat`); drop the rest (mirror how `snippets`/`replacements` are
  sanitized). Do NOT crash on a non-dict value.
- `profile_for` merges `user_map` OVER the built-in map (user wins). Support the
  `title:<keyword>` form too (checked against the title, browser-scoped).
- Add `"app_profiles"` handling to the settings bridge: it is NOT a simple
  instant toggle (it's a dict), so add dedicated bridge methods rather than
  routing through `set_value`:
  `app_profiles_get() -> {profiles: [...names...], map: {...}}` and
  `app_profile_set(app, profile)` / `app_profile_clear(app)` (validate profile
  name; write under the existing `_cfg_lock`). Follow the exact pattern of the
  snippets bridge methods in `settings_ui.py`.

### 4d. Settings UI (Transcription tab)

Add a compact **"App profiles"** block under the existing context-aware area:

- A short hint explaining profiles (verbatim in code, casual in chat/social,
  formal in email; default elsewhere).
- A list of the current user overrides (`app` → `profile`) with a remove (×)
  per row, rendered with `textContent` (never `innerHTML`) — XSS-safe, matching
  the snippets/vocab renderers.
- An add row: a text input for the app exe (or `title:keyword`) + a `<select>`
  of profile names + an Add button, wired to `app_profile_set`.
- Reuse existing styles/toggle patterns. Update the settings **smoke probe** in
  `settings_ui.py` to assert the new element exists (e.g. `profiles=1`) and add
  the matching assertion in `tests/test_settings_smoke.py`.

Keep the existing `context_aware` master toggle behavior (when off, no profile
is applied at all).

## 5. Tests (TDD — write first)

- `tests/test_context.py` (extend): every built-in profile resolves correctly;
  Ableton prefix match; unknown exe → `{}`; user_map overrides a built-in
  (e.g. map `notepad.exe`→`casual`); browser-title routing (chrome + title
  "WhatsApp" → casual; chrome + title "GitHub - repo" → code; a NON-browser exe
  with a matching title is NOT title-routed); `title:` user override; returned
  dict is a copy (mutating it doesn't poison the table).
- `tests/test_config.py` (extend): `app_profiles` default `{}`; sanitize drops
  non-dict, non-str, and unknown-profile-name entries; keeps valid ones.
- `tests/test_settings_bridge.py` (extend): `app_profile_set` validates the
  profile name and persists; `app_profile_clear` removes; `app_profiles_get`
  returns the profile-name list + current map.
- `tests/test_capture_integration.py` (extend): monkeypatch
  `ROARApp._foreground_exe` → a casual app and assert the injected text keeps
  its casual form (no forced filler strip, lowercase); a formal app capitalizes;
  a code app is verbatim; `context_aware=False` reverts to plain user settings.
  Use the existing `_make_app` harness (bare instance; it already sets the
  fields the transcription path needs).

All tests must pass **twice** in a row (kill any running `ROAR.exe` first — a
running instance holds the settings-mutex and flakes the two smoke tests).

## 6. Release train (v0.16.0) — do all of it

1. Bump `paths.APP_VERSION` to `"0.16.0"`; update the version asserts in
   `tests/test_paths.py` and `tests/test_settings_bridge.py::test_get_state_shape`.
   Add a `v0.16.0` line to the README "Current Status" list and a short
   "App profiles" usage paragraph.
2. Kill ROAR + any `msedgewebview2.exe` whose command line contains `ROAR`
   (exclude your own shell). Then:
   - Rebuild exe: `venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm`
   - Build MSI: `bash scripts/build_msi.sh` (run SOLO — never two MSI builds at
     once; that exhausts commit memory). Output is a small `.msi` + external
     `roar*.cab` files (an `.msi` file is hard-capped at 2 GB, so the payload
     lives in external cabs — this is intentional; keep them together).
   - Build the single-file installer: `bash scripts/build_setup.sh`
     (7-Zip SFX wrapping the msi + cabs → `dist/ROAR-Setup-0.16.0.exe`).
3. **Frozen probe**: launch `dist/ROAR/ROAR.exe --settings --smoke`, read the
   tail of `%LOCALAPPDATA%\ROAR\roar.log`, and confirm a line like
   `settings probe navs=… version=0.16.0 … profiles=1`. (The probe app writes
   to the log because it's windowed — read the file, don't expect stdout.)
4. **Install** over the previous version: with ROAR fully stopped, run
   `msiexec /i "dist\ROAR-0.16.0.msi" /qn` (use `/qn`, NOT the setup exe's
   `/qb`, to avoid a blocking "Files in Use" dialog). Confirm the product
   version is `0.16.0` (`Get-CimInstance Win32_Product -Filter "Name='ROAR'"`),
   and that `%LOCALAPPDATA%\ROAR\history.db` row count is unchanged (data
   intact) — history durability is already handled, but verify anyway.
5. **Push**: `git fetch origin` FIRST (the human sometimes edits on GitHub web —
   merge, don't rebase, if diverged), then push `main`, create tag `v0.16.0`,
   `git push origin --tags`. The repo is public: `github.com/xhan145/roar`.
6. Relaunch the installed app
   (`%LOCALAPPDATA%\Programs\ROAR\ROAR.exe`); confirm the log shows
   `hotkeys registered` and `tray ready` and exactly one `ROAR.exe` runs.

## 7. Gotchas (learned the hard way — honor them)

- Kill `ROAR.exe` + its `msedgewebview2` children before any build or install,
  but a running instance is now safe to kill (history checkpoints every record).
- A lingering `--settings` process holds the settings mutex and makes the two
  smoke tests report "already running" — kill everything before the final
  verification and confirm a single tray process.
- Never change the MSI `UpgradeCode` in `installer/roar.wxs`.
- Keep the profile module pure and free of ML imports (settings-process test).
- Browser-title routing must be browser-scoped to avoid false positives.
- If unsure whether a value/name is right, add a test that pins the behavior and
  make it pass — don't guess silently.

## 8. Definition of done

All tests green ×2; exe + MSI + external cabs + setup exe built; frozen probe
shows `version=0.16.0 profiles=1`; installed over the prior version with data
intact; pushed + tagged `v0.16.0`; installed app relaunched and healthy;
README updated. Report what shipped, the exact profile table, and any value you
tuned from this spec with the reason.
