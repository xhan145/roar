# Speech Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove filler words and light disfluencies from dictated text so it reads like writing, deterministically and 100% locally.

**Architecture:** A new pure `cleanup.py` module runs rule-based transforms (interjection removal, allowlisted stutter/repeat collapse, false-start trim, opt-in comma-bounded discourse fillers) as the FIRST stage of `commands.process`. Two instant-apply config toggles gate it; two Transcription-tab toggles expose it.

**Tech Stack:** Python 3.14 (`venv/Scripts/python.exe`), `re`, pytest; pywebview settings UI; PyInstaller/WiX release train.

## Global Constraints

- Version bumps to `0.11.0` (`paths.APP_VERSION`).
- 100% local, deterministic, NO new dependencies, NO language model.
- `cleanup.clean` is pure and total — any string in, a string out, never raises.
- Settings process must NEVER import the ML stack (`cleanup.py` imports only `re`).
- `cleanup_enabled` defaults **on**; `remove_discourse_fillers` defaults **off**.
- Pipeline order: `strip -> cleanup -> replacements -> capitalize -> snippets`.
- Filler lists are English; repeat/false-start collapse is language-agnostic.
- MSI uses external CABs (an `.msi` file is capped at 2 GB); kill ROAR + webviews before any build or install; serialize builds; fetch before push.

---

### Task 1: `cleanup.py` pure engine (TDD)

**Files:**
- Create: `cleanup.py`
- Test: `tests/test_cleanup.py`

**Interfaces:**
- Produces: `clean(text: str, *, discourse: bool = False) -> str`;
  module constants `INTERJECTIONS` (frozenset), `COLLAPSE_WORDS` (frozenset),
  `DISCOURSE_FILLERS` (tuple).

- [ ] **Step 1: Write the failing tests** — `tests/test_cleanup.py`:

```python
import cleanup


def test_interjections_removed():
    assert cleanup.clean("Um, hello there") == "hello there"
    assert cleanup.clean("so uh I think we uh should go") == "so I think we should go"
    assert cleanup.clean("hmm let me think") == "let me think"


def test_interjection_word_boundary_safe():
    # 'um'/'er' inside real words must survive
    assert cleanup.clean("the umbrella is over there") == "the umbrella is over there"
    assert cleanup.clean("summer water") == "summer water"


def test_stutter_collapse_allowlist():
    assert cleanup.clean("the the cat") == "the cat"
    assert cleanup.clean("I I think") == "I think"
    assert cleanup.clean("we we should go to to the store") == "we should go to the store"


def test_stutter_preserves_grammatical_doubles():
    # not on the allowlist -> left intact
    assert cleanup.clean("I had had enough") == "I had had enough"
    assert cleanup.clean("that that is wrong") == "that that is wrong"
    assert cleanup.clean("it was very very good") == "it was very very good"


def test_false_start_trim():
    assert cleanup.clean("I- I think so") == "I think so"
    assert cleanup.clean("wh- what happened") == "what happened"
    assert cleanup.clean("go— go to the door") == "go to the door"


def test_false_start_preserves_real_hyphenates():
    assert cleanup.clean("a well-known fact") == "a well-known fact"


def test_discourse_off_by_default():
    # comma-bounded 'like' stays when discourse is off
    assert cleanup.clean("it's, like, cool") == "it's, like, cool"


def test_discourse_comma_bounded_only():
    assert cleanup.clean("it's, like, cool", discourse=True) == "it's cool"
    assert cleanup.clean("well, you know, maybe", discourse=True) == "well maybe"
    # bare 'like' as a real verb is NEVER touched
    assert cleanup.clean("I like it", discourse=True) == "I like it"
    assert cleanup.clean("I like it") == "I like it"


def test_empty_and_whitespace():
    assert cleanup.clean("") == ""
    assert cleanup.clean("   ") == ""
    assert cleanup.clean("um") == ""
    assert cleanup.clean(None) == ""


def test_whitespace_and_punctuation_normalized():
    assert cleanup.clean("hello  ,  world") == "hello, world"
    assert cleanup.clean("uh,  hello") == "hello"
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_cleanup.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cleanup'`.

- [ ] **Step 3: Implement `cleanup.py`**

