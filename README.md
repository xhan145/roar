# ROAR

**Local voice-to-text for Windows. Speak. Release. Type.**

ROAR is a free, local-first Windows dictation tray app inspired by fast push-to-talk tools like Wispr Flow. Hold your hotkey, speak naturally, release, and ROAR types the transcript into whatever app is focused.

No cloud. No telemetry. No account. Your voice stays on your machine.

---

## What ROAR Does

ROAR turns your Windows PC into a private dictation engine:

1. Hold your push-to-talk hotkey.
2. Speak.
3. Release the hotkey.
4. ROAR transcribes locally and types the result into the focused app.

It is designed for notes, messages, prompts, documents, coding workflows, support replies, and any text field where typing slows you down.

---

## Core Features

- **Push-to-talk dictation**
  - Hold hotkey, speak, release to type.
  - Default workflow is fast and low-friction.

- **100% local transcription**
  - Powered by `faster-whisper`.
  - No remote API required.
  - No telemetry or cloud processing.

- **Windows tray app**
  - Runs quietly in the background.
  - Settings window available from the tray.

- **Focused-app text injection**
  - Types into the active app.
  - Clipboard fallback is available when direct injection is not ideal.

- **Settings UI**
  - Configure startup behavior.
  - Configure hotkeys.
  - Configure voice and microphone settings.
  - Configure transcription behavior.
  - Manage privacy, history, insights, and vocabulary.

- **History and privacy**
  - Transcript history stored locally.
  - Optional retained audio.
  - Audio retention controls.
  - Local SQLite storage.

- **Insights**
  - Local usage analytics.
  - Dictation totals.
  - Activity patterns.
  - Word and phrase insights.

- **Custom vocabulary and hotwords**
  - Add domain-specific words, names, products, phrases, and technical terms.
  - Hotwords are merged locally and used to improve transcription context.

- **GPU acceleration**
  - Uses CUDA when available.
  - Falls back to CPU safely.

---

## Why ROAR Exists

Most dictation tools are either cloud-based, subscription-heavy, or awkward to use across normal desktop apps.

ROAR is built around a simpler idea:

> A private voice layer for your computer should feel instant, local, and invisible until you need it.

ROAR is not trying to be a giant writing suite. It is a small, sharp desktop tool: a local voice engine that gets text where it needs to go.

---

## Current Status

Current app version: `0.13.0` (`paths.APP_VERSION`).

**Shipped**

- Push-to-talk and toggle dictation.
- Local `faster-whisper` transcription with CUDA detection and CPU fallback.
- Windows tray app, settings window, overlay, and streaming preview.
- Local history, optional audio retention, insights, private milestones, and history deletion.
- Custom vocabulary, ROAR Snippets, deterministic cleanup, multilingual language selection, and scratch-that undo.
- Manual, user-clicked update check in About.
- Appearance setting (`system`, `light`, `dark`), Safe Diagnostics, and Safe Mode settings.

**Experimental**

- Bundled multilingual model seeds in release builds. Fresh source checkouts may need `scripts/fetch_models.py` before packaging.
- Real-app text injection behavior varies by target app; clipboard fallback exists for apps that block typed input.
- Speech cleanup heuristics are deterministic and local, but English filler removal can still be imperfect.

**Planned**

- Signed offline license validation and entitlement checks. Current source contains only safe primitives and docs; Core behavior is not paywalled.
- App profile policy, if implemented later, should remain local and avoid storing full window titles by default.
- Richer release smoke automation for installed builds.

**Intentionally Not Included**

- Cloud transcription, telemetry, accounts, subscriptions, sync, team features, marketplace features, and automatic network calls.
- Local LLM rewriting or networked text rewriting.
- Paywalls for basic dictation, privacy controls, history deletion, audio deletion, or local data controls.

ROAR has evolved from its original name, **FlowLocal**, into a Windows-focused local dictation app.

Implemented milestones include:

- `v0.1.0` core tray app
- `v0.2.0` settings window
- `v0.3.0` history and privacy controls
- `v0.4.0` insights, profile, and search
- `v0.5.0` custom vocabulary and hotwords
- `v0.6.0` product rename from FlowLocal to ROAR
- `v0.7.0` streaming dictation with live partial text while speaking
- `v0.8.0` Cinema Dark interface refresh
- `v0.9.0` multilingual dictation
- `v0.10.0` ROAR Snippets + multilingual models bundled in the installer
- `v0.11.0` speech cleanup — filler-word and disfluency removal
- `v0.11.1` slim white + lavender capsule pill (simplified dictation overlay)
- `v0.12.0` "scratch that" spoken undo, manual update check, credits
- `v0.13.0` private offline word milestones + lavender ROAR branding

