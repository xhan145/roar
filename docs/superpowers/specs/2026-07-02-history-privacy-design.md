# FlowLocal History + Privacy — Design Spec

**Date:** 2026-07-02
**Status:** Approved (interactive brainstorm; recommended defaults accepted)
**Sub-project:** 2 of 6 in the FlowLocal upgrade track. Builds on SP1 (settings shell). Fills the placeholder Privacy + History tabs. SP3 (word analytics + speech profile) will read the same store.

## Goal

Give FlowLocal a local dictation history and privacy controls: every transcript optionally saved to a local SQLite store, opt-in audio retention ("delete after use, or keep for X days"), and functional History + Privacy tabs in the existing Deep Focus settings window. 100% local, no telemetry.

## Locked decisions

- **History default ON.** All local; the Privacy tab provides a master toggle and a Delete-all button.
- **Audio retention = preset dropdown:** Off (default; delete-after-use, today's behavior) / 1 / 7 / 30 / 90 days. Auto-purge sweeper enforces it.
- **History v1 = list + copy + per-item delete + clear-all.** Search + analytics + speech profile deferred to SP3.
- **Storage = SQLite** (`sqlite3` stdlib, zero new deps) at `%LOCALAPPDATA%\FlowLocal\history.db`, WAL mode.
- **Version:** ships as v0.3.0.

## Architecture

New module `history.py` owns the DB and audio files. Pure-ish data layer; the tray app and settings bridge both call into it.

```
tray app _handle_transcription --record()--> history.py --> history.db (+ audio/<id>.wav)
settings bridge (SettingsAPI)  --list/delete/clear/stats--> history.py
config-watcher thread          --purge_expired() hourly---> history.py
```

### Schema (single table, created on first open)
```sql
CREATE TABLE IF NOT EXISTS dictations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc      REAL    NOT NULL,      -- time.time() at record
    text        TEXT    NOT NULL,
    char_count  INTEGER NOT NULL,
    word_count  INTEGER NOT NULL,
    model       TEXT,
    audio_path  TEXT                   -- NULL unless retention > 0
);
CREATE INDEX IF NOT EXISTS idx_dictations_ts ON dictations(ts_utc);
```
`user_version` PRAGMA = 1 (migration hook for SP3).

### history.py interface
- `db_path()` / `audio_dir()` — from paths.py (frozen-aware).
- `class History(db_path=None)` — opens/creates DB, WAL. Methods:
  - `record(text, model, audio=None, retention_days=0, ts=None) -> int` — insert row; if `retention_days > 0` and `audio is not None`, write `audio_dir()/<id>.wav` (16 kHz mono float32 → int16 WAV via stdlib `wave`) and store its path. Returns row id. Never raises to the caller for disk/DB errors — logs and degrades (transcript still saved even if audio write fails).
  - `list(limit=100, offset=0) -> list[dict]` — reverse-chron rows as dicts (includes `has_audio`).
  - `delete(id) -> None` — remove row + its audio file.
  - `clear() -> int` — delete all rows + all audio files; returns count removed.
  - `stats() -> dict` — `{count, audio_count, audio_bytes}`.
  - `purge_expired(retention_days) -> int` — delete rows/audio older than cutoff; if `retention_days == 0`, delete ALL audio files + null all `audio_path` (transcripts kept). Returns rows/files purged.
  - `close()`.
- Thread-safety: one `threading.Lock` around all connection use (SQLite connection created with `check_same_thread=False`; tray, settings, and watcher may all call). The settings process uses its own `History` instance/connection — separate process, WAL handles concurrent readers/writers.

## Data flow

- **Capture** (`app.py:_handle_transcription`, after successful `inject_text`): if `cfg["history_enabled"]`, call `self.history.record(text, model=self.transcriber.active_model, audio=(audio if cfg["audio_retention_days"] > 0 else None), retention_days=cfg["audio_retention_days"])`. Wrapped in try/except that logs and never breaks dictation.
- **Purge:** `_watch_config` loop gains a throttled call (on first tick and once per hour of wall-clock ticks) to `self.history.purge_expired(cfg["audio_retention_days"])`. Toggling retention to a shorter window or Off purges on the next sweep.
- **History instance lifecycle:** created in `FlowLocalApp.__init__`, closed in `_quit`.

## Config additions (config.py DEFAULTS)
```json
"history_enabled": true,
"audio_retention_days": 0
```
- `diff_config`: no action needed — both read at use time (add nothing, they simply aren't hotkey/model/device).
- Settings `INSTANT_KEYS`: add `"history_enabled"`, `"audio_retention_days"` (validated: enabled=bool; retention ∈ {0,1,7,30,90}).

## Bridge additions (settings_ui.SettingsAPI)
- `history_list(limit=100) -> list[dict]`
- `history_delete(id) -> {ok} | {error}`
- `history_clear() -> {ok, removed}`
- `privacy_stats() -> {count, audio_count, audio_mb}`
- `set_value` extended to accept the two new instant keys (retention validated against the allowed set; on change to a shorter/Off value, call `History.purge_expired` immediately so the Privacy stat updates without waiting for the tray sweep).

## UI (existing placeholder tabs, Deep Focus tokens)

- **History tab:** reverse-chron list of `.row` cards — relative time ("2m ago"), transcript (2-line clamp), word count, 🔊 when audio kept; each card has **Copy** and **Delete**; a **Clear all** button (two-step confirm: label flips to "Click again to confirm"). Empty state: "No dictations yet — hold your hotkey and speak." Rendered from `history_list`; text inserted via `textContent` (never innerHTML) to stay injection-safe.
- **Privacy tab:** **Save dictation history** toggle (→ `history_enabled`); **Keep audio recordings** dropdown Off/1/7/30/90 days (→ `audio_retention_days`) with caption "Off deletes audio right after transcription."; a live stat line from `privacy_stats` ("142 dictations · 3 clips · 8.2 MB"); a red **Delete all history & audio** button, two-step confirm, calls `history_clear`.

## Error handling

- DB open/corruption → move the bad file aside (`history.db.corrupt-<ts>`) and recreate; log once; app keeps running.
- WAV write failure (disk full/permission) → skip audio, keep transcript, `notify` once per session.
- Delete of a missing audio file → ignored.
- Settings and tray both writing: WAL + per-connection lock; deletes/clears from settings are visible to the tray's next read (fresh queries, no long-lived cursors).

## Testing

- `tests/test_history.py` (temp DB via tmp_path): record→list round-trip; word_count/char_count correctness (incl. multi-space, newlines from "new paragraph"); audio WAV written only when retention>0 and readable back as 16 kHz mono; delete removes row+file; clear empties + returns count; `purge_expired` cutoff (rows at boundary kept/removed correctly; retention 0 nulls audio but keeps transcripts); corrupt-DB recovery; stats math.
- `tests/test_settings_bridge.py` additions: new bridge handlers against a temp DB; retention value validation; instant-key extension.
- Settings smoke probe updated (nav count unchanged at 7; assert History/Privacy render their controls, not the "soon" panels).
- Full existing suite stays green.
- Packaging: no new bundle files (pure stdlib); rebuild exe + MSI at v0.3.0; verify History/Privacy work in the frozen build; install/uninstall cycle; **uninstall/data note:** history.db + audio live in `%LOCALAPPDATA%\FlowLocal` (user data) and are intentionally NOT removed by MSI uninstall — documented in README.

## Out of scope (→ SP3)

Search over transcripts, word-frequency analytics, the speech/talking-style profile, charts, export.
