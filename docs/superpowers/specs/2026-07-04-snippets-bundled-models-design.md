# ROAR Snippets + Bundled Language Models — Design Spec

**Date:** 2026-07-04
**Status:** Approved (user directive: "add that and the languages in by default with the installer")
**Ships as:** v0.10.0

## Part 1 — ROAR Snippets (SP7)

- **Model:** config key `"snippets": {}` — name → expansion (multi-line).
  Sanitized on load (str→str only, mirroring replacements). Validation at the
  bridge: name 1–30 chars matching `[A-Za-z0-9-]+` (case-insensitive unique),
  expansion 1–2000 chars, ≤100 snippets.
- **Firing from dictation** (in `commands.process`, after replacements,
  single pass, no recursion):
  1. keyword form: the token sequence `snippet <name>` (case-insensitive,
     keyword configurable via `"snippet_keyword": "snippet"`) is replaced by
     the expansion;
  2. literal form: the standalone token `/<name>` is replaced too.
  Unknown names are left as-is. Word-boundary safe.
- **Variables** substituted at expansion time: `{date}` → locale short date,
  `{time}` → HH:MM, `{clipboard}` → clipboard text via pyperclip (empty on
  failure). Unknown `{vars}` left literal.
- **UI:** new **Snippets** sidebar section (nav count 8 → 9; smoke asserts
  navs=9, `snip=1`, and CLICKS the tab). Card list (name chip + first-line
  preview + Delete), add/edit form (name input + textarea + Save), inline
  validation errors, **Export pack** / **Import pack** buttons using
  pywebview `create_file_dialog` (SAVE/OPEN). Pack = JSON object of
  name→expansion; import merges, colliding names get `-2` suffix.
- **Bridge:** `snippets_get() -> {snippets, keyword}`,
  `snippet_save(name, text) -> {ok}|{error}`, `snippet_delete(name) -> {ok}`,
  `snippets_export() -> {ok, path}|{error}|{cancelled}`,
  `snippets_import() -> {ok, added, renamed}|{error}|{cancelled}`.
  All config writes under `_cfg_lock`.
- **Pipeline placement:** expansion is part of the final processed text →
  history stores the expanded result; hotwords unaffected. `diff_config`: no
  action (read at use).
- Out of scope: voice-created snippets ("save snippet ..."), typed-trigger
  expansion outside dictation (system-wide expander), per-app packs.

## Part 2 — Multilingual models bundled in the installer

- **Seed fetch:** `scripts/fetch_models.py` — uses
  `faster_whisper.download_model(name, output_dir)` to place
  `large-v3-turbo` and `small` under `models-seed/<name>/` (gitignored).
- **Bundle:** `roar.spec` adds `datas += [("models-seed", "models-seed")]`
  when the dir exists (frozen path: `_internal/models-seed/<name>`).
- **Load order** (transcriber, per attempt): (1) model name with
  `download_root=models_dir()` and `local_files_only=True` (user cache,
  offline); (2) bundled seed dir via direct path when
  `paths.resource_path("models-seed/<name>")` exists; (3) model name with
  network download (current behavior). CUDA→CPU fallback preserved around
  the whole order.
- **Installer:** `installer/roar.wxs` MediaTemplate gains
  `MaximumUncompressedMediaSize="1024"` (multi-CAB; single CAB caps at 2 GB)
  and `CompressionLevel="mszip"` (model weights are incompressible; `high`
  wastes build time/memory — commit-memory exhaustion precedent). Expected
  MSI ≈ 2.5 GB.
- English models (distil-large-v3 / small.en) intentionally NOT bundled —
  the directive covers "the languages"; English stays download-on-first-run
  for fresh machines (this machine already has them).

## Error handling

Snippets: invalid names/expansions rejected inline; import of malformed JSON
→ `{error}`; clipboard variable failure → empty string. Seed: missing seed
dir → behavior identical to today; corrupt seed load falls through to
download; `local_files_only` failure falls through silently to next source.

## Testing / release

Units: expansion (keyword + literal, boundaries, no-recursion, unknown name
untouched, variables incl. clipboard monkeypatch), config sanitize, bridge
CRUD/validation/pack round-trip (tmp config + monkeypatched file dialog),
seed resolution order (monkeypatched paths + stub loader). Probe navs=9 +
`snip=1` clicked. Suite ×2. Release train: fetch models → exe (bigger) →
MSI (multi-CAB, longer) → upgrade over v0.9.0 → OFFLINE language check
(load `small` via seed with `local_files_only` forced off-network) →
adversarial review → fetch-first push → tag v0.10.0 → relaunch → MEMORY.md.
