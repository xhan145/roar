# Snippets + Bundled Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ROAR Snippets (dictation-fired text expansion with variables + packs) and multilingual models seeded into the installer; v0.10.0.

**Architecture:** Pure `snippets.py` (expand/validate/variables) wired into `commands.process` as the last text stage; bridge CRUD + pack dialogs via a module-level `_WINDOW`; transcriber load order user-cache→bundled-seed→download; wxs multi-CAB + mszip for the ~2 GB seed.

**Tech Stack:** stdlib + existing deps (pyperclip, pywebview dialogs). Seed via `faster_whisper.download_model` (already fetching in background task blglhuufx).

## Global Constraints

- Spec `docs/superpowers/specs/2026-07-04-snippets-bundled-models-design.md` normative: names `[A-Za-z0-9-]{1,30}` case-insensitively unique, expansions ≤2000 chars, ≤100 snippets; one-pass expansion (no recursion); variables `{date}/{time}/{clipboard}`; unknown left literal.
- Nav count 8 → 9; probe adds `snip=1` and CLICKS the tab. v0.10.0.
- Builds serialized; kill app+webviews first; MSI uses mszip + MaximumUncompressedMediaSize=1024 (2 GB CAB limit, memory precedent); fetch-first push.

---

### Task 1: snippets.py (pure, TDD)

**Files:** Create `snippets.py`, `tests/test_snippets.py`

**Interfaces:** `expand(text, snippets, keyword="snippet", clipboard_getter=None) -> str`; `validate(name, expansion, existing: dict) -> str|None`; `resolve_variables(text, clipboard_getter=None) -> str`; `NAME_RE`, `MAX_SNIPPETS=100`, `MAX_EXPANSION=2000`.

- [ ] **Step 1: failing tests** `tests/test_snippets.py`:

```python
import snippets

SNIPS = {"sig": "Thanks,\nGreg", "addr": "42 Roar St"}


def test_keyword_form_expands():
    out = snippets.expand("please snippet sig today", SNIPS)
    assert out == "please Thanks,\nGreg today"


def test_keyword_case_insensitive_and_sentence_start():
    assert snippets.expand("Snippet sig", SNIPS) == "Thanks,\nGreg"


def test_literal_slash_form():
    assert snippets.expand("send to /addr now", SNIPS) == "send to 42 Roar St now"


def test_unknown_name_left_alone():
    assert snippets.expand("snippet nope and /nada", SNIPS) == "snippet nope and /nada"


def test_no_recursion_single_pass():
    out = snippets.expand("snippet a", {"a": "see snippet b", "b": "BOOM"})
    assert out == "see snippet b"


def test_word_boundaries():
    assert snippets.expand("crosssnippet sig", SNIPS) == "crosssnippet sig"
    assert snippets.expand("path//sig", SNIPS) == "path//sig"


def test_variables(monkeypatch):
    out = snippets.expand("snippet st", {"st": "at {time} clip={clipboard}"},
                          clipboard_getter=lambda: "CLIP")
    import re
    assert re.search(r"at \d{2}:\d{2} clip=CLIP", out)


def test_clipboard_failure_empty(monkeypatch):
    def boom():
        raise RuntimeError("no clipboard")
    out = snippets.expand("snippet c", {"c": "[{clipboard}]"},
                          clipboard_getter=boom)
    assert out == "[]"


def test_unknown_variable_left_literal():
    assert snippets.expand("snippet u", {"u": "{unknown}"} ) == "{unknown}"


def test_validate_rules():
    assert snippets.validate("sig", "x", {}) is None
    assert snippets.validate("bad name", "x", {}) is not None
    assert snippets.validate("", "x", {}) is not None
    assert snippets.validate("a" * 31, "x", {}) is not None
    assert snippets.validate("ok", "", {}) is not None
    assert snippets.validate("ok", "y" * 2001, {}) is not None
    full = {f"s{i}": "x" for i in range(snippets.MAX_SNIPPETS)}
    assert snippets.validate("new", "x", full) is not None
    assert snippets.validate("s1", "x", full) is None  # editing existing ok
```

- [ ] **Step 2:** run → ModuleNotFoundError.
- [ ] **Step 3:** `snippets.py`:

