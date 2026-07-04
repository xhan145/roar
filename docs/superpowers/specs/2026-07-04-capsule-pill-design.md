# Slim Capsule Pill (SP9) — Design

**Version:** v0.11.1 (visual patch — no new config, no new features)
**Date:** 2026-07-04
**Status:** approved (variant A of three mockups)

## Goal

Simplify the dictation overlay pill and restyle it white + lavender. One row,
less chrome, state carried by color instead of a status dot.

## Visual spec

- **Geometry:** 360×44 capsule (was 400×76). Corner radius = H/2 (fully
  rounded ends), drawn with the existing smooth-polygon + `transparentcolor`
  technique. Position unchanged (bottom-center, 140px above screen bottom).
- **Colors (flat fills — Tk has no alpha/shadows):**
  - Pill fill `#FFFFFF`, hairline border `#E4DEF7` (pale lavender).
  - Bars while recording `#A78BFA` (vivid lavender).
  - Bars while transcribing/idle `#DDD6FE` (pale lavender).
  - Text `#4C4568` (dark plum), Segoe UI 10.
  - `TRANS_KEY #010203` unchanged (corner transparency).
- **Bars:** 12 bars (was 24), 4px wide, 3px gap (7px step, cluster = 81px),
  max height 20px, vertically centered on H/2.
- **No status dot.** Bar color is the state signal.
- **Layout:** with text present, bar cluster starts at x=18 and text sits to
  its right (west-anchored, vertically centered), head-truncated via
  `tail_text(txt, 34)` (~230px of room at Segoe UI 10). With no text, the bar
  cluster centers itself in the capsule.

## Behavior (unchanged)

Threading model, command queue, adaptive 33/250ms tick, public API
(`start/push_level/show_recording/set_partial/show_transcribing/hide/stop`),
exception-proof cosmetic-only contract, and `overlay_enabled` /
`streaming_preview` config semantics all stay exactly as they are.
Transcribing still appends "…" to the partial ("…" alone when no partial).
Errors never touch the pill (notify path).

## Implementation

`overlay.py` only:
- Replace color constants; delete `REC`/`MUTED`/`DIM`/`ACCENT`/`BG` in favor of
  `PILL`, `PILL_BORDER`, `BAR_ACTIVE`, `BAR_IDLE`, `TEXT`.
- `W, H = 360, 44`; `N_BARS = 12`; `BAR_AREA_H = 20`.
- New pure helper `bar_cluster_x(has_text: bool, w=W) -> int` (18 when text,
  centered otherwise) so layout is unit-testable.
- Rewrite `_draw()` for the one-row layout; drop the dot oval.
- `paths.APP_VERSION = "0.11.1"` + version asserts.

## Testing

- Existing pure tests unchanged (`bar_heights`, `tail_text` keep signatures).
- New: `bar_heights` at the new defaults (n=12, h=20); `bar_cluster_x` both
  branches; lifecycle smoke test unchanged.
- Live visual check from source (dictate, observe pill) before packaging.

## Release

v0.11.1 train: suite ×2, exe rebuild, frozen probe (`version=0.11.1`),
external-CAB MSI, focused review, upgrade-install over 0.11.0 (data intact),
fetch→push, tag, relaunch, memory.
