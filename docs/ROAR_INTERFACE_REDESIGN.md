# ROAR interface redesign blueprint

This blueprint defines a new ROAR interface system that fits the current codebase shape: a Windows tray app with a pywebview settings window backed by `settings.html` and `settings_ui.py`.

## Product promise

ROAR remains simple:

> Hold the hotkey, speak, release, and ROAR types locally into the focused app.

The interface should make that promise feel calm, fast, private, and owned by the user.

## Design principles

1. **Local first, visually obvious**
   - Use persistent privacy language: local, offline, no account, no cloud transcription.
   - Do not bury privacy under an advanced page.

2. **Command center, not control panel**
   - Settings should feel like a small cockpit for a voice layer.
   - Important state should be visible at a glance: hotkey, model, language, privacy, edition, diagnostics.

3. **Core is dignified**
   - Core dictation, privacy, history deletion, audio deletion, streaming preview, multilingual dictation, and scratch-that undo must never look crippled.
   - Paid surfaces unlock workflow power, not basic safety.

4. **No dark-pattern monetization**
   - No launch nags.
   - No fake countdowns.
   - No subscription language.
   - No paywalls around privacy controls.
   - Upgrade prompts appear only when the user intentionally touches a Pro or Developer feature.

5. **Small app, sharp blade**
   - Prefer deterministic local features and simple UI mechanics.
   - Avoid heavy frontend framework churn unless the app is intentionally moving away from single-file settings HTML.

## Current codebase fit

### Existing app facts

- The README describes ROAR as a local-first Windows tray app that holds a hotkey, records speech, transcribes locally with `faster-whisper`, and types into the focused app.
- The current settings UI is `settings.html` with embedded CSS and HTML.
- The settings bridge is `settings_ui.py`, a lightweight pywebview process.
- `settings_ui.py` explicitly avoids importing `app.py` or `transcriber.py` so the settings process does not load the ML/CUDA stack.
- `config.py` already centralizes defaults such as hotkeys, model, language, history, overlay, streaming preview, snippets, cleanup, and milestones.

### Implementation constraint

Keep the redesign implementable by editing:

```text
settings.html
settings_ui.py
config.py
```

Then add pure modules for new business logic:

```text
license.py
entitlements.py
formatting.py
diagnostics.py
```

Avoid importing transcription or recorder-heavy code into the settings bridge beyond the current microphone device listing.

## Visual direction

### Name

**ROAR Command Center**

### Mood

- Quiet lavender glow
- Dark graphite panels
- White/lavender pill overlay
- Rounded, compact, minimal
- Fewer sharp edges than the current cinema-dark style
- More confidence, less dashboard noise

### Color tokens

```css
:root {
  --roar-bg: #05050A;
  --roar-panel: #0B0B12;
  --roar-card: #12121B;
  --roar-card-raised: #181827;
  --roar-border: rgba(255,255,255,.08);
  --roar-border-strong: rgba(185,168,255,.38);
  --roar-text: #F4F1FF;
  --roar-muted: #A6A0BA;
  --roar-dim: #746F86;
  --roar-lavender: #B9A8FF;
  --roar-purple: #6F5CFF;
  --roar-violet: #8E7BFF;
  --roar-green: #48D597;
  --roar-red: #FF6B7A;
  --roar-amber: #FFC96B;
  --roar-blue: #64B5FF;
  --roar-glow: rgba(111,92,255,.32);
}
```

### Typography

Use the existing Windows-friendly stack unless packaging a font is intentional:

```css
font-family: "Segoe UI", system-ui, sans-serif;
```

Recommended scale:

```css
--type-display: 28px;
--type-title: 20px;
--type-body: 14px;
--type-caption: 12px;
--type-micro: 11px;
```

### Radius and spacing

```css
--radius-window: 28px;
--radius-card: 20px;
--radius-row: 16px;
--radius-control: 12px;
--radius-pill: 999px;
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 24px;
--space-6: 32px;
```

## App structure

### Primary navigation

Recommended order:

1. Home
2. Hotkeys
3. Voice & Mic
4. Transcription
5. Snippets
6. History
7. Privacy
8. Insights
9. License
10. Diagnostics
11. About

Reasoning:

- Home becomes the glanceable command center.
- Privacy remains first-class, not hidden.
- License is separated from privacy so monetization never feels like a data switchboard.
- Diagnostics gets its own page for support and hardening.

## Screen 1: Home dashboard

### Purpose

Answer: “Is ROAR ready, private, and configured the way I expect?”

### Sections

#### Header

```text
Ready when your voice is
Hold Ctrl+Win, speak, release. ROAR types locally into the focused app.
```

Actions:

- Start smoke test
- Open diagnostics

#### Status cards

1. **Dictation ready**
   - Shows current push-to-talk hotkey.
2. **Model**
   - Shows selected model and device, e.g. `Auto • GPU`.
3. **Privacy**
   - Shows `History local`, `Audio off`, or current retention.
