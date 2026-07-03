# ROAR Multilingual Dictation — Design Spec

**Date:** 2026-07-04
**Status:** Approved ("approved work autonomously")
**Sub-project:** 6 of 6 — closes the original upgrade queue. Ships as v0.9.0.

## Goal

Dictate in any of Whisper's 100 languages, or let it auto-detect per
utterance. A Language dropdown (Transcription tab, Apply-gated with model)
plus a model auto-policy that forks to multilingual variants — because the
current GPU pick `distil-large-v3` is English-only.

## Locked decisions

- **Model policy fork** (`resolve_model(name, device, language)`):
  auto + en → gpu `distil-large-v3` / cpu `small.en` (unchanged);
  auto + non-en-or-auto → gpu **`large-v3-turbo`** / cpu **`small`**
  (aliases verified present in faster-whisper 1.2.1). Explicit model names
  are honored as-is (user's responsibility; caption warns .en models are
  English-only).
- **`config.language`**: existing key; values `"auto"` or an ISO code from
  faster-whisper's `_LANGUAGE_CODES` (100). Sanitized on load: unknown value
  → `"en"` + log line. Default stays `"en"`.
- **Transcribe call**: `language=None` when `"auto"` else the code —
  per-utterance detection. Applies to finals AND streaming partials.
- **UI**: Language dropdown in Transcription tab above the model list;
  "Auto-detect" + 100 languages, a curated common set first (en, es, fr, de,
  it, pt, nl, pl, ru, uk, zh, ja, ko, ar, hi, tr) then the rest
  alphabetically, labels "native name (code)" where the static table knows
  the native name, else the code. Apply-gated WITH model (shared Apply
  button): `apply_model(name, language)` bridge signature grows; caption
  notes a language switch may download a new model (~1.6 GB for turbo).
- **diff_config**: language change → existing `("reload_model", model)`
  action (worker reload path re-resolves with the new language; the reload
  handler also refreshes `transcriber.language`).
- **MODEL_CHOICES** += `"small"`, `"large-v3-turbo"` (captions mark
  multilingual); existing entries keep captions, `.en` ones marked
  "English only".
- Probe adds `lang=1` (dropdown present). Version v0.9.0.

## Components

- `transcriber.py`: `resolve_model(name, device, language="en")`;
  `Transcriber.language` semantics: stores config value; `_run` passes
  `None if self.language == "auto" else self.language`. `load()` resolves
  with current language.
- `config.py`: sanitize `language` on load (membership in codes ∪ {"auto"};
  static tuple imported lazily from faster_whisper.tokenizer with hardcoded
  fallback set of the 16 common codes if import fails).
- `app.py`: `diff_config` adds language-change → reload_model; reload worker
  branch sets `self.transcriber.language = self.cfg["language"]` before
  load; `_rebuild_hotwords` unchanged.
- `settings_ui.py`: `apply_model(name, language)` (validates both; writes
  both keys); `get_state` gains `languages` list [[code, label]] built from
  a static LANGUAGE_LABELS table (common 16 with native names) + remaining
  codes; INSTANT_KEYS unchanged (language is Apply-gated).
- `settings.html`: Language select + caption; Apply handler sends both
  values; probe `lang`.

## Limitations (documented in README, not built)

Spoken commands are English phrases (user-extensible via `replacements`);
Insights stopwords are English-centric (non-English top-words noisier).

## Error handling

Unknown/hand-edited language → "en" fallback + log (config sanitize).
Model download/load failure on switch → existing notify + CPU-fallback path.
`.en` model + non-English language → allowed but captioned (explicit user
choice); auto policy never produces that combination.

## Testing / release

Unit: resolve_model matrix (en/auto/es × cpu/gpu × auto/explicit-model);
config language sanitize; stub-transcribe receives language=None for auto,
code otherwise; bridge apply_model(name, language) validation + write.
Probe `lang=1`; version asserts 0.9.0. Live non-gating: transcribe a short
clip with language="auto" and log detected language. Release train: exe +
MSI (serialized, kill app+webviews), upgrade over 0.8.0, ProductsEx single
registration, data intact, adversarial review pre-push, push (fetch first —
user edits via GitHub web), tag v0.9.0, relaunch, MEMORY.md update.
