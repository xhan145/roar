# Slim Capsule Pill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the dictation overlay as a simplified one-row white + lavender capsule (approved variant A).

**Architecture:** Constants + `_draw()` rewrite inside `overlay.py` only; threading model, queue, tick cadence, and the public API are untouched. A new pure helper `bar_cluster_x` makes the layout unit-testable.

**Tech Stack:** Python 3.14 (`venv/Scripts/python.exe`), tkinter Canvas, pytest; PyInstaller/WiX release train.

## Global Constraints

- Version bumps to `0.11.1` (`paths.APP_VERSION`) — visual patch, no config changes.
- Colors are FLAT fills (Tk has no alpha/shadow): pill `#FFFFFF`, border `#E4DEF7`, bars recording `#A78BFA`, bars idle/transcribing `#DDD6FE`, text `#4C4568`, `TRANS_KEY #010203` unchanged.
- Geometry: `W, H = 360, 44`; `N_BARS = 12`; `BAR_AREA_H = 20`; bar width 4, step 7 (cluster 81px); no status dot.
- Overlay stays cosmetic-only: every public method exception-proof; position (bottom-center, 140px up) unchanged.
- Kill ROAR.exe + webviews before builds/installs; MSI uses external CABs; serialize builds; fetch before push.

---

### Task 1: overlay redesign (TDD)

**Files:**
- Modify: `overlay.py`, `paths.py` (0.11.1)
- Test: `tests/test_overlay.py`, `tests/test_paths.py`, `tests/test_settings_bridge.py` (version asserts)

**Interfaces:**
- Produces: `bar_cluster_x(has_text: bool, w: int = W) -> int`; constants
  `PILL`, `PILL_BORDER`, `BAR_ACTIVE`, `BAR_IDLE`, `TEXT`, `W=360`, `H=44`,
  `N_BARS=12`, `BAR_AREA_H=20`. `bar_heights`/`tail_text` signatures unchanged.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_overlay.py`:

```python
def test_new_geometry_constants():
    assert (overlay.W, overlay.H) == (360, 44)
    assert overlay.N_BARS == 12 and overlay.BAR_AREA_H == 20


def test_bar_cluster_x_left_when_text_centered_when_not():
    assert overlay.bar_cluster_x(True) == 18
    # cluster = 12 bars * 7px step - 3px trailing gap = 81px
    assert overlay.bar_cluster_x(False) == (overlay.W - 81) // 2


def test_bar_heights_new_defaults():
    out = overlay.bar_heights([1.0] * 12)
    assert len(out) == 12 and max(out) == 20
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_overlay.py -q`
Expected: FAIL — `AttributeError: bar_cluster_x` / geometry mismatch.

- [ ] **Step 3: Implement** — in `overlay.py`, replace the constants block:

```python
PILL = "#FFFFFF"
PILL_BORDER = "#E4DEF7"
BAR_ACTIVE = "#A78BFA"   # recording
BAR_IDLE = "#DDD6FE"     # transcribing / resting
TEXT = "#4C4568"
TRANS_KEY = "#010203"   # transparentcolor => rounded pill corners
W, H = 360, 44
N_BARS = 12
BAR_AREA_H = 20
BAR_W, BAR_STEP = 4, 7
CLUSTER_W = N_BARS * BAR_STEP - (BAR_STEP - BAR_W)  # 81
```

(Delete `ACCENT`, `BG`, `BORDER`, `MUTED`, `REC`, `DIM`.) Add the pure helper
after `tail_text`:

```python
def bar_cluster_x(has_text, w=W):
    """Bars hug the left when text shares the row, center otherwise."""
    return 18 if has_text else (w - CLUSTER_W) // 2
```

Replace `_draw` with:

```python
    def _draw(self):
        c = self._canvas
        c.delete("all")
        r = H // 2  # capsule: fully rounded ends
        c.create_polygon(
            r, 2, W - r, 2, W - 2, 2, W - 2, r, W - 2, H - r, W - 2, H - 2,
            W - r, H - 2, r, H - 2, 2, H - 2, 2, H - r, 2, r, 2, 2,
            smooth=True, fill=PILL, outline=PILL_BORDER)
        txt = self._partial
        if self._mode == "transcribing":
            txt = (txt + " …") if txt else "…"
        color = BAR_ACTIVE if self._mode == "recording" else BAR_IDLE
        heights = bar_heights(self._levels)
        mid = H // 2
        x_start = bar_cluster_x(bool(txt))
        for i, bh in enumerate(heights):
            x0 = x_start + i * BAR_STEP
            c.create_rectangle(x0, mid - bh // 2, x0 + BAR_W, mid + bh // 2,
                               fill=color, outline="")
        if txt:
            c.create_text(x_start + CLUSTER_W + 14, mid,
                          text=tail_text(txt, 34), fill=TEXT,
                          font=("Segoe UI", 10), anchor="w")
```

`paths.py`: `APP_VERSION = "0.11.1"`. Update version asserts:
`tests/test_paths.py` and `tests/test_settings_bridge.py::test_get_state_shape`
from `"0.11.0"` to `"0.11.1"`.

- [ ] **Step 4: Full suite ×2** (kill ROAR.exe + webviews first)

Run: `venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_transcriber_gpu.py`
Expected: PASS twice (lifecycle smoke exercises the new `_draw` live).

- [ ] **Step 5: Live visual check** — run `venv/Scripts/python.exe app.py` from
  source, dictate a sentence, confirm: white capsule, lavender bars left,
  text beside bars, bars pale during transcribing, no dot. Kill the source app
  after. (Screenshot for the report if possible.)

- [ ] **Step 6: Commit**

```bash
git add overlay.py paths.py tests/test_overlay.py tests/test_paths.py tests/test_settings_bridge.py
git commit -m "feat: slim white+lavender capsule pill; bump v0.11.1"
```

---

### Task 2: release train v0.11.1

- [ ] **Step 1:** README: update the overlay/pill description if it mentions
  the old look; add `v0.11.1` milestone line. Commit `docs: capsule pill`.
- [ ] **Step 2:** Kill ROAR.exe + webviews; exe rebuild; frozen probe
  (`version=0.11.1`, all probe flags green); MSI build SOLO (external CABs).
- [ ] **Step 3:** Focused review (Workflow, small): capsule geometry/centering
  math, tail_text width vs 34 chars, mode-color mapping, no regression to the
  cosmetic-only contract. Verify confirmed findings inline; fix; suite ×2.
- [ ] **Step 4:** Upgrade-install over 0.11.0 (kill first): exit 0, single
  ROAR v0.11.1, installed probe green, config + history intact.
- [ ] **Step 5:** `git fetch` → push; release commit `roar v0.11.1 — capsule
  pill`; tag; push --tags; relaunch installed ROAR; MEMORY.md +
  flowlocal-project.md; final report.
