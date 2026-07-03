# Multilingual Dictation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Language picker (auto-detect + 100 languages) with a model auto-policy that forks to multilingual variants; v0.9.0 closes the upgrade queue.

**Architecture:** `resolve_model(name, device, language)` fork (`distil-large-v3`/`small.en` for en; `large-v3-turbo`/`small` otherwise); `"auto"` → `language=None` at transcribe time; config sanitization; Apply-gated dropdown sharing the model Apply; `diff_config` folds language into the reload action.

**Tech Stack:** existing faster-whisper 1.2.1 (aliases verified), no new deps.

## Global Constraints

- Spec `docs/superpowers/specs/2026-07-04-multilingual-design.md` normative. `config.language` default stays `"en"`; unknown values sanitize to `"en"`. Explicit model names honored as-is.
- `apply_model(name, language=None)` — language omitted ⇒ untouched (back-compat with existing tests/UI paths).
- v0.9.0; probe adds `lang=1`. Kill ROAR.exe + webviews before tests/builds/installs; builds serialized; fetch before push; `git status` before adds.

---

### Task 1: transcriber language fork (TDD)

**Files:** Modify `transcriber.py`; tests append `tests/test_transcriber.py`

**Interfaces:** `GPU_MODEL_EN/GPU_MODEL_MULTI/CPU_MODEL_EN/CPU_MODEL_MULTI` consts; `resolve_model(name, device, language="en")`; `Transcriber._run` passes `language=None` when `self.language == "auto"`; `load()` resolves with `self.language`.

- [ ] **Step 1: failing tests** (append):

```python
def test_resolve_model_language_fork():
    assert resolve_model("auto", "cuda", "en") == "distil-large-v3"
    assert resolve_model("auto", "cpu", "en") == "small.en"
    assert resolve_model("auto", "cuda", "es") == "large-v3-turbo"
    assert resolve_model("auto", "cuda", "auto") == "large-v3-turbo"
    assert resolve_model("auto", "cpu", "auto") == "small"
    assert resolve_model("tiny.en", "cuda", "es") == "tiny.en"  # explicit wins


def test_auto_language_reaches_transcribe_as_none():
    t = Transcriber(model_name="small.en", force_device="cpu", language="auto")

    class StubModel:
        def transcribe(self, audio, **kwargs):
            self.kwargs = kwargs
            return iter(()), None

    t._model = StubModel()
    t.active_model, t.device = "stub", "cpu"
    t.transcribe("x.wav")
    assert t._model.kwargs["language"] is None
    t.language = "es"
    t.transcribe("x.wav")
    assert t._model.kwargs["language"] == "es"
```

- [ ] **Step 2:** run → FAIL. **Step 3:** implement:

```python
GPU_MODEL_EN = "distil-large-v3"     # English-only distillation
GPU_MODEL_MULTI = "large-v3-turbo"   # multilingual, fast
CPU_MODEL_EN = "small.en"
CPU_MODEL_MULTI = "small"


def resolve_model(name: str, device: str, language: str = "en") -> str:
    if name != "auto":
        return name
    english = language == "en"
    if device == "cuda":
        return GPU_MODEL_EN if english else GPU_MODEL_MULTI
    return CPU_MODEL_EN if english else CPU_MODEL_MULTI
```

`load()` attempts use `resolve_model(name, dev, self.language)`. `_run`: `lang = None if self.language == "auto" else self.language` passed as `language=lang`. (Old two-arg `resolve_model` calls in tests keep working via the default.)

- [ ] **Step 4:** transcriber tests pass. **Step 5:** commit `feat: language-aware model policy + auto-detect`.

---

### Task 2: config sanitize + diff/reload wiring (TDD)

**Files:** Modify `config.py`, `app.py`; tests append `tests/test_config.py`, `tests/test_diff_config.py`

**Interfaces:** `config.valid_language(v) -> bool` (public; `"auto"` or fw code; hardcoded 16-code fallback if fw import fails); load sanitizes `language`; `diff_config` emits ONE `("reload_model", new["model"])` when model OR language changed; app reload branch sets `self.transcriber.language = self.cfg["language"]` before `load()`.

- [ ] **Step 1: failing tests.** test_config append:

```python
def test_language_sanitized_on_load(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"language": "klingon"}))
    assert config.load(str(p))["language"] == "en"
    p.write_text(json.dumps({"language": "auto"}))
    assert config.load(str(p))["language"] == "auto"
    p.write_text(json.dumps({"language": "es"}))
    assert config.load(str(p))["language"] == "es"
```

test_diff_config append:

```python
def test_language_change_reloads_model_once():
    old, new = _pair(language="es", model="auto")
    assert diff_config(old, new) == [("reload_model", "auto")]


def test_language_and_model_change_single_reload():
    old, new = _pair(language="auto", model="small")
    assert diff_config(old, new).count(("reload_model", "small")) == 1
```

- [ ] **Step 2:** FAIL. **Step 3:** `config.py`:

```python
_COMMON_LANGS = {"en", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "uk",
                 "zh", "ja", "ko", "ar", "hi", "tr"}


def valid_language(v) -> bool:
    if v == "auto":
        return True
    if not isinstance(v, str):
        return False
    try:
        from faster_whisper.tokenizer import _LANGUAGE_CODES
        return v in _LANGUAGE_CODES
    except Exception:
        return v in _COMMON_LANGS
```

