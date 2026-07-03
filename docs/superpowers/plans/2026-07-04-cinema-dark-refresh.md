# Cinema Dark Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle settings window, dictation pill, tray icons, and app icon to Cinema Dark (spec tokens); v0.8.0; zero behavior change.

**Architecture:** Token substitution in `settings.html` `:root` + targeted class updates + inline SVG sidebar icons; color-constant swaps in `overlay.py`, `tray_icons.py`, `scripts/make_icon.py`; icon.ico regeneration; standard release train.

**Tech Stack:** CSS/SVG only + Python color constants. No new deps.

## Global Constraints

- Spec `docs/superpowers/specs/2026-07-04-cinema-dark-refresh-design.md` tokens are normative. NO behavior/DOM-ID/bridge changes — the 129-test suite and probe must pass untouched (only version asserts move to 0.8.0).
- Accent `#5E6AD2` replaces `#2563EB` on brand surfaces; recording red + error amber stay semantic. Radius 16 cards / 24 pill. Hairline borders `rgba(255,255,255,.08)`.
- Kill ROAR.exe + ROAR webviews before tests/builds; builds serialized; `git status` before adds.

---

### Task 1: settings.html restyle

**Files:** Modify `settings.html` only.

- [ ] **Step 1:** `:root` becomes:

```css
  :root {
    --bg-deep: #020203; --bg-base: #050506; --card: rgba(255,255,255,0.05);
    --side: rgba(255,255,255,0.03); --border: rgba(255,255,255,0.08);
    --text: #EDEDEF; --muted: #8A8F98; --disabled: #4A4F5E;
    --accent: #5E6AD2; --glow: rgba(94,106,210,.35);
    --err: #F87171; --ok: #34D399;
    --ease: cubic-bezier(0.16,1,0.3,1);
  }
```

body: `background: linear-gradient(180deg, #0a0a0f, #020203); color: var(--text);` (replace `--bg` uses accordingly — global replace `var(--bg)` → `var(--bg-deep)` where used as solid, e.g. old `--bg` in tone rows/pill mock; audit each use). Class deltas (exact):
  - `aside`: `background: var(--side); border-right: 1px solid var(--border);`
  - `.nav[aria-current="true"]`: `background: rgba(94,106,210,.16); border: 1px solid rgba(94,106,210,.45); box-shadow: 0 0 14px var(--glow); border-radius: 10px;`
  - `.row`: `border-radius: 16px;` (border stays 1px solid var(--border), bg var(--card))
  - `.toggle[aria-pressed="true"]`, `.btn:hover`, `.btn.primary`, `.chip.pending`, `.wbar`, `select/range accent-color`, `.pathlink`, focus ring: `#2563EB`→`var(--accent)`; glow values → `var(--glow)`.
  - inputs/selects solid `#0E1320` → `#0a0a0c`; `.chipword`/`.chip` bg → `#0a0a0c`; misc `#242C3D` (toggle off) → `#1A1D29`; `#3A4254` knobs → `#2A2E3F`.
  - transitions: `transition: all .2s var(--ease);` in the reduced-motion block.
- [ ] **Step 2:** Sidebar SVG icons — each nav button gains a leading inline SVG (16×16, `stroke="currentColor"`, `stroke-width="1.5"`, `fill="none"`, `stroke-linecap="round" stroke-linejoin="round"`, style `vertical-align:-3px;margin-right:8px;`):
  - General (sliders): `<svg viewBox="0 0 24 24" width="16" height="16"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h13M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>`
  - Hotkeys (keyboard): `<svg viewBox="0 0 24 24" width="16" height="16"><rect x="3" y="7" width="18" height="11" rx="2"/><path d="M7 11h.01M11 11h.01M15 11h.01M7 14h10"/></svg>`
  - Voice & Mic (mic): `<svg viewBox="0 0 24 24" width="16" height="16"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>`
  - Transcription (text-lines): `<svg viewBox="0 0 24 24" width="16" height="16"><path d="M4 6h16M4 12h16M4 18h9"/></svg>`
  - Insights (bars): `<svg viewBox="0 0 24 24" width="16" height="16"><path d="M5 20V10M12 20V4M19 20v-7"/></svg>`
  - Privacy (shield): `<svg viewBox="0 0 24 24" width="16" height="16"><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/></svg>`
  - History (clock): `<svg viewBox="0 0 24 24" width="16" height="16"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>`
  - About (info): `<svg viewBox="0 0 24 24" width="16" height="16"><circle cx="12" cy="12" r="8"/><path d="M12 11v5M12 8h.01"/></svg>`
