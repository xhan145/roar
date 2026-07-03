# FlowLocal Custom Vocabulary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Custom dictionary + auto signature words merged into faster-whisper `hotwords` on every transcription, edited from the Transcription tab; v0.5.0.

**Architecture:** Pure `vocabulary.py` (merge + validation); `Transcriber.hotwords` attribute passed to `model.transcribe`; tray app rebuilds hotwords at model load / every 25 dictations / on config change (new `rebuild_hotwords` diff action); bridge + chip-editor UI in the Transcription tab.

**Tech Stack:** stdlib only. Existing pywebview UI, PyInstaller, WiX.

## Global Constraints

- Project `C:\Users\xhan1\flowlocal`, branch `main`, venv `venv/Scripts/python.exe`, pytest from project root, kill FlowLocal.exe (and FlowLocal msedgewebview2 children) before test runs/installs.
- Spec: `docs/superpowers/specs/2026-07-03-custom-vocabulary-design.md`. Validation: entries 2–40 chars trimmed, ≤50 custom, case-insensitive dedupe, no control chars. Merge cap 60, custom first, None when empty.
- `paths.APP_VERSION = "0.5.0"`. Smoke probe adds `vocab=1`. `git status` before adds. Release: exe + MSI (hardened build), over-install + `ProductsEx("","",2)` single-registration check, adversarial review pre-push, tag v0.5.0, relaunch INSTALLED copy.

---

### Task 1: vocabulary.py (pure)

**Files:** Create `vocabulary.py`, `tests/test_vocabulary.py`

**Interfaces:** `merge_hotwords(custom: list, signature: list, cap: int = 60) -> str | None`; `validate_entry(word: str, existing: list) -> str | None` (error text or None). `MAX_CUSTOM = 50`.

- [ ] **Step 1: failing tests** `tests/test_vocabulary.py`:

```python
from vocabulary import MAX_CUSTOM, merge_hotwords, validate_entry


def test_merge_dedupes_case_insensitively_custom_first():
    s = merge_hotwords(["ScratchEdge", "Kubernetes"], ["kubernetes", "flowlocal"])
    assert s == "ScratchEdge Kubernetes flowlocal"


def test_merge_trims_and_drops_empties():
    assert merge_hotwords(["  padded  ", "", "  "], []) == "padded"


def test_merge_empty_returns_none():
    assert merge_hotwords([], []) is None
    assert merge_hotwords(["  "], [""]) is None


def test_merge_cap():
    custom = [f"word{i:02d}" for i in range(50)]
    sig = [f"sig{i}" for i in range(20)]
    merged = merge_hotwords(custom, sig, cap=60).split()
    assert len(merged) == 60
    assert merged[0] == "word00" and merged[49] == "word49"  # custom first
    assert merged[50] == "sig0"


def test_validate_entry_rules():
    assert validate_entry("ok", []) is None
    assert validate_entry("x", []) is not None            # too short
    assert validate_entry("y" * 41, []) is not None       # too long
    assert validate_entry("dupe", ["DUPE"]) is not None   # case-insensitive dup
    assert validate_entry("ctl\x07chr", []) is not None   # control char
    assert validate_entry("word", [f"w{i}" for i in range(MAX_CUSTOM)]) is not None
    assert validate_entry("  spaced  ", []) is None       # trimmed before checks
```

- [ ] **Step 2:** Run `venv/Scripts/python.exe -m pytest tests/test_vocabulary.py -q` → ModuleNotFoundError.
- [ ] **Step 3:** `vocabulary.py`:

```python
"""Custom-vocabulary merging and validation. Pure functions."""

MAX_CUSTOM = 50


def merge_hotwords(custom, signature, cap=60):
    """Merged hotwords string for faster-whisper, or None when empty.
    Custom words first, case-insensitive dedupe, capped."""
    out, seen = [], set()
    for word in list(custom) + list(signature):
        w = str(word).strip()
        key = w.lower()
        if w and key not in seen:
            seen.add(key)
            out.append(w)
        if len(out) >= cap:
            break
    return " ".join(out) if out else None


def validate_entry(word, existing):
    """None when the entry is acceptable, else a human-readable reason."""
    w = (word or "").strip()
    if len(w) < 2:
        return "words need at least 2 characters"
    if len(w) > 40:
        return "words are limited to 40 characters"
    if any(ord(ch) < 32 for ch in w):
        return "that contains unprintable characters"
    if len(existing) >= MAX_CUSTOM:
        return f"the custom list is limited to {MAX_CUSTOM} words"
    if w.lower() in {str(e).strip().lower() for e in existing}:
        return "that word is already in the list"
    return None
```

