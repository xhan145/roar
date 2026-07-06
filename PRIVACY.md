# ROAR privacy

ROAR is a local-first dictation app. The short version: **your voice and your
words never leave your machine.**

## What ROAR stores, and where

Everything lives in per-user folders you control:

| Data | Location | Controls |
|---|---|---|
| Settings | `%APPDATA%\ROAR\config.json` | Edit or delete freely |
| Dictation history (transcripts) | `%LOCALAPPDATA%\ROAR\history.db` | History toggle, per-row delete, Clear all |
| Retained audio (optional, OFF by default) | `%LOCALAPPDATA%\ROAR\audio\` | Retention Off/1/7/30/90 days; Delete all |
| Rolling history backups (last 5) | `%LOCALAPPDATA%\ROAR\backups\` | Delete the folder any time |
| Log | `%LOCALAPPDATA%\ROAR\roar.log` | Clear Log button; contains counts and states, never transcript text |
| Milestone badges | inside `history.db` | Reset Milestones button |

## Network

ROAR makes **no network calls on its own** — no telemetry, no analytics, no
accounts, no cloud transcription, no auto-update. The single exception is the
**Check for updates** button in About, which fetches the latest version tag
from GitHub only when you click it. A test suite invariant enforces that this
remains the only network call site.

## What never leaves the app

Transcripts, audio, clipboard contents, snippets, vocabulary, and window
titles are used in-process only. Window titles (for app profiles) are read at
the moment of dictation and are never stored or logged. Safe Diagnostics
reports are filtered through an allowlist and redact private paths.

## Deleting everything

Uninstall removes the program. Your data folders above are deliberately left
behind (uninstall should never destroy user data silently) — delete
`%APPDATA%\ROAR` and `%LOCALAPPDATA%\ROAR` to remove every trace.