```python
"""Deterministic speech cleanup: strip fillers and light disfluencies from a
transcript so it reads like writing. Pure, total, no dependencies, English
filler lists (repeat/false-start collapse is language-agnostic)."""
import re

INTERJECTIONS = frozenset({
    "um", "umm", "ummm", "uh", "uhh", "uhm", "er", "err", "erm",
    "hmm", "hmmm", "hm", "mm", "mmm",
})

# Immediate duplicates of these collapse (classic stutters). Grammatical
# doubles ("had had", "that that", "very very") are deliberately excluded.
COLLAPSE_WORDS = frozenset({
    "i", "a", "an", "the", "to", "and", "we", "you", "it", "is",
    "so", "but", "my", "of", "in", "on", "at", "for", "he", "she", "they",
})

# Removed only when comma-bounded (how Whisper punctuates true fillers).
DISCOURSE_FILLERS = (
    "you know", "i mean", "i guess", "sort of", "kind of",
    "basically", "actually", "literally", "you see", "like", "right",
)

_INTERJ_RE = re.compile(
    r"\b(?:" + "|".join(sorted(INTERJECTIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE)
_FALSE_START_RE = re.compile(r"\b\w{1,4}[‒-―\-]\s+", re.UNICODE)
_COLLAPSE_RE = re.compile(
    r"\b(" + "|".join(sorted(COLLAPSE_WORDS, key=len, reverse=True))
    + r")(\s+\1\b)+", re.IGNORECASE)


def _collapse_repeats(text):
    # \1 backref: same allowlisted word repeated (2+ times) -> keep one
    return _COLLAPSE_RE.sub(lambda m: m.group(1), text)


def _remove_discourse(text):
    for phrase in DISCOURSE_FILLERS:
        # comma-bounded on both sides -> collapse to a single space
        text = re.sub(r",\s*" + re.escape(phrase) + r"\s*,", " ", text,
                      flags=re.IGNORECASE)
        # sentence-initial "phrase, ..." or trailing "..., phrase"
        text = re.sub(r"^\s*" + re.escape(phrase) + r"\s*,\s*", "", text,
                      flags=re.IGNORECASE)
        text = re.sub(r",\s*" + re.escape(phrase) + r"\s*$", "", text,
                      flags=re.IGNORECASE)
    return text


def _normalize(text):
    text = re.sub(r"[ \t]*—[ \t]*", " ", text)  # leftover em-dashes -> space
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)      # no space before punct
    text = re.sub(r"^[\s,]+", "", text)                # no leading comma/space
    text = re.sub(r"[ \t]{2,}", " ", text)             # collapse runs of spaces
    return text.strip()


def clean(text, *, discourse=False):
    if not isinstance(text, str) or not text.strip():
        return ""
    text = _FALSE_START_RE.sub("", text)
    text = _INTERJ_RE.sub("", text)
    text = _collapse_repeats(text)
    if discourse:
        text = _remove_discourse(text)
    return _normalize(text)
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_cleanup.py -q`
Expected: PASS (all). If `test_whitespace_and_punctuation_normalized` or the
interjection tests reveal a stray double-space, the `_normalize` pass is what
fixes it — do not special-case individual inputs.

- [ ] **Step 5: Commit**

```bash
git add cleanup.py tests/test_cleanup.py
git commit -m "feat: deterministic speech-cleanup engine (pure)"
```

---

### Task 2: config keys + pipeline wiring (TDD)

**Files:**
- Modify: `config.py` (DEFAULTS + sanitize), `commands.py` (`process` signature + stage), `app.py` (pass config)
- Test: `tests/test_config.py`, `tests/test_commands.py`

**Interfaces:**
- Consumes: `cleanup.clean(text, *, discourse=bool)` from Task 1.
- Produces: `commands.process(text, replacements, snippets=None,
  snippet_keyword="snippet", cleanup=False, discourse_fillers=False) -> str`;
  config keys `cleanup_enabled: bool` (default True), `remove_discourse_fillers:
  bool` (default False).

- [ ] **Step 1: Write failing tests** — append to `tests/test_config.py`:

```python
def test_cleanup_defaults_present():
    cfg = config.load(str(_tmp := __import__("tempfile").mktemp(suffix=".json")))
    assert cfg["cleanup_enabled"] is True
    assert cfg["remove_discourse_fillers"] is False


def test_cleanup_flags_coerced_to_bool(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"cleanup_enabled": 0, "remove_discourse_fillers": 1}))
    cfg = config.load(str(p))
    assert cfg["cleanup_enabled"] is False
    assert cfg["remove_discourse_fillers"] is True
```

Append to `tests/test_commands.py`:

