# ROAR Cinema Dark Interface Refresh — Design Spec

**Date:** 2026-07-04
**Status:** Approved (visual companion: user picked "Cinema Dark" of three UUPM-grounded directions)
**Ships as:** v0.8.0 (pure restyle — zero behavior change)

## Goal

Restyle every ROAR surface to the Cinema Dark direction (Linear/Raycast-style
premium dark): gradient depth, indigo accent, frosted hairline borders, radius
16, soft ambient glow. Surfaces: settings window, dictation pill, tray state
icons, app icon.

## Design tokens (normative)

| Token | Value |
|---|---|
| bg gradient | `linear-gradient(180deg, #0a0a0f, #020203)` (settings body) |
| bg deep / base / elevated | `#020203` / `#050506` / `#0a0a0c` |
| surface | `rgba(255,255,255,0.05)` |
| border | `rgba(255,255,255,0.08)` (hairline) |
| text / muted | `#EDEDEF` / `#8A8F98` |
| accent | `#5E6AD2` (indigo — replaces #2563EB everywhere non-semantic) |
| accent glow | `rgba(94,106,210,0.2–0.5)` |
| recording red | `#F25757` (pill dot; tray recording stays `#DC2626` family — semantic red kept) |
| error amber | `#D97706` (unchanged, semantic) |
| radius | 16 px cards/pill, 10 px small controls |
| motion | 200 ms, `cubic-bezier(0.16,1,0.3,1)`, under `prefers-reduced-motion: no-preference` only |

Accent swap is GLOBAL for brand surfaces: settings UI, pill bars, tray idle/
loading/transcribing tints, app icon (`scripts/make_icon.py` BRAND →
`#5E6AD2`, regenerate icon.ico). Recording red and error amber stay semantic.

## Surface-by-surface

- **settings.html** (structure/JS/probe IDs unchanged — restyle only):
  gradient body; sidebar = surface + hairline right border; active nav =
  indigo tint bg + hairline indigo border + soft glow; **inline SVG icons**
  (1.5 px stroke, 16 px, single set) for the 8 sidebar items; cards → surface
  + hairline + radius 16; toggles/buttons/sliders/selects/chips → indigo
  accents + glow on primary only; the history rows' `🔊` emoji → small inline
  speaker SVG (UUPM no-emoji rule); focus-visible rings indigo; stat tiles /
  activity bars / word bars / chips re-tinted; contrast: #EDEDEF on #0a0a0c ≥
  4.5:1, #8A8F98 muted ≥ 3:1 (verified values).
- **overlay.py pill**: Tk approximation of the treatment (no gradients/blur in
  Tk): solid `#0a0a0c` fill, `#23263B` outline, corner radius 24 polygon,
  bars `#5E6AD2`, transcribing bars `#3A3F58`, dot `#F25757`, text `#EDEDEF`.
  Geometry/behavior identical.
- **tray_icons.py**: idle/loading `#8A8F98`, transcribing `#5E6AD2`,
  recording `#DC2626`, error `#D97706`. Shape decorations unchanged (state =
  shape AND color preserved).
- **scripts/make_icon.py**: BRAND `#5E6AD2`, disc `#0a0a0c`; regenerate
  `icon.ico`; exe rebuild picks it up.

## Explicitly unchanged

All behavior, DOM structure, element IDs, bridge API, probe markers, tests'
functional assertions, hotkeys, Deep Focus *naming* in old specs (historical).
`README` gains one line ("Cinema Dark UI" mention) only.

## Testing / release

- Suite must stay green untouched EXCEPT `tests/test_icons.py` if it pins hex
  values (it pins distinctness, not hexes — verify) — adjust only if needed.
- Probe unchanged (`navs=8 … ovl=1`, version → 0.8.0).
- Visual sanity: `--settings` manual open + pill lifecycle smoke.
- Standard release train: exe + MSI (serialized; kill app + webviews first),
  upgrade-over-0.7.0 with ProductsEx single-registration + data checks,
  adversarial review pre-push (contrast/regression sweep), push, tag v0.8.0,
  relaunch installed ROAR, MEMORY.md token update.

## Out of scope

Layout/IA changes, new settings, light mode, Tk gradient/blur emulation,
multilingual (SP6).
