# 14-Day Full-Feature Trial

An explicit, offline, one-per-machine trial of everything in ROAR Pro and
ROAR Developer. When it ends, ROAR Core keeps working, forever, and nothing
the user made is touched.

## Product rules

- The trial **begins only** when the user clicks **Start 14-Day Trial** in
  Settings → About. Installing, launching, or upgrading ROAR never starts it.
- It lasts exactly `timedelta(days=14)` from that moment (`trial.TRIAL_DURATION`
  — not configurable, not user-editable, enforced in production).
- While active, the effective edition is `trial`, which carries the full
  Developer feature set (`entitlements._BY_EDITION["trial"]`).
- No account, no payment card, no subscription, no internet. Ever.
- A valid paid licence **always** outranks the trial — even ROAR Pro, although
  the trial temporarily granted more. Priority:
  `supporter/developer/pro licence > active trial > core`.
- At expiry: ROAR stays open, Core dictation keeps working, an active
  recording is never interrupted, and no settings, snippets, profiles, tags,
  vocabulary, or history are deleted. Paid-feature *execution* locks; the
  saved configuration stays intact and returns the moment a licence activates.
- One calm ended notice, ever (see below). Locked features show contextual
  upgrade options only when the user intentionally selects them.

## Architecture

Three layers, mirroring the licence system:

| Layer | Module | Responsibility |
|---|---|---|
| Pure state | `trial.py` | UTC record model, `TrialStatus`, boundaries, whole-day countdown, HMAC integrity signing, `resolve_effective_edition` |
| Persistence | `trial_store.py` | `TrialService`: protected file + registry marker, self-healing, last-seen bookkeeping, rollback detection |
| Runtime | `access.py` | `effective_edition()` — the one place licence and trial combine; `can()`/`requires_upgrade()` consult it (cached ~30 s) |

Status vocabulary (the UI never reads raw timestamps):
`not_started · active · expired · invalid · clock_rollback_detected · licensed`.

### Storage

Two lightweight local indicators hold the same signed envelope:

- `%APPDATA%\ROAR\trial.json` — beside `license.json`, deliberately **not** in
  the `%LOCALAPPDATA%` tree that holds history/audio, so privacy resets,
  history clears, audio deletion, and normal MSI upgrades can never touch it.
- `HKCU\Software\ROAR\TrialState` — a registry copy, so deleting the file (or
  an uninstall/reinstall that removes files) does not quietly grant a second
  trial. Whichever copy has the **earliest** start date wins; missing copies
  self-heal from the survivor.

The envelope's HMAC key is protected with **Windows DPAPI** (current-user
scope, `ctypes`/`crypt32`, lazily imported); elsewhere, or if DPAPI fails, the
key falls back to plain storage. This is honest best-effort protection against
accidental resets and trivial deletion — **it is not DRM and is never
advertised as such**. No hardware fingerprint is collected, and no private
keys or reusable production secrets ship in the app.

The record contains only:
`schema_version, trial_id (random UUID), started_at_utc, expires_at_utc,
last_seen_at_utc, expired_notice_seen, signature` — never transcripts, audio,
history, clipboard, vocabulary, or window titles (pinned by tests).

### Clock rollback

Each successful read advances a monotonic `last_seen_at_utc` high-water mark.
If the current UTC time is more than **5 minutes**
(`trial.CLOCK_TOLERANCE`) before it, status becomes
`clock_rollback_detected`: paid trial features lock, Core stays available, a
valid licence still overrides, the Settings card explains the clock moved
backward and offers **Try Again**, and the state is never destroyed — fixing
the clock recovers on the next read.

### Expiry UX

- The tray fires **one** notification at the first transition to IDLE after
  expiry (never while recording/transcribing, never when licensed), marking
  `expired_notice_seen` in the record *before* notifying so it can never
  repeat — not on the next launch, not ever.
- The Settings card shows the ended state with four actions (Buy ROAR Pro,
  Buy ROAR Developer, Enter License, Continue with ROAR Core); visiting the
  page also counts as seeing the notice.
- No countdown timers in hours/minutes/seconds, no fake urgency, no repeated
  modals, nothing over the transcription overlay.

### Licence activation during a trial

`license_service.import_license` validates offline as always; on success
`access.effective_edition()` immediately resolves to the purchased edition,
all trial messaging stops, and the historical trial record is kept (for
diagnostics and duplicate-trial prevention) — never deleted.

## Configuration

`config.py` defaults: `trial_enabled`, `trial_expiry_notice_enabled`,
`trial_status_badge_enabled` (no Settings controls expose them), plus an
informational `trial_duration_days: 14` — `trial.TRIAL_DURATION` is
authoritative and tests inject clocks/storages through `TrialService(path=,
marker=, protection=)` seams instead. There is **no environment-variable
bypass** and no magic key (pinned: first-party code contains no `ROAR_TRIAL`
env read).

## Diagnostics

Display facts only: `effective_edition`, `trial_status`, `trial_started`,
`trial_expires`, `trial_days_remaining`. The trial id, signature, key
material, DPAPI blobs, and registry values never enter reports —
`diagnostics.SAFE_KEYS` is an allowlist and tests pin the redaction.

## Known limitations (by design)

Offline trial enforcement is best-effort: a user with admin rights who
deletes both the file and the registry marker, or hand-rolls the clock while
never letting a newer `last_seen` persist, can defeat it. That trade is
accepted — the alternative (accounts, activation servers, fingerprinting)
would break ROAR's core privacy promise. Revenue protection comes from the
signed-licence system, honest pricing, and goodwill, not surveillance.

## Test map

`tests/test_trial.py` (pure boundaries, signing, resolution),
`tests/test_trial_store.py` (persistence, healing, rollback, atomicity),
`tests/test_trial_resolution.py` (entitlements + access priority chain),
`tests/test_trial_ui.py` (bridge, Settings card copy/ids, one-time notice),
`tests/test_trial_hardening.py` (preservation, privacy, offline, packaging,
diagnostics redaction). All use fake clocks — no test waits in real time.