4. **Edition**
   - Shows Core, Pro, Developer, or Supporter.

#### Dictation controls

Rows:

- Show dictation pill
- Live text preview
- Paste fallback
- Audio feedback tones

These map to existing config keys:

```text
overlay_enabled
streaming_preview
paste_fallback
tones_enabled
```

#### Milestone shelf

Show:

- Current milestone
- Next milestone
- Progress bar
- Short privacy line: `Private and offline. No leaderboard.`

#### Diagnostics summary

Show:

- Last recording duration
- Last transcription duration
- Last injection method
- Safe Mode button
- Copy redacted diagnostics button

## Screen 2: Transcription

### Purpose

Make model/language/cleanup easier to understand and prepare for smart formatting.

### Current controls to preserve

- Model
- Language
- Speech cleanup
- Remove filler phrases

### New formatting mode cards

Core:

- Raw
- Clean

Pro:

- Notes
- Professional
- Chat

Developer:

- Code

Card text:

```text
Raw
Minimal transcript changes.
Core

Clean
Current local cleanup behavior.
Core

Notes
Line breaks and bullets from spoken structure.
Pro

Professional
Conservative deterministic polish.
Pro

Chat
Short, casual, message-ready cleanup.
Pro

Code
Programming symbols and code-aware spacing.
Developer
```

### Config additions

```python
"format_mode": "clean"
```

Validation:

```text
raw, clean, notes, professional, chat, code
```

## Screen 3: Dictation pill overlay

### Purpose

Make the overlay feel like a small living instrument, not a modal interruption.

### States

1. **Idle hidden**
2. **Listening**
   - Text: `Listening`
   - Subtext: `Release to type`
   - Animated waveform
3. **Live preview**
   - Shows partial transcript when `streaming_preview` is true.
4. **Processing**
   - Text: `Transcribing locally…`
5. **Typed**
   - Text: `Typed into focused app`
6. **Scratch that**
   - Text: `Undoing last ROAR insertion`
7. **Error**
   - Text: `Focused window changed. Undo refused safely.`

### Visual style

- White/lavender capsule
- Thin lavender border
- Soft glow
- Minimal waveform
- No giant status modal

## Screen 4: Snippets workspace

### Purpose

Make snippets feel like a local voice macro shelf.

### Layout

- Search snippets
- Snippet list
- Editor panel
- Variable helper row
- Import/export controls

### Core snippets behavior to preserve

- Say `snippet sig`
- Type literal `/sig`
- Variables `{date}`, `{time}`, `{clipboard}`
- Snippets live in `config.json`

### Future variables

Pro/Developer candidates:

```text
{app}
{window_title}
{mode}
{language}
```

Privacy rule:

- Resolve variables only at dictation time.
- Do not store window titles unless the user explicitly inserts them into output.

## Screen 5: History workspace

### Purpose

Make local history feel useful without making it creepy.

### Layout

- Search field
- Retention status chip
- History rows
- Tags/chips if v0.14 tagging is implemented
- Delete row
- Clear all history

### Privacy copy

```text
History is stored locally in SQLite. Clear it any time.
```

### Pro history filters

If monetized:

- Search remains Core.
- Delete and clear remain Core.
- Advanced filters/tags can be Pro.

## Screen 6: Privacy

### Purpose

Make trust obvious and untouchable by payment state.

### Rows

- History enabled
- Audio retention
- Clear transcript history
- Delete retained audio
- Open config path
- Open local log path

### Copy

```text
Privacy controls are always available in ROAR Core.
```

Never show locked cards on this page.

## Screen 7: License

### Purpose

Support offline one-time licensing without corrupting the privacy story.

### Content

```text
ROAR Core is active.
Core dictation is free, local, and private.
```

If activated:

```text
ROAR Pro is activated locally.
No account is required.
Your dictation data stays on this machine.
```

Actions:

- Enter license
- Import license file
- Buy ROAR Pro
- Buy Developer Pack

### Required constraints

- License validation is offline.
- License UI never reads transcript, audio, history, or vocabulary.
- Purchase buttons may open configured URLs only by user click.
- No background license network call.

## Screen 8: Diagnostics

### Purpose

Help support and hardening without leaking private data.

### Fields

- Version
- Edition
- Model
- Device
- Language
- Format mode
- Overlay enabled
- Streaming preview enabled
- Last record duration
- Last transcription duration
- Last injection duration
- Last injection method
- History count
- License status

### Actions

- Copy redacted diagnostics
- Enable Safe Mode
- Open log file

### Redaction rules

Diagnostics must not include:

- Transcript text
- Clipboard contents
- Raw license keys or signatures
- Full window title unless the user explicitly opts in
- Audio paths unless needed and sanitized

## Component inventory

### Components to implement in CSS/HTML