load(): `elif key == "language": cfg[key] = value if valid_language(value) else "en"`. `app.py` diff_config: merge language into the model condition (`if old["model"] != new["model"] or old["language"] != new["language"]: actions.append(("reload_model", new["model"]))`); reload worker branch adds `self.transcriber.language = self.cfg["language"]` before `self.transcriber.load()`.

- [ ] **Step 4:** both files + full suite green. **Step 5:** commit `feat: language sanitization + hot-reload on language change`.

---

### Task 3: bridge + UI + probe + version (TDD)

**Files:** Modify `settings_ui.py`, `settings.html`, `paths.py`, version asserts, `tests/test_settings_bridge.py`, `tests/test_settings_smoke.py`

**Interfaces:** `MODEL_CHOICES` += `"small"`, `"large-v3-turbo"`; `LANGUAGE_LABELS` (17 entries incl. auto); `_language_options() -> [[code,label]]` (common first, then rest alphabetical); `get_state()["languages"]`; `apply_model(name, language=None)` — validates + writes language only when given.

- [ ] **Step 1: failing tests** (append test_settings_bridge):

```python
def test_apply_model_with_language(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.apply_model("auto", "es")["ok"] is True
    cfg = config.load(p)
    assert cfg["model"] == "auto" and cfg["language"] == "es"
    assert "error" in api.apply_model("auto", "klingon")
    assert api.apply_model("small.en")["ok"] is True   # language untouched
    assert config.load(p)["language"] == "es"


def test_get_state_languages(tmp_path):
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    langs = api.get_state()["languages"]
    assert langs[0] == ["auto", "Auto-detect"]
    assert ["es", "Español"] in langs
    assert len(langs) > 50
```

- [ ] **Step 2:** FAIL. **Step 3:** implement bridge:

```python
MODEL_CHOICES = ["auto", "tiny.en", "base.en", "small.en", "medium.en",
                 "distil-large-v3", "small", "large-v3-turbo"]
LANGUAGE_LABELS = {
    "auto": "Auto-detect", "en": "English", "es": "Español", "fr": "Français",
    "de": "Deutsch", "it": "Italiano", "pt": "Português", "nl": "Nederlands",
    "pl": "Polski", "ru": "Русский", "uk": "Українська", "zh": "中文",
    "ja": "日本語", "ko": "한국어", "ar": "العربية", "hi": "हिन्दी",
    "tr": "Türkçe",
}
_COMMON_ORDER = ["auto", "en", "es", "fr", "de", "it", "pt", "nl", "pl",
                 "ru", "uk", "zh", "ja", "ko", "ar", "hi", "tr"]


def _language_options():
    try:
        from faster_whisper.tokenizer import _LANGUAGE_CODES
        codes = sorted(_LANGUAGE_CODES)
    except Exception:
        codes = sorted(set(LANGUAGE_LABELS) - {"auto"})
    rest = [c for c in codes if c not in _COMMON_ORDER]
    return ([[c, LANGUAGE_LABELS.get(c, c)] for c in _COMMON_ORDER]
            + [[c, c] for c in rest])
```

`get_state` adds `"languages": _language_options()`. `apply_model`:

```python
    def apply_model(self, name, language=None):
        if name not in MODEL_CHOICES:
            return {"error": f"unknown model {name}"}
        if language is None:
            self._write(model=name)
            return {"ok": True}
        if not config_mod.valid_language(language):
            return {"error": f"unknown language {language}"}
        self._write(model=name, language=language)
        return {"ok": True}
```

`settings.html`: above `#model-list` add

```html
      <div class="row">
        <div style="margin-bottom:8px;">Language</div>
        <select id="s-language" aria-label="Dictation language"></select>
        <div class="hint" style="margin-top:6px;">Auto-detect identifies the language each time you dictate. Switching away from English may download a multilingual model (~1.6 GB) on Apply. ".en" models are English-only.</div>
      </div>
```

init(): populate from `state.languages`, select `c.language`; language `change` → `pending.langsel = value; $("b-apply-model").disabled = false;` Apply handler sends `api().apply_model(pending.model || state.config.model, pending.langsel || null)` and clears both. MODEL_CAPS += `"small": "Multilingual, good accuracy on CPU"`, `"large-v3-turbo": "Multilingual, fast on GPU — best for non-English"`. Probe adds `lang = evaluate_js("document.getElementById('s-language') ? 1 : 0")`; smoke asserts `lang=1`. `paths.APP_VERSION = "0.9.0"`; version asserts → 0.9.0.

- [ ] **Step 4:** full suite ×2 green. **Step 5:** commit `feat: language picker UI + bridge; bump v0.9.0`.

---

### Task 4: release train v0.9.0

- [ ] **Step 1:** README: multilingual section (auto-detect, model policy fork, English-only limitations of commands/insights). Live non-gating check: script transcribes an English WAV with language="auto" via Transcriber, log detected language path works.
- [ ] **Step 2:** Kill app+webviews; exe rebuild; frozen probe `version=0.9.0 … lang=1`; MSI (solo).
- [ ] **Step 3:** Kill app+webviews (pythonnet 1304 gotcha); install over 0.8.0; ProductsEx = one ROAR v0.9.0; installed probe; data intact.
- [ ] **Step 4:** Adversarial review (policy-fork matrix vs actual fw behavior, `.en`+non-en combos, sanitize edges, UI apply coupling, turbo download UX); fix confirmed; suite ×2.
- [ ] **Step 5:** `git fetch` + reconcile (user edits via GitHub web); push; release commit `roar v0.9.0 — multilingual dictation`; tag v0.9.0; push --tags; relaunch installed ROAR; MEMORY.md + memory update (queue COMPLETE); final report.