Installing: `scripts/build_msi.sh` produces `dist/ROAR-<version>.msi` plus
`roar*.cab` files (an `.msi` file is capped at 2 GB, so the payload lives in
external cabinets — keep them next to the msi). `scripts/build_setup.sh` then
wraps all of it into a single double-clickable `dist/ROAR-Setup-<version>.exe`.

---

## Multilingual dictation

Settings → Transcription → **Language**: pick any of Whisper's 100 languages,
or **Auto-detect** to let ROAR identify the language each time you dictate.
With the model on `auto`, non-English languages switch to multilingual models
(`large-v3-turbo` on GPU, `small` on CPU). **Both multilingual models ship
inside the installer**, so switching languages works immediately and fully
offline — no first-switch download. Notes: spoken commands ("new line") are
English phrases (add your own per-language in `replacements`), and Insights
word filtering is English-centric.

## Speech cleanup

Settings → Transcription → **Clean up speech** (on by default) makes dictation
read like writing instead of raw speech. It runs entirely locally and
deterministically — no cloud, no language model, no delay:

- **Interjections** — "um", "uh", "er", "hmm" and their variants are removed
  (word-bounded, so "umbrella" and "summer" are safe).
- **Stutters and repeats** — an immediately repeated word collapses
  ("the the cat" → "the cat"), but only for common stutter-prone words, so
  grammatical doubles like "had had" and "very very" survive.
- **False starts** — a cut-off fragment before a dash is dropped
  ("I— I think" → "I think").

A second, opt-in toggle — **Remove filler phrases** (off by default) — also
strips "like", "you know", "I mean" and similar, but only when they appear as
comma-bounded fillers (", like,"), so "I like it" is never touched. It's off by
default because that heuristic can occasionally clip a real word.

The filler lists are English; the stutter/repeat and false-start collapse are
language-agnostic and help every language.

## Milestones

ROAR tracks how many words you've dictated and unlocks quiet local badges as
you go — from **First Roar** (1,000 words) up to **Million Word Roar**. See your
shelf, next milestone, and progress in Settings → Insights. When you cross a
threshold, a tray notification says so.

These are **private and offline**: the count and unlock times live only in your
local history database. There are no leaderboards, no sharing, no accounts, and
nothing leaves your machine. Badges are sticky — once earned, they stay even if
you later clear your history. Turn tracking or notifications off any time in
Insights. The nine milestones: First Roar, Warming Up, Voice Layer, Fluent Flow,
Local Legend, Hundred-K Roar, Dictation Engine, Thunder Typist, Million Word Roar.

## Scratch that

Said something you regret? Hold the hotkey and say just **"scratch that"**
(or "scratch it" / "undo that") — ROAR backspaces exactly what it last typed.
Say it again to undo the injection before that (up to 10 back). Safety rules:
the whole utterance must be the command (a sentence *containing* "scratch
that" is typed normally), and undo only fires in the same window the text
went to — click elsewhere and ROAR refuses with an error tone instead of
backspacing into the wrong app. Caveats: apps that transform typed text
(auto-indent, autocomplete) can make the backspace count imprecise, and undo
of emoji / other astral characters is best-effort (backspace granularity for
them is app-dependent).

ROAR never touches the network on its own; the **Check for updates** button
in About is the one exception, and only when you click it.

## ROAR Snippets

ROAR Snippets is the text-expansion layer for ROAR — dictation plus
abbreviation expansion:

```text
/sig → Thanks,
Greg
```

While dictating, say **"snippet sig"** (or type the literal form `/sig`) and
ROAR types the stored expansion instead. Manage snippets in Settings →
**Snippets**: names are 1–30 letters/digits/dashes, expansions up to 2,000
characters, 100 snippets max.

Expansions can include variables, resolved at the moment of dictation:

| Variable | Becomes |
|---|---|
| `{date}` | today's date |
| `{time}` | current time (HH:MM) |
| `{clipboard}` | current clipboard text |

Snippets live in `config.json` and can be shared as **packs** — plain JSON
files exported/imported from the Snippets tab. Imports never overwrite: a
colliding name is added with a `-2` suffix instead.