- [ ] **Step 3:** History rows: replace the `" · 🔊"` string concat in `renderHistory` meta with a text marker `" · audio"` styled via muted span — concretely change `(r.has_audio ? " · 🔊" : "")` to `(r.has_audio ? " · audio kept" : "")` (textContent-safe, no-emoji rule).
- [ ] **Step 4:** Suite green (probe/DOM untouched); manual `app.py --settings` visual check.
- [ ] **Step 5:** `git add settings.html && git commit -m "style: Cinema Dark settings window (tokens, SVG icons, gradient)"`

---

### Task 2: pill + tray icons + app icon

**Files:** Modify `overlay.py`, `tray_icons.py`, `scripts/make_icon.py`; regenerate `icon.ico`.

- [ ] **Step 1:** `overlay.py` constants: `ACCENT="#5E6AD2"`, `BG="#0a0a0c"`, `BORDER="#23263B"`, `TEXT="#EDEDEF"`, `MUTED="#8A8F98"`, `REC="#F25757"`, `DIM="#3A3F58"`; `_draw` pill radius `r = 24`.
- [ ] **Step 2:** `tray_icons.py` COLORS: idle/loading `#8A8F98`, recording `#DC2626` (keep), transcribing `#5E6AD2`, error `#D97706` (keep).
- [ ] **Step 3:** `scripts/make_icon.py`: `BRAND = "#5E6AD2"`, disc fill `#0a0a0c`; run `venv/Scripts/python.exe scripts/make_icon.py`.
- [ ] **Step 4:** Suite green (icon tests assert distinctness not hexes); overlay lifecycle test passes.
- [ ] **Step 5:** `git add overlay.py tray_icons.py scripts/make_icon.py icon.ico && git commit -m "style: Cinema Dark pill, tray states, app icon (indigo)"`

---

### Task 3: version + README

- [ ] **Step 1:** `paths.APP_VERSION = "0.8.0"`; version asserts in `tests/test_settings_bridge.py` + `tests/test_paths.py` → 0.8.0.
- [ ] **Step 2:** README: change the Settings line `dark "Deep Focus" UI` → `dark "Cinema Dark" UI`; suite ×2 green (exit codes).
- [ ] **Step 3:** `git add -u && git commit -m "chore: bump v0.8.0, README Cinema Dark"` (status-checked).

---

### Task 4: release train v0.8.0

- [ ] **Step 1:** Kill app+webviews; PyInstaller `roar.spec`; frozen probe (`version=0.8.0 … ovl=1`); visual: launch dist exe, open settings once.
- [ ] **Step 2:** `bash scripts/build_msi.sh` (solo).
- [ ] **Step 3:** Kill app+webviews AGAIN (upgrade gotcha!); install over 0.7.0; ProductsEx = one ROAR v0.8.0; installed probe; data intact (history rows, ctrl+shift, device 8).
- [ ] **Step 4:** Adversarial review workflow (contrast regressions, missed old-token remnants `#2563EB`/`#0B0E14`/`#121722` greps, emoji sweep, icon consistency); fix confirmed; suite ×2.
- [ ] **Step 5:** Push; release commit `roar v0.8.0 — Cinema Dark interface refresh`; tag v0.8.0; push --tags; relaunch installed ROAR; MEMORY.md token section update; report.