```python
"""Snippet expansion: 'snippet <name>' or '/<name>' in dictated text becomes
the stored expansion. One pass — expansions are never re-scanned."""
import re
import time

NAME_RE = re.compile(r"^[A-Za-z0-9-]{1,30}$")
MAX_SNIPPETS = 100
MAX_EXPANSION = 2000


def _default_clipboard():
    import pyperclip
    return pyperclip.paste()


def resolve_variables(text, clipboard_getter=None):
    out = text.replace("{date}", time.strftime("%x"))
    out = out.replace("{time}", time.strftime("%H:%M"))
    if "{clipboard}" in out:
        try:
            clip = (clipboard_getter or _default_clipboard)() or ""
        except Exception:
            clip = ""
        out = out.replace("{clipboard}", clip)
    return out


def expand(text, snippets, keyword="snippet", clipboard_getter=None):
    if not snippets or not isinstance(snippets, dict):
        return text
    table = {k.lower(): v for k, v in snippets.items()
             if isinstance(k, str) and isinstance(v, str)}

    def sub(match):
        name = match.group(1).lower()
        if name in table:
            return resolve_variables(table[name], clipboard_getter)
        return match.group(0)

    text = re.sub(r"(?<!\S)" + re.escape(keyword) + r"\s+([A-Za-z0-9-]{1,30})\b",
                  sub, text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\S)/([A-Za-z0-9-]{1,30})\b", sub, text)
    return text


def validate(name, expansion, existing):
    if not NAME_RE.match(name or ""):
        return "names are 1-30 letters, digits or dashes"
    if not expansion or len(expansion) > MAX_EXPANSION:
        return f"expansions are 1-{MAX_EXPANSION} characters"
    lower_existing = {k.lower() for k in existing}
    if len(existing) >= MAX_SNIPPETS and (name or "").lower() not in lower_existing:
        return f"limited to {MAX_SNIPPETS} snippets"
    return None
```

- [ ] **Step 4:** 11 tests pass. **Step 5:** commit `feat: snippet expansion engine (pure)`.

---

### Task 2: config + pipeline (TDD)

**Files:** Modify `config.py`, `commands.py`, `app.py`; tests append `tests/test_commands.py`, `tests/test_config.py`

**Interfaces:** DEFAULTS += `"snippets": {}`, `"snippet_keyword": "snippet"`; load sanitizes snippets (str→str merge, same as replacements); `commands.process(text, replacements, snippets=None, snippet_keyword="snippet")` — expansion is the LAST stage (after capitalize, before the final empty-check); app passes cfg values.

- [ ] **Step 1: failing tests.** test_commands append:

```python
def test_snippet_expansion_in_pipeline():
    out = commands.process("snippet sig", {}, {"sig": "Thanks,\nGreg"})
    assert out == "Thanks,\nGreg"


def test_snippets_after_replacements_and_capitalize():
    out = commands.process("hello new line snippet sig", REPL,
                           {"sig": "greg"})
    assert out == "Hello\ngreg"   # capitalize hit transcript, not expansion


def test_process_backcompat_two_args():
    assert commands.process("plain", {}) == "Plain"
```

test_config append:

```python
def test_snippets_sanitized_on_load(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"snippets": {"ok": "text", "bad": 7, 3: "x"}}))
    cfg = config.load(str(p))
    assert cfg["snippets"] == {"ok": "text"}
    assert cfg["snippet_keyword"] == "snippet"
```

- [ ] **Step 2:** FAIL. **Step 3:** DEFAULTS += the two keys; load(): `elif key == "snippets" and isinstance(value, dict): cfg["snippets"].update({k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)})`. `commands.py`: add `import snippets as snippets_mod`; `process(text, replacements, snippets=None, snippet_keyword="snippet")`; after the capitalize loop insert:

```python
    if snippets:
        text = snippets_mod.expand(text, snippets, keyword=snippet_keyword)
```

`app.py` `_handle_transcription`: `text = commands.process(raw, self.cfg["replacements"], self.cfg.get("snippets"), self.cfg.get("snippet_keyword", "snippet"))`.

- [ ] **Step 4:** suite green. **Step 5:** commit `feat: snippets in the dictation pipeline`.

---

### Task 3: bridge CRUD + packs + UI tab + version (TDD)

**Files:** Modify `settings_ui.py`, `settings.html`, `paths.py` (0.10.0) + version asserts + smoke; tests append `tests/test_settings_bridge.py`

**Interfaces:** module global `_WINDOW = None` (set by run_settings after create_window; tests monkeypatch); `snippets_get() -> {snippets, keyword}`; `snippet_save(name, text)`; `snippet_delete(name)`; `snippets_export() -> {ok,path}|{cancelled}|{error}`; `snippets_import() -> {ok,added,renamed}|{cancelled}|{error}`. All writes under `_cfg_lock`; save replaces case-insensitive duplicates; import merges with `-2` suffix on collision.

- [ ] **Step 1: failing tests** (append):

