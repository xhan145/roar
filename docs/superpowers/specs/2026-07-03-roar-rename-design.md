# Product Rename: FlowLocal → ROAR — Design Spec

**Date:** 2026-07-03
**Status:** Approved (explicit user directive: "before sp5 make the product be name ROAR across all code")
**Ships as:** v0.6.0 (rename-only release; precedes SP5 streaming)

## Rename map

| Surface | Old | New |
|---|---|---|
| Display name / brand / casing | FlowLocal | **ROAR** (all-caps) |
| Log prefix (stdout + log file) | `FlowLocal:` | `ROAR:` |
| Exe / dist folder | FlowLocal.exe, dist/FlowLocal | ROAR.exe, dist/ROAR |
| PyInstaller spec file | flowlocal.spec | roar.spec (EXE/COLLECT name "ROAR") |
| MSI artifact / Product Name / shortcut | FlowLocal-\<v\>.msi / FlowLocal | ROAR-\<v\>.msi / ROAR |
| MSI install dir / registry marker | Programs\FlowLocal / Software\FlowLocal | Programs\ROAR / Software\ROAR |
| MSI UpgradeCode | a7a83e4a-… | **UNCHANGED** (ROAR 0.6.0 upgrades FlowLocal 0.5.0 in place) |
| Mutexes | Global\FlowLocalSingleton, Global\FlowLocalSettings | Global\ROARSingleton, Global\ROARSettings |
| Autostart Run value | FlowLocal | ROAR (legacy value removed by migration) |
| Data dirs | %APPDATA%\FlowLocal, %LOCALAPPDATA%\FlowLocal | %APPDATA%\ROAR, %LOCALAPPDATA%\ROAR (migrated) |
| paths.APP_NAME / APP_VERSION | FlowLocal / 0.5.0 | ROAR / 0.6.0 |
| Settings window title / sidebar | FlowLocal Settings / FLOWLOCAL | ROAR Settings / ROAR |
| README title/copy, UI strings, notifications | FlowLocal | ROAR |
| Tests: marker/name assertions | FlowLocal:… | ROAR:… |

## Deliberately NOT renamed

- Repo folder `C:\Users\xhan1\flowlocal` and GitHub repo name (folder rename breaks the venv's absolute paths; GH rename offered separately).
- Historical docs under docs/superpowers/ (they are records; only the new spec/plan mention both names).
- Python module filenames (app.py, history.py, …) — internal.
- HF model cache contents.

## Migration (runs before anything opens files)

`paths.migrate_legacy_data()` called at the top of `app.main()` and `settings_ui.run_settings()`:
1. For each (old, new) of (%LOCALAPPDATA%\FlowLocal → %LOCALAPPDATA%\ROAR) and (%APPDATA%\FlowLocal → %APPDATA%\ROAR): if old exists and new doesn't → `os.rename` (same-volume, instant, carries history.db/audio/models/config.json/flowlocal.log). If BOTH exist (partial prior migration) → leave both, prefer new, log once.
2. Autostart: if Run value `FlowLocal` exists → delete it; if it existed, create `ROAR` pointing at the current binary (reuses the existing self-heal path).
3. Frozen-only concern; source mode uses the project dir (unchanged behavior).
4. Failure (locked file) → log and continue with old-name dirs still readable? NO — paths derive from APP_NAME=ROAR, so on rename failure the app would start empty. Mitigation: if rename fails, fall back to... keep simple + safe: retry once after 2s (webview stragglers), then proceed (empty new dir) and notify "your previous data is still in %LOCALAPPDATA%\FlowLocal" — never delete anything.

## Verification

- Full suite with updated assertions, ×2, exit codes.
- Grep sweep: `grep -ri flowlocal` over *.py, settings.html, installer/, scripts/, README — zero hits outside docs/ and this spec (repo-path strings in docs OK).
- Migration unit tests (tmp dirs, monkeypatched env): fresh rename; both-exist no-clobber; row-count preserved through History open post-migration.
- Rebuild exe (ROAR.exe) → smoke probes (`ROAR:` markers, navs=8 version=0.6.0 vocab=1); rebuild MSI (serialized, never concurrent — commit-memory lesson).
- MSI upgrade test: install ROAR-0.6.0.msi over installed FlowLocal 0.5.0 → exit 0; ProductsEx shows exactly one product, named ROAR, v0.6.0; Programs\FlowLocal dir gone, Programs\ROAR present; Start Menu shortcut ROAR; user data migrated (history row count preserved).
- Adversarial review workflow before push (missed-string sweep, migration edge cases, upgrade semantics).
- Push, release commit `roar v0.6.0 — product renamed from FlowLocal`, tag v0.6.0, relaunch installed ROAR.
