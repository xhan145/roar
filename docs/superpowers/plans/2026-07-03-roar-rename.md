# ROAR Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the product FlowLocal → ROAR everywhere runtime-reachable, migrate user data dirs, ship v0.6.0 whose MSI upgrades the installed FlowLocal 0.5.0 in place.

**Architecture:** `paths.migrate_legacy_data()` (frozen-only, rename-in-place, never deletes) + a scripted string sweep over the enumerated files, gated by a repo-wide grep. Same UpgradeCode keeps Windows Installer upgrade continuity.

**Tech Stack:** stdlib. Existing build chain (PyInstaller → WiX), builds strictly serialized.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-03-roar-rename-design.md` — its rename map is normative; "Deliberately NOT renamed" list is normative too (repo folder/name, historical docs, module filenames).
- Casing exactly **ROAR**. `paths.APP_NAME = "ROAR"`, `APP_VERSION = "0.6.0"`. UpgradeCode `a7a83e4a-83a0-4834-8edc-8dc058eb254f` UNCHANGED.
- Never delete user data; migration is os.rename or nothing. Builds one at a time. Kill ROAR/FlowLocal exe + their msedgewebview2 children before builds/installs. `git status` before adds.

---

### Task 1: paths rename + migration (TDD)

**Files:** Modify `paths.py`; Test: `tests/test_paths.py` (additions)

**Interfaces:** `APP_NAME="ROAR"`, `APP_VERSION="0.6.0"`, `migrate_legacy_data(old_name="FlowLocal") -> list[str]` (log lines of what moved; frozen-only via `is_frozen()`; also migrates the autostart Run value).

- [ ] **Step 1: failing tests** (append to `tests/test_paths.py`):

```python
def test_app_name_is_roar():
    assert paths.APP_NAME == "ROAR"
    assert paths.APP_VERSION == "0.6.0"


def test_migrate_legacy_data_renames_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    la, ra = tmp_path / "Local", tmp_path / "Roaming"
    (la / "FlowLocal").mkdir(parents=True)
    (la / "FlowLocal" / "history.db").write_text("data")
    (ra / "FlowLocal").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(la))
    monkeypatch.setenv("APPDATA", str(ra))
    moved = paths.migrate_legacy_data()
    assert (la / "ROAR" / "history.db").read_text() == "data"
    assert not (la / "FlowLocal").exists()
    assert (ra / "ROAR").exists() and not (ra / "FlowLocal").exists()
    assert len(moved) >= 2


def test_migrate_no_clobber_when_both_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    la = tmp_path / "Local"
    (la / "FlowLocal").mkdir(parents=True)
    (la / "FlowLocal" / "old.txt").write_text("old")
    (la / "ROAR").mkdir(parents=True)
    (la / "ROAR" / "new.txt").write_text("new")
    monkeypatch.setenv("LOCALAPPDATA", str(la))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    paths.migrate_legacy_data()
    assert (la / "FlowLocal" / "old.txt").exists()   # untouched
    assert (la / "ROAR" / "new.txt").exists()


def test_migrate_noop_when_not_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    assert paths.migrate_legacy_data() == []
```

- [ ] **Step 2:** Run → FAIL (APP_NAME still FlowLocal; no migrate function).
- [ ] **Step 3:** In `paths.py`: `APP_NAME = "ROAR"`, `APP_VERSION = "0.6.0"`, and:

```python
def migrate_legacy_data(old_name="FlowLocal"):
    """One-time rename of legacy data dirs + autostart entry. Frozen-only.
    Never deletes: rename-in-place or leave everything where it is."""
    if not is_frozen():
        return []
    moved = []
    import time
    for env in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        old = os.path.join(base, old_name)
        new = os.path.join(base, APP_NAME)
        if os.path.isdir(old) and not os.path.exists(new):
            for attempt in (1, 2):
                try:
                    os.rename(old, new)
                    moved.append(f"migrated {old} -> {new}")
                    break
                except OSError:
                    if attempt == 1:
                        time.sleep(2)  # webview stragglers may hold locks
                    else:
                        moved.append(f"could not migrate {old}; data left in place")
        elif os.path.isdir(old) and os.path.isdir(new):
            moved.append(f"both {old} and {new} exist; using {new}, leaving {old}")
    try:
        import autostart
        if autostart.get(old_name) is not None:
            autostart.set_enabled(old_name, "", False)
            autostart.set_enabled(APP_NAME, autostart.default_command(), True)
            moved.append("autostart entry renamed")
    except OSError:
        pass
    return moved