- [ ] **Step 4:** Run → 6 passed.
- [ ] **Step 5:** `git add vocabulary.py tests/test_vocabulary.py && git commit -m "feat: vocabulary merge + validation (pure)"`

---

### Task 2: transcriber hotwords + config keys + diff action

**Files:** Modify `transcriber.py`, `config.py`, `app.py` (diff_config only); tests in `tests/test_transcriber.py`, `tests/test_history_capture.py` (config keys), `tests/test_diff_config.py`

**Interfaces:** `Transcriber.hotwords` (attr, default None) → passed as `hotwords=` in `_run`. DEFAULTS += `custom_vocabulary: []`, `auto_vocabulary: True`. `diff_config` emits `("rebuild_hotwords", None)` once when either key changes.

- [ ] **Step 1: failing tests.** Append to `tests/test_transcriber.py`:

```python
def test_hotwords_reach_model_transcribe():
    t = Transcriber(model_name="small.en", force_device="cpu")

    class StubModel:
        def __init__(self):
            self.kwargs = None

        def transcribe(self, audio, **kwargs):
            self.kwargs = kwargs
            return iter(()), None

    t._model = StubModel()
    t.active_model, t.device = "stub", "cpu"
    t.transcribe("ignored.wav")
    assert t._model.kwargs["hotwords"] is None  # default
    t.hotwords = "ScratchEdge FlowLocal"
    t.transcribe("ignored.wav")
    assert t._model.kwargs["hotwords"] == "ScratchEdge FlowLocal"
```

Append to `tests/test_diff_config.py`:

```python
def test_vocabulary_changes_rebuild_hotwords_once():
    old, new = _pair(custom_vocabulary=["ScratchEdge"], auto_vocabulary=False)
    assert diff_config(old, new) == [("rebuild_hotwords", None)]


def test_defaults_have_vocabulary_keys():
    from config import DEFAULTS
    assert DEFAULTS["custom_vocabulary"] == []
    assert DEFAULTS["auto_vocabulary"] is True
```

- [ ] **Step 2:** Run both files → FAIL.
- [ ] **Step 3:** `config.py` DEFAULTS += the two keys. `transcriber.py`: `self.hotwords = None` in `__init__`; `_run` passes `hotwords=self.hotwords`. `app.py` `diff_config` appends:

```python
    if (old["custom_vocabulary"] != new["custom_vocabulary"]
            or old["auto_vocabulary"] != new["auto_vocabulary"]):
        actions.append(("rebuild_hotwords", None))
```

- [ ] **Step 4:** Both files pass.
- [ ] **Step 5:** `git add transcriber.py config.py app.py tests/ && git commit -m "feat: hotwords plumbing, vocab config keys, diff action"`

---

### Task 3: app wiring — _rebuild_hotwords

**Files:** Modify `app.py`; test in `tests/test_capture_integration.py`

**Interfaces:** `FlowLocalApp._rebuild_hotwords()` — signature words from `insights.compute_insights(self.history.list(limit=5000))["signature_words"]` when `cfg["auto_vocabulary"]` and `cfg["history_enabled"]`, else `[]`; sets `self.transcriber.hotwords = vocabulary.merge_hotwords(cfg["custom_vocabulary"], sig)`. Failure: log, keep previous. Called after model load (worker), every 25th dictation (`self._dictation_count`), and by the watcher on `rebuild_hotwords`.

- [ ] **Step 1: failing test** (append to `tests/test_capture_integration.py`):

```python
def test_rebuild_hotwords_merges_custom_and_signature(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: None)
    a = _make_app(tmp_path)
    a.cfg["custom_vocabulary"] = ["ScratchEdge"]
    a.cfg["auto_vocabulary"] = True
    for i in range(3):
        a.history.record("kubernetes deployment pipeline kubernetes", ts=float(i))
    a._rebuild_hotwords()
    hw = a.transcriber.hotwords
    assert hw.startswith("ScratchEdge")
    assert "kubernetes" in hw
    a.cfg["auto_vocabulary"] = False
    a._rebuild_hotwords()
    assert a.transcriber.hotwords == "ScratchEdge"
    a.history.close()
```

- [ ] **Step 2:** Run → AttributeError.
- [ ] **Step 3:** In `app.py` (import `vocabulary`, `from insights import compute_insights` lazily inside the method):