```python
def test_snippet_crud(tmp_path):
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert api.snippets_get()["snippets"] == {}
    assert api.snippet_save("sig", "Thanks,\nGreg")["ok"] is True
    assert "error" in api.snippet_save("bad name", "x")
    assert api.snippet_save("SIG", "replaced")["ok"] is True   # case-insensitive replace
    assert api.snippets_get()["snippets"] == {"SIG": "replaced"}
    assert api.snippet_delete("sig")["ok"] is True
    assert api.snippets_get()["snippets"] == {}


def test_snippet_pack_round_trip(tmp_path, monkeypatch):
    import settings_ui as su
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api.snippet_save("sig", "Greg")
    pack = tmp_path / "pack.json"

    class StubWin:
        def create_file_dialog(self, kind, **kw):
            return str(pack)
    monkeypatch.setattr(su, "_WINDOW", StubWin())
    assert api.snippets_export()["ok"] is True
    api.snippet_delete("sig")
    api.snippet_save("sig", "different")          # collision on import
    r = api.snippets_import()
    assert r["ok"] is True and r["added"] == 1 and r["renamed"] == 1
    snaps = api.snippets_get()["snippets"]
    assert snaps["sig"] == "different" and snaps["sig-2"] == "Greg"
```

- [ ] **Step 2:** FAIL. **Step 3:** implement (module global `_WINDOW = None`; run_settings sets `settings_ui_module._WINDOW = window` — plain `global _WINDOW; _WINDOW = window`):

```python
    def snippets_get(self):
        cfg = config_mod.load(self.config_path)
        return {"snippets": cfg.get("snippets", {}),
                "keyword": cfg.get("snippet_keyword", "snippet")}

    def snippet_save(self, name, text):
        from snippets import validate
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            sn = dict(cfg.get("snippets", {}))
            err = validate(name, text, sn)
            if err:
                return {"error": err}
            for k in list(sn):
                if k.lower() == name.lower():
                    del sn[k]
            sn[name] = text
            self._write(snippets=sn)
        return {"ok": True}

    def snippet_delete(self, name):
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            sn = {k: v for k, v in cfg.get("snippets", {}).items()
                  if k.lower() != str(name).lower()}
            self._write(snippets=sn)
        return {"ok": True}

    def snippets_export(self):
        import json as _json
        import webview
        if _WINDOW is None:
            return {"error": "no window"}
        path = _WINDOW.create_file_dialog(
            webview.SAVE_DIALOG, save_filename="roar-snippets.json")
        if not path:
            return {"cancelled": True}
        path = path if isinstance(path, str) else path[0]
        cfg = config_mod.load(self.config_path)
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(cfg.get("snippets", {}), f, indent=2, ensure_ascii=False)
        return {"ok": True, "path": str(path)}

    def snippets_import(self):
        import json as _json
        import webview
        from snippets import validate
        if _WINDOW is None:
            return {"error": "no window"}
        path = _WINDOW.create_file_dialog(webview.OPEN_DIALOG)
        if not path:
            return {"cancelled": True}
        path = path if isinstance(path, str) else path[0]
        try:
            with open(path, encoding="utf-8") as f:
                incoming = _json.load(f)
            assert isinstance(incoming, dict)
        except Exception as e:
            return {"error": f"not a snippet pack: {e}"}
        added = renamed = 0
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            sn = dict(cfg.get("snippets", {}))
            lower = {k.lower() for k in sn}
            for name, text in incoming.items():
                if not isinstance(name, str) or not isinstance(text, str):
                    continue
                target = name
                if name.lower() in lower:
                    target = f"{name}-2"
                    if target.lower() in lower:
                        continue
                    renamed += 1
                if validate(target, text, sn) is None:
                    sn[target] = text
                    lower.add(target.lower())
                    added += 1
            self._write(snippets=sn)
        return {"ok": True, "added": added, "renamed": renamed}
```

Note the StubWin test path bypasses the `import webview` cost only at dialog-kind constants — tests need webview importable (it is, in the venv). `settings.html`: sidebar button `<button class="nav" data-s="snippets">(scissors SVG)Snippets</button>` after History; new section with list div, name input, textarea, Save + Export + Import buttons, msg line; JS `renderSnippets()` (cards via textContent, Delete + Edit-fills-form), save handler → `snippet_save`, export/import handlers show returned path/counts. Probe: `snip` via `document.getElementById('snip-name') ? 1 : 0` AND a nav-click activation check like the others; smoke asserts `navs=9`, `snip=1`. `paths.APP_VERSION = "0.10.0"`; bridge + paths test asserts → 0.10.0.

- [ ] **Step 4:** suite ×2 green. **Step 5:** commit `feat: Snippets tab, packs, bridge; bump v0.10.0`.

---