```python
def test_cleanup_runs_before_capitalize():
    # leading interjection gone, then first real word capitalized
    out = commands.process("um, hello there", {}, cleanup=True)
    assert out == "Hello there"


def test_cleanup_off_by_default_in_signature():
    assert commands.process("um hello", {}) == "Um hello"


def test_cleanup_then_replacement():
    out = commands.process("uh new line done", REPL, cleanup=True)
    assert out == "\nDone" or out == "\ndone"  # replacement fired after cleanup


def test_discourse_gated_by_flag():
    assert commands.process("it's, like, cool", {}, cleanup=True) == "It's, like, cool"
    assert commands.process("it's, like, cool", {}, cleanup=True,
                            discourse_fillers=True) == "It's cool"
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_commands.py -q`
Expected: FAIL — KeyError on the new config keys / wrong output (cleanup not applied).

- [ ] **Step 3a: `config.py` DEFAULTS** — add after `"streaming_preview": True,`:

```python
    "cleanup_enabled": True,
    "remove_discourse_fillers": False,
```

- [ ] **Step 3b: `config.py` sanitize** — in the `load()` for-loop, add a branch
  before the final `else`:

```python
        elif key in ("cleanup_enabled", "remove_discourse_fillers"):
            cfg[key] = bool(value)
```

- [ ] **Step 3c: `commands.py`** — replace the `process` definition:

```python
import cleanup as cleanup_mod


def process(text: str, replacements: dict, snippets=None,
            snippet_keyword: str = "snippet", cleanup: bool = False,
            discourse_fillers: bool = False) -> str:
    """Full pipeline: strip -> cleanup -> replacements -> capitalize -> snippets.
    Cleanup runs first so capitalization lands on the real first word and
    commands/snippets see already-cleaned text. Returns '' when there is
    nothing worth injecting."""
    text = text.strip()
    if not text:
        return ""
    if cleanup:
        text = cleanup_mod.clean(text, discourse=discourse_fillers)
        if not text:
            return ""
    text = apply_replacements(text, replacements)
    for i, ch in enumerate(text):
        if ch.isalpha():
            if ch.islower():
                text = text[:i] + ch.upper() + text[i + 1:]
            break
    if snippets:
        text = snippets_mod.expand(text, snippets, keyword=snippet_keyword)
    if not text.strip():
        return text if "\n" in text else ""
    return text
```

Put `import cleanup as cleanup_mod` at the top with `import snippets as snippets_mod`.

- [ ] **Step 3d: `app.py`** — update the `commands.process` call in `_handle_transcription`:

```python
        text = commands.process(
            raw, self.cfg["replacements"],
            self.cfg.get("snippets"),
            self.cfg.get("snippet_keyword", "snippet"),
            cleanup=self.cfg.get("cleanup_enabled", True),
            discourse_fillers=self.cfg.get("remove_discourse_fillers", False))
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_commands.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py commands.py app.py tests/test_config.py tests/test_commands.py
git commit -m "feat: wire cleanup into config + dictation pipeline"
```

---

### Task 3: settings toggles + version bump (TDD)

**Files:**
- Modify: `settings_ui.py` (INSTANT_KEYS + smoke probe), `settings.html` (two toggles + init + handlers), `paths.py` (0.11.0)
- Test: `tests/test_settings_bridge.py`, `tests/test_paths.py`, `tests/test_settings_smoke.py`