```

Call it at the top of `app.main()` (right after `redirect_output_when_frozen`, printing each line via `print(f"{APP_NAME}: {line}")`... concretely `for line in paths.migrate_legacy_data(): print(f"ROAR: {line}", flush=True)`) and at the top of `settings_ui.run_settings()` (same pattern, before the mutex).

- [ ] **Step 4:** tests pass. **Step 5:** commit `refactor: ROAR identity in paths + legacy data migration`.

---

### Task 2: scripted string sweep + grep gate

**Files:** Modify `app.py`, `settings_ui.py`, `settings.html`, `README.md`, `installer/flowlocal.wxs`, `scripts/build_msi.sh`, `scripts/make_icon.py` (comment only), all `tests/*.py` assertions; `git mv flowlocal.spec roar.spec`.

- [ ] **Step 1:** Python sweep script (run once, from repo root) applying exact replacements per file — the full pair list:
  - everywhere in the files above: `FlowLocal:` → `ROAR:`; `Global\\FlowLocalSingleton` → `Global\\ROARSingleton`; `Global\\FlowLocalSettings` → `Global\\ROARSettings`; `"FlowLocal"` display strings → `"ROAR"`; `FlowLocal Settings` → `ROAR Settings`; `FLOWLOCAL` → `ROAR`; `FlowLocal.exe` → `ROAR.exe`; `dist/FlowLocal` → `dist/ROAR`; `FlowLocal-$VERSION` → `ROAR-$VERSION`; `FlowLocal-*.msi` → `ROAR-*.msi`; wxs: `Name="FlowLocal"` → `Name="ROAR"` (Product + Directory + Shortcut), `Software\FlowLocal` → `Software\ROAR`; remaining prose `FlowLocal` → `ROAR`.
  - `settings_ui.py`: replace local `APP_NAME = "FlowLocal"` with `APP_NAME = paths.APP_NAME`.
  - `roar.spec`: `name="FlowLocal"` → `name="ROAR"` (EXE and COLLECT); build_msi.sh references `roar.spec` in its comment and `dist/ROAR`.
- [ ] **Step 2: grep gate** — `grep -rniE "flowlocal" *.py settings.html README.md installer scripts roar.spec tests` → ONLY acceptable hits: none. (Docs and repo path excluded by not being listed.)
- [ ] **Step 3:** Full suite ×2 (exit codes) — all marker assertions now expect `ROAR:`; smoke expects `version=0.6.0`.
- [ ] **Step 4:** Commit `refactor: rename product to ROAR across runtime surfaces`.

---

### Task 3: builds + upgrade verification + release

- [ ] **Step 1:** Kill app + webview children. `venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm` → `dist/ROAR/ROAR.exe`. Smoke: `--settings --smoke` probe in `%LOCALAPPDATA%\ROAR\roar… ` — note: log file name stays `flowlocal.log`? NO — `log_path()` derives from `_data_dir()` only by directory; filename literal `flowlocal.log` in paths.py must be renamed to `roar.log` in Task 2's sweep (add pair `flowlocal.log` → `roar.log`). Assert `ROAR:` markers + `navs=8 version=0.6.0 vocab=1`.
- [ ] **Step 2:** `bash scripts/build_msi.sh` (alone) → `dist/ROAR-0.6.0.msi`; old FlowLocal-0.5.0.msi purged manually (purge pattern only matches ROAR-*).
- [ ] **Step 3:** Upgrade verify: seed a marker row in the CURRENT `%LOCALAPPDATA%\FlowLocal\history.db`; install ROAR-0.6.0.msi over installed FlowLocal 0.5.0 → exit 0; ProductsEx = exactly one product, name ROAR, v0.6.0; `Programs\FlowLocal` gone, `Programs\ROAR\ROAR.exe` present; launch installed ROAR → migration log lines; history row count preserved in `%LOCALAPPDATA%\ROAR\history.db`; Start Menu shortcut "ROAR".
- [ ] **Step 4:** Adversarial review workflow (missed strings, migration edges, upgrade semantics); fix confirmed; suite ×2; `git status` before adds.
- [ ] **Step 5:** Push; release commit `roar v0.6.0 — product renamed from FlowLocal`; tag v0.6.0; push --tags; relaunch installed ROAR; update memory; report (include GH-repo-rename offer).