```python
    def _rebuild_hotwords(self):
        """Merge custom + auto signature words into the transcriber. Never
        raises; on failure the previous hotwords stay in effect."""
        import vocabulary
        try:
            signature = []
            if self.cfg.get("auto_vocabulary", True) and self.cfg.get("history_enabled", True):
                from insights import compute_insights
                signature = compute_insights(
                    self.history.list(limit=5000))["signature_words"]
            self.transcriber.hotwords = vocabulary.merge_hotwords(
                self.cfg.get("custom_vocabulary", []), signature)
        except Exception as e:
            self.log(f"hotwords rebuild failed: {e}")
```

`__init__`: `self._dictation_count = 0`. Worker: call `self._rebuild_hotwords()` right after the model-loaded log line. `_handle_transcription` (after record_history): `self._dictation_count += 1; if self._dictation_count % 25 == 0: self._rebuild_hotwords()`. Watcher action branch: `elif action == "rebuild_hotwords": self._rebuild_hotwords()`.

- [ ] **Step 4:** Test passes; full suite green.
- [ ] **Step 5:** `git add app.py tests/test_capture_integration.py && git commit -m "feat: hotwords rebuilt from custom+signature vocabulary"`

---

### Task 4: bridge + UI + probe

**Files:** Modify `settings_ui.py`, `settings.html`, `tests/test_settings_bridge.py`, `tests/test_settings_smoke.py`

**Interfaces:** Bridge: `vocab_get() -> {custom, auto_enabled, auto_words}`, `vocab_add(word) -> {ok, custom}|{error}`, `vocab_remove(word) -> {ok, custom}`; `INSTANT_KEYS` += `auto_vocabulary`. Probe adds `vocab=`.

- [ ] **Step 1: failing tests** (append to `tests/test_settings_bridge.py`):

```python
def test_vocab_round_trip(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert api.vocab_get()["custom"] == [] and api.vocab_get()["auto_enabled"] is True
    assert api.vocab_add("ScratchEdge")["ok"] is True
    assert "error" in api.vocab_add("scratchedge")       # dup
    assert "error" in api.vocab_add("x")                 # too short
    assert api.vocab_get()["custom"] == ["ScratchEdge"]
    assert api.set_value("auto_vocabulary", False)["ok"] is True
    assert api.vocab_get()["auto_enabled"] is False
    assert api.vocab_remove("SCRATCHEDGE")["ok"] is True
    assert api.vocab_get()["custom"] == []
```

- [ ] **Step 2:** Run → AttributeError.
- [ ] **Step 3:** `settings_ui.py`: add `"auto_vocabulary"` to INSTANT_KEYS with bool coercion beside `history_enabled` (`if key in ("history_enabled", "auto_vocabulary"): value = bool(value)`); add methods:

```python
    def vocab_get(self):
        import vocabulary  # noqa: F401  (import validates availability)
        cfg = config_mod.load(self.config_path)
        auto_words = []
        if cfg.get("auto_vocabulary", True):
            try:
                from insights import compute_insights
                auto_words = compute_insights(
                    self._history.list(limit=5000))["signature_words"]
            except Exception:
                pass
        return {"custom": cfg.get("custom_vocabulary", []),
                "auto_enabled": bool(cfg.get("auto_vocabulary", True)),
                "auto_words": auto_words}

    def vocab_add(self, word):
        from vocabulary import validate_entry
        cfg = config_mod.load(self.config_path)
        custom = [str(w) for w in cfg.get("custom_vocabulary", [])]
        err = validate_entry(word, custom)
        if err:
            return {"error": err}
        custom.append(str(word).strip())
        self._write(custom_vocabulary=custom)
        return {"ok": True, "custom": custom}

    def vocab_remove(self, word):
        cfg = config_mod.load(self.config_path)
        target = str(word).strip().lower()
        custom = [w for w in cfg.get("custom_vocabulary", [])
                  if str(w).strip().lower() != target]
        self._write(custom_vocabulary=custom)
        return {"ok": True, "custom": custom}
```

`settings.html` — Vocabulary card appended inside `#transcription` after the Apply button/msg:

