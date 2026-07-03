# FlowLocal Custom Vocabulary — Design Spec

**Date:** 2026-07-03
**Status:** Approved (design presented 2026-07-03; user "go")
**Sub-project:** 4 of 6. Consumes SP3's signature words. Ships as v0.5.0.

## Goal

Bias transcription toward the words that matter to this user: a hand-edited custom dictionary plus (optionally) the top signature words from dictation history, merged and passed to faster-whisper's `hotwords` parameter on every transcription. Closes the loop the Insights tab teased ("these will boost transcription accuracy").

## Locked decisions

- **Mechanism: `hotwords`** (verified present in faster-whisper 1.2.1 `WhisperModel.transcribe`). NOT `initial_prompt` (its punctuation/phrasing style leaks into output) and NOT fine-tuning (out of scope).
- **Two merged sources:** config `custom_vocabulary` (user-edited list) + top 10 signature words from history when `auto_vocabulary` is true (default true). Deduped case-insensitively, custom words first, capped at 60 total.
- **Refresh policy:** the tray app builds the hotwords string at model load and refreshes it every 25 dictations (signature words drift slowly). Custom-vocabulary or auto-toggle config changes rebuild immediately via the config watcher.
- **UI:** a "Vocabulary" card inside the existing **Transcription** tab (no new nav; navs stay 8): chip editor (type + Enter to add, × to remove, instant-apply), "Include my signature words automatically" toggle (instant), read-only row of the current auto words.
- **Validation:** entries 2–40 chars after trim; max 50 custom entries; case-insensitive dedupe; printable text only (no control chars).

## Components

### vocabulary.py (new, pure)
- `merge_hotwords(custom: list[str], signature: list[str], cap: int = 60) -> str | None` — trims, drops empties/dupes (case-insensitive, custom wins), joins with single spaces, returns None when empty.
- `validate_entry(word: str, existing: list[str]) -> str | None` — returns error string or None; rules above (2–40 chars, ≤50 entries, no duplicates, printable).

### config.py
DEFAULTS += `"custom_vocabulary": []`, `"auto_vocabulary": True`.

### transcriber.py
- `Transcriber` gains `self.hotwords: str | None = None` (plain attribute; set by the app).
- `_run` passes `hotwords=self.hotwords` to `model.transcribe`.

### app.py
- `_rebuild_hotwords()`: signature = SP3 path (`compute_insights(self.history.list(limit=5000))["signature_words"]` when `cfg["auto_vocabulary"]` and history enabled, else `[]`); `self.transcriber.hotwords = merge_hotwords(cfg["custom_vocabulary"], signature)`. Wrapped: failure logs and leaves previous hotwords (custom-only fallback on insights failure).
- Called: after model load in the worker; every 25th dictation (counter in `_handle_transcription`); and on config change — `diff_config` gains `("rebuild_hotwords", None)` when `custom_vocabulary` or `auto_vocabulary` differ (watcher handles it).

### settings bridge (settings_ui.py)
- `set_value` accepts `auto_vocabulary` (bool coerce) as an instant key.
- `vocab_get() -> {custom: [...], auto_enabled: bool, auto_words: [...]}` (auto words computed live from history).
- `vocab_add(word) -> {ok, custom} | {error}` (validate_entry; appends; writes config).
- `vocab_remove(word) -> {ok, custom}` (case-insensitive removal; writes config).

### settings.html (Transcription tab)
Vocabulary card below the model list: chip row (custom words as removable chips), input + Add on Enter, inline error line, auto toggle, muted "Auto: word1 · word2 · …" row (or "none yet — dictate more"). All text via `textContent`. Probe extends: `vocab=1` when the input exists.

## Error handling

- Empty merged vocabulary → `hotwords=None` (exactly today's behavior — no regression risk).
- Insights/signature computation failure → keep previous hotwords; log.
- Bridge validation errors surface inline; config never gets malformed entries (list filtered to strings on load, mirroring the replacements guard).

## Testing

- `tests/test_vocabulary.py`: merge (dedupe case-insensitive, custom precedence, cap, None-when-empty, whitespace trim); validate_entry (length bounds, duplicate, 50-cap, control chars).
- `tests/test_transcriber.py` addition: stub model captures kwargs — `hotwords` reaches `model.transcribe`; None by default.
- `tests/test_diff_config.py` addition: vocabulary/auto changes → `("rebuild_hotwords", None)`; single action when both change.
- Bridge tests: vocab_get/add/remove round-trip on tmp config + validation errors; auto_vocabulary instant key.
- Capture test: `_rebuild_hotwords` sets transcriber.hotwords from config + seeded history (monkeypatched paths).
- Smoke probe: `vocab=1`. Version asserts → 0.5.0.
- Live sanity (non-gating): dictate a signature word once via the SAPI harness.
- Release train: exe + MSI v0.5.0 (installer now hardened: atomic build, purge, same-version upgrade), install-over-current + single-registration check via `ProductsEx`, adversarial review pre-push, tag v0.5.0, relaunch installed copy.

## Out of scope

Per-app vocabularies, pronunciation/phonetic hints, model fine-tuning, streaming (SP5), multilingual (SP6).
