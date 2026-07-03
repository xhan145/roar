# FlowLocal Insights & Speech Profile — Design Spec

**Date:** 2026-07-03
**Status:** Approved (design accepted with recommended defaults: Insights tab, duration migration, vocabulary teaser)
**Sub-project:** 3 of 6. Reads the SP2 history store; adds the Insights tab, speech profile, and History search. SP4 (custom vocabulary → transcription hints) consumes the signature-words output.

## Goal

"Track word use, develop a profile based on how users talk": a local analytics view (word usage, activity, speaking pace) and a rule-based speech profile computed purely from the existing dictation history — plus a search box on the History tab. Ships as v0.4.0.

## Locked decisions

- **Compute-on-read**: analytics are pure functions over `history.db`. No new stores, no background aggregation. History toggle/Clear-all/retention from SP2 automatically govern the profile ("your profile is a view of your history").
- **New Insights tab** in the settings sidebar (nav count 7 → 8; smoke probe updated AND clicks the new tab).
- **Duration migration**: schema `user_version` 1 → 2, `ALTER TABLE dictations ADD COLUMN duration_s REAL`. Capture threads `duration_s = len(audio)/SAMPLE_RATE` through `record()`. Old rows have NULL duration and are excluded from pace math.
- **Signature words teaser**: read-only list; explicitly labeled as feeding transcription hints in a future update.
- Charts are hand-rolled CSS/HTML (no chart libs — pywebview local file, zero deps, Deep Focus native).

## Components

### insights.py (new, pure — no I/O)
`compute_insights(rows: list[dict], now: float | None = None) -> dict`
`rows` = History.list() dicts extended with `duration_s`. `now` injectable for tests. Returns:
```python
{
  "totals": {"dictations": int, "words": int, "avg_words": float},
  "activity": [{"date": "YYYY-MM-DD", "dictations": int, "words": int}] ,  # last 14 days, zero-filled, oldest first
  "pace": {"median_wpm": float | None, "recent_wpm": float | None},        # None when no durations
  "top_words": [[word, count]],        # top 15; lowercase, alpha-only, len>=3, stopwords filtered
  "signature_words": [word],           # top 10 by count where len>=5 and not a stopword
  "profile_sentences": [str],          # 2-3 deterministic sentences; [] when < 5 dictations
}
```
- Word extraction: `re.findall(r"[a-zA-Z']+", text.lower())`, strip leading/trailing `'`, drop len<3, drop stopwords (inline ~120-word English list).
- WPM per row: `word_count / (duration_s / 60)` for rows with `duration_s and duration_s > 0.5`; `median_wpm` over all such rows, `recent_wpm` over those in the last 7 days. Round to whole numbers.
- Profile sentences (rule-based, only when >= 5 dictations): length habit (avg_words <10 "short bursts" / <25 "medium-length thoughts" / else "long-form passages"), pace (median_wpm: <110 "measured", <150 "conversational", else "brisk") when available, and top-word flavor ("You reach for 'X' more than any other word.").

### history.py changes
- SCHEMA (used for fresh DBs) now includes `duration_s REAL` and fresh DBs are stamped `user_version=2` directly. Migration in `_open()` handles pre-existing v1 files only: if `PRAGMA user_version` < 2 and the column is absent (checked via `PRAGMA table_info`), run `ALTER TABLE dictations ADD COLUMN duration_s REAL`, then stamp `user_version=2`.
- `record(..., duration_s=None)` stores the new column.
- `list(limit, offset, query=None)`: optional substring search — `WHERE text LIKE ? ESCAPE '\'` with `%`/`_`/`\` escaped, parameter-bound. Returned dicts include `duration_s`.

### app.py changes
- `_handle_transcription`: pass `duration_s=len(audio) / recorder_mod.SAMPLE_RATE` into `record_history` → `hist.record`.

### settings bridge (settings_ui.py)
- `get_insights() -> dict`: `compute_insights(self._history.list(limit=5000))`; empty history → the natural empty payload (never an error).
- `history_list(limit=100, query=None)` passes the search string through.

### settings.html
- Sidebar: **Insights** entry between Transcription and Privacy (8 navs).
- Insights section (Deep Focus): 3 stat tiles (dictations / words / avg length, tabular figures); 14-day activity bar chart (CSS flex columns, height ∝ words, value labels on hover title + count under bar — not color-only); pace card ("— " when no durations yet); top-words horizontal bars (width ∝ count, word + count labels); signature-words chips with caption "These will boost transcription accuracy in a future update"; profile sentences block. Empty state when totals.dictations == 0: "Dictate a few times to build your profile."
- History tab: debounced (300 ms) search input above the list; renderHistory(query) uses it; clearing the box restores the full list.
- All dynamic text via `textContent` (SP2 rule).

## Error handling

- Empty/disabled history → empty-state payloads throughout; never an error dialog.
- Migration failure (locked/corrupt) → existing corrupt-recovery path (move aside + recreate at v2, logged).
- Search strings parameter-bound; LIKE wildcards escaped.
- get_insights over a huge history: capped at the 5000 most recent rows.

## Testing

- `tests/test_insights.py`: totals/avg math; activity zero-fill + ordering + 14-day window (injected `now`); WPM median + recent split; rows without duration excluded; stopword/short-word/apostrophe filtering; signature-word selection; profile sentences thresholds (absent <5 dictations, pace sentence absent without durations); empty input.
- `tests/test_history.py` additions: fresh DB is user_version 2 with duration_s; opening a REAL v1 DB (constructed in-test without the column, user_version=1) migrates in place preserving rows; record stores duration; search matches/escapes (`%`, `_`) and misses.
- Bridge: `get_insights` shape on empty + seeded DB; `history_list(query=...)`.
- Capture integration: duration recorded (≈ len/16000).
- Smoke probe: navs=8, insights tab click activates, retention control still present. Version assertions → 0.4.0.
- Release train: exe + MSI v0.4.0, install/uninstall (+data preserved), adversarial review before push, tag v0.4.0, relaunch.

## Out of scope (later sub-projects)

Vocabulary → Whisper hints (SP4), streaming (SP5), multilingual (SP6), CSV export, per-app stats.