```html
      <div class="row" style="margin-top:14px;">
        <div>Vocabulary</div>
        <div class="hint" style="margin-bottom:8px;">Words FlowLocal should recognize more reliably — names, jargon, brands</div>
        <div id="vocab-chips" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;"></div>
        <div style="display:flex;gap:8px;">
          <input id="vocab-input" type="text" maxlength="40" placeholder="Add a word and press Enter"
                 style="flex:1;background:#0E1320;border:1px solid var(--border);border-radius:8px;padding:8px 12px;" aria-label="Add vocabulary word">
          <button class="btn" id="b-vocab-add">Add</button>
        </div>
        <div class="msg" id="m-vocab"></div>
        <div class="row flex" style="margin-top:10px;background:#0E1320;">
          <div>Include my signature words automatically<div class="hint">Pulled from your dictation history (see Insights)</div></div>
          <button class="toggle" id="t-autovocab" aria-pressed="true" aria-label="Auto vocabulary"></button>
        </div>
        <div class="hint" id="vocab-auto-words" style="margin-top:6px;"></div>
      </div>
```

JS (new functions + init hook):

```javascript
async function renderVocab() {
  const v = await api().vocab_get();
  setToggle($("t-autovocab"), v.auto_enabled);
  const chips = $("vocab-chips"); chips.innerHTML = "";
  if (!v.custom.length) {
    const e = document.createElement("span"); e.className = "hint";
    e.textContent = "No custom words yet.";
    chips.appendChild(e);
  }
  v.custom.forEach(w => {
    const chip = document.createElement("span"); chip.className = "chipword";
    chip.textContent = w + " ";
    const x = document.createElement("button");
    x.textContent = "×"; x.setAttribute("aria-label", "remove " + w);
    x.style.cssText = "background:none;border:none;color:var(--muted);cursor:pointer;padding:0 2px;";
    x.onclick = async () => { await api().vocab_remove(w); renderVocab(); };
    chip.appendChild(x); chips.appendChild(chip);
  });
  $("vocab-auto-words").textContent = v.auto_enabled
    ? (v.auto_words.length ? "Auto: " + v.auto_words.join(" · ") : "Auto: none yet — dictate more to build your signature words")
    : "";
}
async function vocabAdd() {
  const w = $("vocab-input").value;
  if (!w.trim()) return;
  const r = await api().vocab_add(w);
  if (r.error) { msg("m-vocab", r.error, "err"); return; }
  $("vocab-input").value = "";
  msg("m-vocab", "Added — takes effect on your next dictation", "ok");
  renderVocab();
}
$("b-vocab-add").addEventListener("click", vocabAdd);
$("vocab-input").addEventListener("keydown", e => { if (e.key === "Enter") vocabAdd(); });
$("t-autovocab").addEventListener("click", async () => {
  const want = !isOn($("t-autovocab"));
  const r = await api().set_value("auto_vocabulary", want);
  if (r.ok) renderVocab(); else msg("m-vocab", r.error, "err");
});
```

`init()` calls `renderVocab()`. Probe: `vocab = evaluate_js("document.getElementById('vocab-input') ? 1 : 0")` appended to the probe print; smoke asserts `vocab=1`.

- [ ] **Step 4:** Bridge + smoke tests pass; full suite green.
- [ ] **Step 5:** `git add settings_ui.py settings.html tests/ && git commit -m "feat: vocabulary editor in Transcription tab"`

---

### Task 5: v0.5.0 release train

- [ ] **Step 1:** `paths.APP_VERSION = "0.5.0"`; version asserts → 0.5.0. Full suite ×2 (exit codes).
- [ ] **Step 2:** Kill app + FlowLocal webview children; PyInstaller rebuild; frozen `--settings --smoke` log probe asserts `navs=8 version=0.5.0 ... vocab=1`.
- [ ] **Step 3:** `bash scripts/build_msi.sh` (background) → hardened build auto-purges 0.4.0 MSI, atomic rename.
- [ ] **Step 4:** Install over current 0.4.0 (per-user, hardened MajorUpgrade) → exit 0; `ProductsEx("","",2)` shows exactly ONE FlowLocal at 0.5.0; installed smoke probe passes.
- [ ] **Step 5:** Live sanity (non-gating): SAPI-dictate "ScratchEdge" once with it in custom vocabulary; note transcript in the log.
- [ ] **Step 6:** README: Vocabulary section under Settings; test count updated. Adversarial review workflow (merge/validate edge cases, hotwords thread-visibility, bridge/UI injection safety, rebuild cadence); fix confirmed; `git status` before adds; suite ×2.
- [ ] **Step 7:** Push; release commit `flowlocal v0.5.0 — custom vocabulary + auto signature hotwords`; tag `v0.5.0`; push --tags; relaunch INSTALLED copy; memory; report.
