# Changelog

## v0.35.2 — 2026-08-02 — installer honesty, continued

An adversarial review of the v0.35.1 packaging fixes found four real defects —
two of them introduced by v0.35.1 itself. The app is unchanged; this is again
purely about installing and building.

- **Fixed: an install that needs a restart no longer claims it failed.**
  Windows returns a distinct "installed, but restart to finish" result when it
  has to replace files that were in use. v0.35.1 reported that as
  `FAILED — nothing was changed`, which was untrue, and said nothing about
  restarting — leaving you free to launch a half-replaced app. It now tells you
  the install succeeded and to restart before launching ROAR.
- **Fixed: the build could delete the installer package it had just made.**
  The v0.35.1 rule kept the two newest packages, which quietly discarded a
  freshly built one whenever two newer versions were already present — building
  an older version to reproduce a bug, for instance — while still printing
  "built" and reporting success. The version being built is now always kept.
- **Fixed: the version stamp is written next to the build recipe** rather than
  wherever the build happened to be started from, so it can neither go missing
  nor be silently stamped from a stale copy.

## v0.35.1 — 2026-08-02 — upgrades that actually upgrade

- **Fixed: installing a new version could silently leave the old one running.**
  On some machines an in-place upgrade would finish, report success, and change
  nothing at all — same version, same files. ROAR.exe now carries a proper
  Windows version stamp (visible in Properties → Details), which is what
  Windows Installer uses to decide whether to replace it. Without that stamp it
  could decide to keep what was already there.
- **Fixed: a failed install no longer looks like a successful one.** If the
  installer cannot complete, it now says so on screen with the error code,
  writes a full log to `%TEMP%\ROAR-install-<version>.log`, and tells you where
  that log is — instead of closing quietly as though everything worked.
- **Fixed: the build no longer deletes what the next upgrade needs.** Packaging
  discarded the previous version's installer package, which Windows needs to
  remove the old version during an upgrade; without it the upgrade failed and
  rolled back. Both the current and previous packages are now kept.

Nothing changed in the app itself — this release is entirely about installing
and updating it. If v0.35.0 is already working for you, there is nothing new to
see; if updating to it appeared to do nothing, this is the release that fixes
that.

## v0.35.0 — 2026-08-02 — 14-day Full-Feature Trial

- **Try every ROAR feature for 14 days.** Settings → About now offers a
  Full-Feature Trial: click **Start 14-Day Trial** and every Pro and Developer
  feature unlocks — smart formatting, snippets, Code Mode, app profiles,
  vocabulary suggestions, history tools, Flow automations and routing. No
  account, no payment card, no subscription, and no internet: the trial is
  calculated and stored entirely on your machine. It never starts on its own —
  installing, launching, or updating ROAR does nothing until you click the
  button.
- **When it ends, ROAR Core is still yours.** Local dictation, multilingual
  transcription, streaming preview, history, privacy controls, basic
  vocabulary and Scratch That keep working, free, forever. Nothing you created
  is deleted or converted: your snippets, profiles, tags, vocabulary and
  settings sit exactly where you left them and light back up the moment a
  licence is activated. You get one calm notification when the trial ends —
  never during dictation, and never again after that.
- **A licence always wins.** Buying at any point — during the trial or long
  after it ended — takes effect immediately in the running app, with no
  restart. Clearing history, deleting audio, or resetting settings can never
  restart, extend, or shorten a trial, and a normal update preserves it.
- **Honest about the clock.** If your system clock moves backward, ROAR says
  so plainly, keeps Core available, and offers Try Again instead of accusing
  you of anything. Offline trial enforcement is best-effort and documented as
  such in `docs/TRIAL_ARCHITECTURE.md` — it is not, and is never advertised
  as, DRM.
- **Under the hood.** New `trial.py` (pure state) and `trial_store.py`
  (protected storage) feed one runtime answer, `access.effective_edition()`:
  a valid paid licence outranks an active trial, which outranks Core. The
  trial record holds only trial bookkeeping — never transcripts, audio,
  history, clipboard, vocabulary, or window titles — and diagnostics show
  dates and states only.

## v0.34.0 — 2026-08-01 — Live transcript window + per-app routing