- `.app-shell`
- `.sidebar`
- `.brand-lockup`
- `.nav-item`
- `.page-header`
- `.status-grid`
- `.status-card`
- `.settings-row`
- `.toggle`
- `.button.primary`
- `.button.secondary`
- `.chip`
- `.mode-card`
- `.locked-card`
- `.diagnostic-grid`
- `.overlay-pill`
- `.waveform`

## Recommended implementation sequence

### Commit 1: UI token refactor

Files:

```text
settings.html
```

Work:

- Replace existing CSS variables with ROAR Command Center tokens.
- Keep all current IDs intact.
- Do not change bridge methods yet.

Commit:

```text
style: refresh settings design tokens
```

### Commit 2: Home dashboard

Files:

```text
settings.html
settings_ui.py
```

Work:

- Add Home nav/page.
- Move high-value current controls into Home, preserving old sections too if needed.
- Extend `get_state()` only with lightweight fields already available.

Commit:

```text
feat: add settings home dashboard
```

### Commit 3: License page shell

Files:

```text
settings.html
settings_ui.py
config.py
```

Work:

- Add License nav/page.
- Add config defaults:

```python
"license_edition": "core",
"license_notifications": True,
```

- Do not gate features yet.

Commit:

```text
feat: add local license page shell
```

### Commit 4: Diagnostics page shell

Files:

```text
settings.html
settings_ui.py
```

Work:

- Add Diagnostics page.
- Add redacted diagnostics copy helper.
- Add Safe Mode button that toggles conservative settings.

Commit:

```text
feat: add diagnostics page shell
```

### Commit 5: Formatting modes UI

Files:

```text
settings.html
settings_ui.py
config.py
```

Work:

- Add `format_mode` config.
- Add mode cards/dropdown.
- Keep Raw/Clean Core.
- Locked cards for advanced modes only when entitlements exist.

Commit:

```text
feat: add formatting mode controls
```

### Commit 6: smoke test expansion

Files:

```text
settings_ui.py
```

Work:

Extend settings smoke probe to verify:

- Home nav reachable
- License nav reachable
- Diagnostics nav reachable
- Privacy nav still reachable
- Snippets nav still reachable
- Formatting control exists
- Existing version/about checks still pass

Commit:

```text
test: expand settings smoke coverage
```

## Acceptance criteria

- Settings window still launches at 900 x 640 minimum.
- No `settings_ui.py` import of `app.py` or `transcriber.py`.
- Existing IDs used by JS bridge remain stable or are migrated deliberately.
- Privacy page has no upgrade prompts.
- History clear and audio deletion are never locked.
- License page can exist before feature gating.
- Diagnostics copy is redacted.
- Manual update check remains click-only.
- Core dictation remains free and visibly complete.

## Claude Code implementation prompt

```md
You are working in the ROAR repo.

Implement the ROAR Command Center settings redesign in small, safe commits.

Start with the existing architecture:
- `settings.html` is the settings UI.
- `settings_ui.py` is the pywebview bridge.
- `config.py` owns defaults.

Requirements:
1. Refresh the settings UI visual system using the tokens in `docs/ROAR_INTERFACE_REDESIGN.md`.
2. Add a Home dashboard with dictation readiness, current hotkey, model/device, privacy state, edition, milestone summary, and diagnostics summary.
3. Add License and Diagnostics nav/page shells.
4. Add formatting mode controls for Raw, Clean, Notes, Professional, Chat, and Code.
5. Keep Raw and Clean available to Core.
6. Do not gate privacy controls, history deletion, audio deletion, offline use, basic dictation, streaming preview, multilingual dictation, or scratch-that undo.
7. Do not add subscriptions, accounts, telemetry, or cloud transcription.
8. Do not import `app.py` or `transcriber.py` into `settings_ui.py`.
9. Keep existing settings behavior working.
10. Expand the settings smoke probe for new nav items and controls.

Constraints:
- ROAR is local-first.
- No cloud transcription.
- No telemetry.
- No account required.
- Paid UI must be calm and click-intent only.
- Add tests/smoke checks where possible.

Commit in small chunks:
- style: refresh settings design tokens
- feat: add settings home dashboard
- feat: add local license page shell
- feat: add diagnostics page shell
- feat: add formatting mode controls
- test: expand settings smoke coverage
```

## GPT Codex review prompt

```md
Red-team the ROAR Command Center settings redesign.

Check:
- Settings still launches without importing the ML stack.
- Existing settings values load and save correctly.
- Privacy controls are never paid-only or visually locked.
- History clear and audio deletion remain available in Core.
- License UI never reads transcripts, audio, history rows, or vocabulary.
- Diagnostics copy redacts transcript text, clipboard, license secrets, and sensitive paths.
- Upgrade prompts appear only after intentional clicks on Pro/Developer features.
- Manual update check remains click-only.
- No cloud transcription, telemetry, account requirement, or subscription language was introduced.
- Settings smoke test covers Home, License, Diagnostics, Privacy, Snippets, cleanup controls, language controls, and version/about.

Return:
1. Release blockers.
2. Should-fix issues.
3. Suggested patch.
```