### Task 4: seed resolution + bundle plumbing (TDD)

**Files:** Modify `transcriber.py`, `roar.spec`, `installer/roar.wxs`; tests append `tests/test_transcriber.py`

**Interfaces:** `seed_dir(model_name) -> str|None` (checks `paths.resource_path("models-seed/<name>")`); load source order per attempt: (name, local_files_only=True) → (seed_path,) → (name, download).

- [ ] **Step 1: failing test** (append):

```python
def test_seed_dir_resolution(tmp_path, monkeypatch):
    import paths
    from transcriber import seed_dir
    monkeypatch.setattr(paths, "resource_path",
                        lambda name: str(tmp_path / name))
    assert seed_dir("small") is None
    (tmp_path / "models-seed" / "small").mkdir(parents=True)
    assert seed_dir("small").endswith("small")


def test_load_source_order_uses_seed(monkeypatch, tmp_path):
    import paths
    import transcriber as tr
    (tmp_path / "models-seed" / "small").mkdir(parents=True)
    monkeypatch.setattr(paths, "resource_path",
                        lambda name: str(tmp_path / name))
    calls = []

    class StubWM:
        def __init__(self, src, **kw):
            calls.append((src, kw.get("local_files_only")))
            if kw.get("local_files_only"):
                raise RuntimeError("not in cache")

    monkeypatch.setattr(tr, "WhisperModel", StubWM)
    t = tr.Transcriber(model_name="small", force_device="cpu")
    t.load()
    assert calls[0][1] is True                       # cache first
    assert calls[1][0].endswith("small")             # then bundled seed
    assert t.active_model == "small"
```

- [ ] **Step 2:** FAIL. **Step 3:** `transcriber.py`:

```python
def seed_dir(model_name):
    """Bundled offline copy of a model, when the installer shipped one."""
    p = paths.resource_path(os.path.join("models-seed", model_name))
    return p if os.path.isdir(p) else None
```

(add `import paths` to transcriber imports). In `load()`, replace the single WhisperModel call per attempt with the source order:

```python
        for model, dev, compute in attempts:
            sources = [(model, {"download_root": self.models_dir,
                                "local_files_only": True})]
            seed = seed_dir(model)
            if seed:
                sources.append((seed, {}))
            sources.append((model, {"download_root": self.models_dir}))
            for src, extra in sources:
                try:
                    if dev == "cuda":
                        _add_nvidia_dll_dirs()
                    self.log(f"loading {model} on {dev} ({compute})...")
                    self._model = WhisperModel(src, device=dev,
                                               compute_type=compute, **extra)
                    self.active_model, self.device = model, dev
                    return
                except Exception as e:
                    last_err = e
            self.log(f"load failed for {model} on {dev}: {last_err}")
```

`roar.spec` after the settings.html datas line:

```python
import os as _os
if _os.path.isdir("models-seed"):
    datas += [("models-seed", "models-seed")]
```

`installer/roar.wxs`: `<MediaTemplate EmbedCab="yes" CompressionLevel="mszip" MaximumUncompressedMediaSize="1024" />`.

- [ ] **Step 4:** suite green (existing load tests still pass — cache-first succeeds where models exist). **Step 5:** commit `feat: bundled model seed resolution; multi-CAB mszip installer`.

---

### Task 5: release train v0.10.0

- [ ] **Step 1:** Confirm seed fetch (blglhuufx) done: `models-seed/large-v3-turbo/model.bin` + `models-seed/small/model.bin` exist. README: Snippets section (usage, variables, packs) + "languages included in the installer" note.
- [ ] **Step 2:** Kill app+webviews; exe rebuild (now ~3.5 GB dist); frozen probe `version=0.10.0 … snip=1 lang=1`; MSI build (mszip, multi-CAB, ~2.5 GB — expect 15-25 min, run SOLO).
- [ ] **Step 3:** Offline seed check on the frozen build: temp-rename `%LOCALAPPDATA%\ROAR\models` aside, run a script loading `small` via the dist exe's seed (or venv with resource_path monkeypatched to dist), assert load succeeds WITHOUT network/cache; restore models dir.
- [ ] **Step 4:** Upgrade over 0.9.0 (kill first — pythonnet 1304): exit 0, ProductsEx one ROAR v0.10.0, installed probe green, data intact.
- [ ] **Step 5:** Adversarial review (expansion regex edges/injection, pack import validation, seed-order regressions, CAB/size claims); fix confirmed; suite ×2; `git status` first.
- [ ] **Step 6:** fetch → push; release commit `roar v0.10.0 — snippets + languages included`; tag; push --tags; relaunch installed ROAR; MEMORY.md + memory; final report.