- **Standalone live transcript window.** Tray → "Live transcript…" (or the
  fob's right-click menu) opens a compact chat-style window showing everything
  ROAR transcribes as it happens — dictations and meeting-capture lines
  interleaved, with All / Dictation / Capture filters, search, an always-on-top
  toggle, per-line copy, and export to a text file. Reads your local history
  only; if history is off it says so instead of sitting empty. Free in every
  edition.
- **Per-app routing profiles.** Pin any route on or off per application:
  "notes off in Slack" while notes is globally on, "notes always on in Word".
  Unpinned routes keep following your live toggles, and typing into the
  focused app is never affected. Managed under Settings → Flow; rules persist
  (that's their job) and are documented in the privacy promise. (ROAR
  Developer)

## v0.33.0 — 2026-07-31 — The mic fob

- **The dictation pill is now a fob** — like ROAR Android. Idle, it collapses
  to a small round mic button that's always on screen. **Tap** it to start or
  stop hands-free dictation (same as double-tapping the hotkey). **Drag** it
  anywhere — ROAR remembers the spot across restarts, and a position left on
  an unplugged monitor safely resets. **Right-click** for quick actions:
  Scratch that, Read selected text, Open Settings, Hide fob.
- While dictating, the familiar waveform pill expands around wherever the fob
  sits, clamped so it never grows off-screen.
- Clicking the fob **never steals keyboard focus** from the app you're
  dictating into (WS_EX_NOACTIVATE). If Windows refuses the style, the fob
  turns display-only rather than risk typing into the wrong window.
- On by default; turn it off with its right-click menu, the tray's "Show mic
  fob", or Settings → Voice & Mic. Hiding the fob restores exactly the old
  pill-only behavior.

## v0.32.0 — 2026-07-31 — Live transcript, meeting capture, OSC, Translate

- **Live transcript view.** History gains a Live toggle — a chat-style local
  view that refreshes every 2 s — and an Export button that writes the current
  (searchable) view to a timestamped text file in Documents.
- **Meeting capture (system audio).** A tray toggle transcribes whatever the
  PC is playing — calls, meetings, videos — via WASAPI loopback, in ~8 s
  chunks, into local history (watch it in the Live view; it also feeds the
  notes route). It never types into apps and never touches the clipboard.
  Captured people may need to consent to being recorded where you live; ROAR
  says so when you turn it on. (ROAR Pro)
- **OSC show control.** A new trusted-rule action sends OSC messages to
  lighting desks, QLab, Resolume, or TouchDesigner ("lights up" → your cue).
  Same trust gate as scripts and webhooks. MIDI is future work. (Developer)
- **Translate mode.** Settings → Transcription → "Translate to English":
  dictate in any language and ROAR types English, using Whisper's built-in
  translate task on a multilingual model. Free in every edition.

## v0.31.0 — 2026-07-31 — ROAR Flow

- **Voice automations.** Say a trigger phrase at the start of a dictation and
  ROAR acts on it: open an app, open a URL, press a hotkey chord, insert a
  snippet, speak a reply, or copy text. Rules are managed under
  Settings → Settings → Flow, and never fire mid-sentence.
- **Trusted rules.** Script and webhook actions exist but only run on rules
  you explicitly mark trusted (ROAR Developer feature), and ROAR shows a toast
  naming the rule when one fires. Everything the microphone hears can speak a
  trigger phrase — the gate exists so that fact can't run code by surprise.
- **Multi-channel output routing.** One dictation can now also go to the
  clipboard, a timestamped local notes file, and/or be spoken back — on top of
  normal typing, never instead of it. Toggle by voice ("roar route notes on",
  "roar routes off") or from the new tray "Flow routes" menu. Extra routes
  always start OFF when ROAR starts, and a failing route can never block
  typing.
- Privacy: everything is local. The notes file is opt-in, plain text, at a
  path you choose. A webhook is the only possible network call, exists only
  inside a rule you marked trusted, and sends only that utterance's text, the
  rule name, and a timestamp.

## Unreleased — Pricing

- **New pricing.** ROAR Pro is now $19 once, ROAR Developer $29 once, and ROAR
  Supporter $49 once (was $29 / $49 / $99). Core stays free and unchanged. No
  subscription, no account. Existing licenses keep working, and no feature moved
  between editions.
- Prices now live in one place — `PRICING` in `commercial_config.py`. The
  in-app upgrade copy, the settings screen, the docs, and the website all derive
  from it, and tests fail if any of them drift.
- Renamed "Developer Pack" to **ROAR Developer** in customer-facing copy.
- Rebuilt the website pricing section: four cards, honest trust copy, and buy
  buttons that carry an edition id rather than a price. Added
  `site/purchase/success.html` for a future Stripe redirect — it says a license
  *will be* delivered, and never claims one was sent.
- Added `docs/STRIPE_SETUP.md` (Stripe Payment Links, plus the warning that a
  completed payment is not a delivered license) and
  `docs/WEBSITE_IMPLEMENTATION.md` (the server-side contract, if the site ever
  gets a backend).
- Added `fulfillment.py`: the boundary where automated license delivery would
  live. It validates a request and then refuses, because the signing key is
  deliberately offline.

## Unreleased — Read Aloud

- Added optional, fully local Kokoro-82M Read Aloud for Windows with typed
  text, explicit clipboard/selected-text commands, voice previews, long-form
  chunking, output-device selection, pause/resume/stop/repeat, configurable
  hotkeys, and opt-in dictation read-back.
- Added an isolated Python 3.12 worker over standard pipes so Kokoro/PyTorch
  never load in the Python 3.14 tray or lightweight Settings process.
- Added a hash-pinned, atomic local voice-pack manager; no runtime download,
  network listener, telemetry, generated-audio file, or content-bearing
  diagnostics/status/logging.
- Added UI Automation selected-text retrieval with secure-field fail-closed
  behavior and an explicit opt-in clipboard fallback with sequence-race
  protection.
- Insights now shows estimated dictation time saved using measured recording
  durations and a clearly disclosed 40 WPM typing baseline.
- Added offline integration tests, fake-engine lifecycle tests, accessibility
  checks, a local benchmark, packaging checks, privacy tests, and operator
  documentation.

All notable changes to ROAR. Dates are release-tag dates; entries before a tag
exists are marked unreleased.

## Unreleased — Linux (experimental)
- **ROAR runs on Ubuntu 24.04 (X11)** from the same codebase: XDG paths,
  pynput global hotkey (self-healing), pynput/xdotool text injection, xdotool
  focus tracking, flock single-instance, .desktop autostart, CUDA GPU via the
  nvidia-cu12 wheels (Vulkan is Windows-only). Run-from-source (linux/setup.sh)
  plus an AppImage recipe. Test on 24.04/Xorg per docs/LINUX.md.

## v0.30.0 — 2026-07-28
- **Point & Speak responds instantly.** With the gesture enabled, the voice now
  loads in the background at startup instead of on your first click. Existing
  installs were hit hardest: their config still held `tts_preload_model: false`
  from an older version, so the newer default never applied and the first
  gesture waited on a cold load (115s measured here) — which just read as
  nothing happening.

## v0.29.0 — 2026-07-28
- **Point & Speak reliability in browsers.** The copy now waits for you to let
  go of Ctrl before it runs — sending Ctrl+C while the gesture's own modifier is
  still held produced a malformed chord and a silent empty copy. Failure
  messages are also specific now ("Nothing was copied — select some text first"
  vs "The copied selection came back empty"), so a miss says what happened.

## v0.28.0 — 2026-07-28
- **Point & Speak now works in browsers, PDF viewers and Electron apps.** Two
  fixes: the Ctrl+Right-click gesture is now consumed by ROAR, so the app's
  context menu no longer opens and steal the focus the capture needs (plain
  right-click is untouched); and ROAR asks lazily-accessible apps like Chrome
  and Edge to expose their text, retrying before falling back to the clipboard.
  Verified end-to-end against a real Edge selection.

## v0.27.0 — 2026-07-27
- **Point & Speak now works everywhere.** In apps that don't expose their
  selection to accessibility tools (browsers, PDF viewers, Electron apps), the
  gesture copies your selection with Ctrl+C — only after you trigger it — and
  restores your clipboard afterward, including images and copied files. If
  nothing is selected you get a calm notice; no whole-page reads.

## v0.26.0 — 2026-07-27
- **Point & Speak** — highlight text in any application and **Ctrl +
  Right-click** to hear it read aloud immediately; the same gesture stops it.
  Plain right-click is untouched (the gesture is observed, never consumed).
  Off by default: Settings -> Read Aloud -> Point & Speak. Uses the existing
  privacy-hardened selection capture; elevated windows remain out of reach
  (Windows UIPI).

## v0.25.0 — 2026-07-24
- **Teach ROAR the words it mishears.** If a word comes out wrong every time,
  fix it once and ROAR remembers. It rewrites that word in future dictations —
  and adds what you meant to its vocabulary, so the recognizer is more likely to
  hear it right in the first place.
  - **From History:** press *Teach ROAR* on a past dictation, fix the word in
    place, confirm. ROAR works out which word changed.
  - **From Settings → Dictionary → Corrections:** type what it heard → what you
    meant.
  - Corrections are local, yours, and free in every edition. They never absorb
    your punctuation — only the misheard word changes.
- Landing page now covers Read Aloud and personal corrections.

## v0.24.0 — 2026-07-24
- **Read Aloud (Kokoro TTS)** — ROAR can now speak selected or typed text
  locally and offline using the Kokoro-82M voice model. Runs in an isolated
  Python 3.12 worker; nothing leaves your machine. The model + runtime are
  optional downloads (Settings -> Read Aloud), never bundled in the installer.
- **GPU acceleration** — if an NVIDIA GPU is present, the runtime installs CUDA
  torch and synthesis runs ~10x faster (~0.35s vs ~3.4s per sentence on an RTX
  4060). CPU still works everywhere. A one-time warm-up keeps the first request
  fast, and the model is preloaded + kept warm so speech starts promptly.
- Read Aloud is off until you enable it; Core dictation is unchanged.

## v0.23.0 — 2026-07-17
- **Paid editions now activate.** This build carries the production license key
  and runs in production mode, so a signed Pro/Developer/Supporter license
  imported in Settings → License unlocks its edition — verified offline. Test
  (dev-signed) licenses are rejected.
- **License generator tooling** (owner-side, not shipped in the app):
  `scripts/generate_keypair.py` mints the Ed25519 signing keypair (private key
  kept off the repo); `scripts/issue_license.py` signs a real per-customer
  license (unique id, hashed email, self-verifies against the app key before
  writing). See docs/commercial/LICENSE_FULFILLMENT.md.
- Core is unchanged and still free; existing installs stay grandfathered and
  their settings/history/license survive the upgrade.

## v0.22.0 — 2026-07-11
- Commercial editions are now real and **enforced, with grandfathering**. The
  edition model, entitlements and offline Ed25519 licensing shipped in v0.17.0;
  this release closes the gaps and turns the gates on.
- **Licences actually load now.** There was no `license_path()`, so the edition
  was always Core and no licence was ever read from disk. Licences live at
  `%APPDATA%\ROAR\license.json` — beside config, never in the data dir that
  history/audio clears touch, so clears and upgrades can't remove them.
- **License service + activation UI**: paste or import a licence file, remove it,
  buy links. Import is atomic and validates *before* replacing, so a bad paste
  can never disturb a valid licence. Oversized input is rejected before parsing;
  licence IDs are redacted everywhere.
- **Grandfathering**: every paid-target feature shipped free through v0.21.0, so
  an existing install gets a one-time grant of exactly those features — **nobody
  loses anything they already had**. New installs are gated. A grant is feature
  IDs only and never confers an edition; never-shipped features stay Developer-
  only for everyone.
- **Gates run in the backend**, not the markup: the pipeline resolves settings
  *down* to what you're entitled to (code→clean, snippets/profiles withheld), so
  a gate can never break plain dictation, and your paid settings are preserved —
  drop to Core and back and everything reactivates untouched.
- One reusable upgrade prompt, shown only on intentional paid-feature
  interaction — never at startup, never during dictation, no countdowns, no
  "trial expired", and Core is never called a trial.
- Core is untouchable: dictation, offline use, privacy controls, history/audio
  deletion and retention toggles are free in every edition, forever.
- Docs: commercial audit, security review, release checklist; FEATURE_MATRIX
  records the grandfathering decision and marks unbuilt features **planned**.
- Pricing stays **$29 / $49 / $99** (the brief's $19/$29/$49 table was stale).
  Purchase URLs + the production key remain placeholders — see
  docs/commercial/RELEASE_CHECKLIST.md before charging.

## v0.21.0 — unreleased (source)
- Real AMD / Intel GPU acceleration via a new **whisper.cpp Vulkan** backend
  (Vulkan is vendor-agnostic — any Vulkan-1.3 GPU). Opt-in from Settings
  ("Engine: AMD / Intel GPU (Vulkan)"); selecting it downloads a small,
  checksum-verified GPU binary + model once (inbound-only, never in the
  dictation path), then transcribes on a warm local `whisper-server` subprocess
  bound to loopback — 100% offline. If it can't start, ROAR falls back to the
  CTranslate2 CPU/CUDA path automatically. Validated on GPU hardware
  (~0.3s/11s clip); NVIDIA CUDA and CPU paths are unchanged.
- Replaces the honest-but-dead DirectML scaffold as the AMD GPU story.

## v0.20.1 — unreleased (source)
- CPU / AMD Ryzen perf: set CTranslate2 `cpu_threads` to the physical-core
  estimate (logical//2 on SMT chips, capped 16) instead of ct2's default,
  which oversubscribes SMT. Measured ~20% faster CPU transcription
  (2197ms -> ~1770ms, small.en int8, 16-logical laptop). New `cpu_threads`
  config (0=auto; >0 explicit), shown in Diagnostics; changing it reloads.

## v0.20.0 — unreleased (source)
- GPU/perf hardening: automatic NVIDIA CUDA fast path made config-driven —
  `hardware_accel.py` detection + device/compute selection with a safe fallback
  ladder; Fast/Balanced/Accurate presets (precision + beam only, never the
  model, so no preset ever downloads); Acceleration + Compute-type controls in
  Settings; always keeps the CPU int8 fallback attempt.
- Real release-to-text latency instrumentation (record/transcription/injection
  ms) surfaced in Diagnostics + the Home dashboard (the old "latency" was
  mislabeled audio length). Model stays warm (unchanged; never per-dictation).
- `scripts/benchmark_transcription.py` (offline). Measured RTX 4060: CPU int8
  2079 ms vs CUDA float16 288 ms / int8_float16 259 ms (~8× faster; Fast ~10%
  under Balanced).
- Backend seam (`backends/`) + honest experimental DirectML spike: AMD/DirectML
  is **unavailable** (no false claim) and falls back cleanly to CUDA/CPU with a
  diagnostics reason. `requirements-directml.txt` is opt-in only.
- CPU-only installs unchanged; no network added to the transcription path; no
  transcript ever written to logs/status/diagnostics (allowlists enforce it).

## v0.19.0 — unreleased (source)
- Reconciled the Home dashboard (v0.18.0) and the commercial scaffold (v0.17.0)
  onto one `main`. Both were developed in parallel off v0.16.0; this is their
  union. No behavior change beyond that; runtime feature gates stay OFF.

## v0.18.0 — unreleased (source)
- ROAR Home dashboard (P1): the Settings window opens to a polished Home view
  ("Talk. Type. Locally.") showing real local state — live dictation status,
  session/last-transcription/active-profile cards, settings summary, and a
  status bar — via a one-way `status.json` the tray writes (operational facts
  only, never transcript/clipboard/audio/window titles). Added as the default
  first sidebar item; all existing sections stay reachable. Live status polls
  only while Home is visible; reduced-motion freezes the mic/waveform. No new
  network, deps, or external assets.
- ROAR Home dashboard (P2): sidebar re-mapped to the 8-item IA — Home / Profiles
  / Insights / History / Dictionary / Hotkeys / Settings / About. Profiles and
  Dictionary split out of Transcription; General/Voice/Transcription/Privacy/
  Snippets grouped under a Settings overview (kept intact, reachable, never
  gated).
- ROAR Home dashboard (P3): optional remote Start/Stop + Scratch-that from Home
  via a local `command.json` (fixed command names only), behind the
  `dashboard_controls` config flag (OFF by default). When off, the buttons show
  hotkey guidance.

## v0.17.0 — unreleased (source)
- Commercial scaffold: reconciled licensing into one canonical, offline-signed
  model (`commercial_config.py`, `entitlements.py`, `license.py`) with real
  Ed25519 verification behind a `SignatureVerifier` interface, verify-before-trust,
  fail-closed to Core, and dev-license rejection in production builds.
- Full diagnostics redaction (`redact_diagnostics`), a calm **display-only**
  license card in Settings, dev-only license generate/verify scripts, and a
  pure upgrade-prompt copy helper (not wired to gate anything).
- Commercial docs: monetization, pricing, FAQ, founder readiness, support,
  refund policy, privacy promise, checkout setup, readiness checklist; README
  pricing block; LICENSING updated to the real implementation.
- **Runtime feature gates remain OFF** — the feature matrix is policy only;
  privacy controls and history/audio deletion stay free, and nothing users have
  today is removed.

## v0.16.0 — unreleased (source)
- Expanded app profiles: `code` (verbatim), `casual` (texting style, keeps
  slang), `formal` (polished) with a large built-in app map (VS/JetBrains/
  terminals; WhatsApp/Discord/Ableton/Spotify; Outlook/Word), Ableton prefix
  matching, browser-title routing (browser-scoped), and user overrides
  (`app_profiles` config + Settings UI).
- Red-team hardening pass: focus-change injection guard, clipboard size
  bounds, safe diagnostics + Safe Mode, appearance (light/dark/system),
  snippet `{clipboard}` cap + UI flags, milestone/log reset actions,
  entitlement primitives + licensing/privacy/release docs.

## v0.15.1 — 2026-07-05
- Rolling launch-time backups of the history DB (keep 5) via SQLite online
  backup API.

## v0.15.0 — 2026-07-05
- Context-aware formatting (first cut): verbatim in code editors/terminals,
  terser in chat apps; `context_aware` toggle.
- Double-tap hands-free dictation (double-tap PTT to lock, tap to stop),
  `double_tap_ms` setting. (Built as v0.14.0; first released here.)
- CRITICAL fix: WAL checkpoint after every dictation and on close — a force-
  killed app could previously strand committed history rows in the WAL
  sidecar (data loss).

## v0.13.0 — 2026-07-04
- Private, offline word-count milestones (9 badges, sticky unlocks, tray
  notification) in Insights; lavender ROAR logo in About. Repo made public;
  history DB migrates v2→v3 (`badge_unlocks`).

## v0.12.0 — 2026-07-04
- "Scratch that" spoken undo (standalone utterance, same-window guard,
  UTF-16-exact backspacing, history rollback).
- Manual check-for-updates (GitHub tags, click-only). About credits.

## v0.11.1 — 2026-07-04
- Slim white + lavender capsule overlay (one-row, no status dot, pixel-clamped
  preview text).

## v0.11.0 — 2026-07-04
- Speech cleanup: interjections, stutter collapse, false starts; opt-in
  comma-bounded discourse-filler removal.

## v0.10.0 — 2026-07-03
- ROAR Snippets ("snippet name" / literal `/name`, variables
  {date}/{time}/{clipboard}, packs import/export, Settings tab).
- Multilingual models bundled in the installer (offline language switching).
- Installer moved to external CABs (`.msi` format is capped at 2 GB); later a
  single-file 7-Zip SFX setup exe wraps msi+cabs.

## v0.9.0 — 2026-07-03
- Multilingual dictation: language picker (auto + 100 codes), model policy
  fork (distil-large-v3 is English-only → large-v3-turbo / small).

## v0.8.0 — 2026-07-03
- Cinema Dark settings refresh (indigo accent, SVG iconography, contrast
  fixes).

## v0.7.0 — 2026-07-03
- Streaming preview overlay (waveform pill + live partial text), soft chimes,
  overlay/streaming toggles.

## v0.6.0 — 2026-07-02
- Product renamed FlowLocal → ROAR (exe, installer, data dirs migrated
  in place; GitHub repo renamed).

## v0.5.0 — 2026-07-02
- Custom vocabulary + auto signature-word hotwords.

## v0.4.0 — 2026-07-02
- Insights (totals, activity, pace, top/signature words) + history search.

## v0.3.0 — 2026-07-02
- Local dictation history (SQLite) + privacy controls (retention, delete).

## v0.2.0 — 2026-07-02
- Settings window (pywebview), hotkey capture, autostart, hot-apply config.

## v0.1.0 — 2026-07-02
- Core tray app: push-to-talk local dictation (faster-whisper), SendInput
  injection, packaged exe + MSI.