**Interfaces:**
- Consumes: config keys from Task 2.
- Produces: `set_value` accepts `"cleanup_enabled"` / `"remove_discourse_fillers"`;
  `paths.APP_VERSION == "0.11.0"`; DOM ids `t-cleanup`, `t-discourse`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_settings_bridge.py`:

```python
def test_cleanup_instant_keys(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("cleanup_enabled", False)["ok"] is True
    assert config.load(p)["cleanup_enabled"] is False
    assert api.set_value("remove_discourse_fillers", True)["ok"] is True
    assert config.load(p)["remove_discourse_fillers"] is True
```

Update the version assert in `tests/test_settings_bridge.py::test_get_state_shape`
from `"0.10.0"` to `"0.11.0"`, and `tests/test_paths.py` from `"0.10.0"` to `"0.11.0"`.

Update `tests/test_settings_smoke.py` to add after the existing `snip` asserts:

```python
    assert "cleanup=1" in out and "discourse=1" in out
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_settings_bridge.py tests/test_paths.py -q`
Expected: FAIL — `set_value` rejects the new keys / version mismatch.

- [ ] **Step 3a: `settings_ui.py` INSTANT_KEYS** — add the two keys:

```python
INSTANT_KEYS = {"tones_enabled", "paste_fallback", "silence_rms_threshold",
                "input_device", "history_enabled", "audio_retention_days",
                "auto_vocabulary", "overlay_enabled", "streaming_preview",
                "cleanup_enabled", "remove_discourse_fillers"}
```

And in `set_value`, extend the bool-coercion list:

```python
        if key in ("history_enabled", "auto_vocabulary",
                   "overlay_enabled", "streaming_preview",
                   "cleanup_enabled", "remove_discourse_fillers"):
            value = bool(value)
```

- [ ] **Step 3b: `paths.py`** — `APP_VERSION = "0.11.0"`.

- [ ] **Step 3c: `settings.html`** — inside `<section id="transcription">`, after
  the vocabulary `</div>` block (before `</section>`), add:

```html
      <div class="row" style="margin-top:14px;">
        <div class="row flex" style="background:#0a0a0c;">
          <div>Clean up speech<div class="hint">Removes "um", "uh", stutters, and repeated words</div></div>
          <button class="toggle" id="t-cleanup" aria-pressed="true" aria-label="Clean up speech"></button>
        </div>
        <div class="row flex" style="background:#0a0a0c;margin-top:8px;">
          <div>Remove filler phrases<div class="hint">Also strips "like", "you know", "I mean" when used as fillers — may occasionally remove a real word</div></div>
          <button class="toggle" id="t-discourse" aria-pressed="false" aria-label="Remove filler phrases"></button>
        </div>
      </div>
```

In `init()` (near `setToggle($("t-streamprev"), ...)`), add:

```javascript
  setToggle($("t-cleanup"), c.cleanup_enabled);
  setToggle($("t-discourse"), c.remove_discourse_fillers);
```

Near the `t-overlay`/`t-streamprev` handlers, add:

```javascript
$("t-cleanup").addEventListener("click", async () => {
  const want = !isOn($("t-cleanup"));
  const r = await api().set_value("cleanup_enabled", want);
  if (r.ok) setToggle($("t-cleanup"), want); else msg("m-vocab", r.error, "err");
});
$("t-discourse").addEventListener("click", async () => {
  const want = !isOn($("t-discourse"));
  const r = await api().set_value("remove_discourse_fillers", want);
  if (r.ok) setToggle($("t-discourse"), want); else msg("m-vocab", r.error, "err");
});
```

- [ ] **Step 3d: `settings_ui.py` smoke probe** — in `probe_and_close`, add two
  probes and extend the print line:

```python
                    has_cleanup = window.evaluate_js(
                        "document.getElementById('t-cleanup') ? 1 : 0")
                    has_discourse = window.evaluate_js(
                        "document.getElementById('t-discourse') ? 1 : 0")
```

Extend the existing `print(...)` probe line to include:
`f"cleanup={has_cleanup} discourse={has_discourse}"`.

- [ ] **Step 4: Run suite twice**

Run: `venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_transcriber_gpu.py`
(kill ROAR.exe + webviews first so the smoke mutex tests pass)
Expected: PASS. Run again to confirm stability.

- [ ] **Step 5: Commit**

```bash
git add settings_ui.py settings.html paths.py tests/test_settings_bridge.py tests/test_paths.py tests/test_settings_smoke.py
git commit -m "feat: Speech Cleanup toggles in Transcription tab; bump v0.11.0"
```

---

### Task 4: docs + release train v0.11.0

- [ ] **Step 1:** README — add a "Speech cleanup" section under Multilingual:
  what it removes (interjections, stutters, repeats, false starts), the opt-in
  discourse-filler toggle and its false-positive caveat, the English-list /
  language-agnostic-collapse note. Commit `docs: speech cleanup`.
- [ ] **Step 2:** Kill ROAR.exe + webviews. Rebuild exe
  (`venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm`). Frozen probe
  via `dist/ROAR/ROAR.exe --settings --smoke`: assert
  `version=0.11.0 … cleanup=1 discourse=1`.
- [ ] **Step 3:** Build MSI SOLO (`bash scripts/build_msi.sh`) — external CABs,
  `dist/ROAR-0.11.0.msi` + `roar*.cab`.
- [ ] **Step 4:** Adversarial review (Workflow): cleanup regex edge cases
  (backref collapse across 3+ repeats, false-start eating hyphenates,
  interjection word-boundary, discourse comma-bounding false positives, order
  interactions with replacements/capitalize), config/bridge, English-only
  scope. Verify confirmed findings inline; fix; suite ×2; `git status` clean
  before `git add`.
- [ ] **Step 5:** Kill installed ROAR + webviews. Upgrade-install over 0.10.0:
  exit 0, ProductsEx one ROAR v0.11.0, installed probe green, config + history
  intact (hotkey `ctrl+shift`, dictation rows).
- [ ] **Step 6:** `git fetch` first (merge if diverged); push; release commit
  `roar v0.11.0 — speech cleanup`; tag `v0.11.0`; push --tags; relaunch
  installed ROAR; update MEMORY.md + `flowlocal-project.md`; final report.
