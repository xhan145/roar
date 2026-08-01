# ROAR site redesign — "aurora" — Design

**Date:** 2026-08-01 · **Status:** approved (user: "go and build using uupm";
autonomous) · **Repo:** `xhan145/roar` · **File:** `site/index.html` (+
`site/purchase/success.html` reskin to match)

## Direction (user-approved)

A blend of three references on a dark base: Wispr Flow's confident hero +
product-in-action, Linear/Raycast's glass-and-glow developer polish, ProdCom's
bold capability blocks. Audiences called out explicitly: corporate, college
students, programmers. Animated aurora gradient background.

UUPM design-system run (dark developer-tool SaaS): OLED dark ✓, Inter ✓,
minimal glow, visible focus, reduced-motion, 375/768/1024/1440 breakpoints.
Deviation from UUPM's suggested green CTA: the accent stays ROAR lavender
`#A78BFA` — brand continuity with the app and installer outweighs the generic
"run green".

## Design tokens

```
--bg:        #08080D   (near-black, OLED)
--surface:   rgba(255,255,255,.04)  glass card fill
--border:    rgba(255,255,255,.10)  glass hairline
--text:      #EDEDF2
--muted:     #A2A5B4   (≥4.5:1 on bg)
--accent:    #A78BFA   / --accent-2: #7C6CF0 / hot: #E879F9
--accent-ink:#0B0B10
--r: 16px;  glass: backdrop-filter blur(14px)
type: Inter/system stack (NO external fonts); display sizes clamp()-ed
```

## Aurora background

Fixed full-viewport layer behind everything: 3 radial-gradient blobs
(violet/indigo/magenta at 12–20 % alpha, `filter: blur(90px)`), each on its own
26–44 s `transform: translate/scale` keyframe loop (GPU-only properties; the
blur is static, never animated). A subtle dot-grid overlay on top of the blobs
for the developer texture. Blobs strongest behind the hero; a vertical fade
mask dims them over content sections. `prefers-reduced-motion`: animations
off, blobs frozen at their start positions (page still looks designed).
`@supports not (backdrop-filter)` fallback: solid surface fills.

## Page structure

1. **Glass nav** (sticky): logo + ROAR wordmark, Features / Flow / Pricing /
   FAQ anchors, lavender Download CTA. Collapses to logo + Download under
   640 px (anchors hidden — single-page site, scroll still works).
2. **Hero**: version chip (`id="roar-version"` preserved), display headline
   "Speak. It types. Nothing leaves your machine.", sub-line naming the three
   audiences, dual CTA (Download for Windows — free · See pricing), trust
   micro-row (100% local · No account · No subscription). **Product-in-action
   mock**: a glass window frame containing a CSS-recreated pill — animated
   waveform bars + a line of text that types itself (CSS steps() typewriter,
   ~6 s loop) — plus `kbd` hotkey chips. Static full text under
   reduced-motion.
3. **Audience strip** — three glass cards: For engineers / For students /
   For work. Each: icon, 1-line hook, 3 checkmark features drawn from real
   capabilities (Code Mode & OSC; meeting capture & Translate; clean prose &
   local privacy).
4. **Capability triptych** (ProdCom-bold): Dictate / Automate / Route —
   alternating two-column blocks, each with a terminal-style mock
   (`"open terminal" → wt.exe`, route toggles, live transcript lines).
5. **Feature grid**: existing 12 cards, same copy, restyled as glass tiles
   with hover glow + lift.
6. **Privacy** section: same copy, glass panel.
7. **Pricing**: same DOM contract (`.tier` cards, badges, `data-edition`
   buttons, fineprint trust strip, `#checkout-note`) restyled: glass cards,
   Pro card gets the aurora border glow.
8. **FAQ**: same `<details>` content, glass rows.
9. **Footer**: no GitHub (kept), tagline + Pricing/Support.

`site/purchase/success.html`: same tokens + one static aurora blob (no
animation needed), copy unchanged.

## Invariants (pinned by tests — must survive verbatim)

- Pricing card structure split on `<div class="tier`, display names, prices
  Free/$19/$29/$49, badges "Best for most people"/"Best for developers",
  Supporter no-exclusive-features copy, "All v1.x updates included" per paid
  card.
- Trust copy: "One payment. No subscription." + the six promise phrases.
- `data-edition` buttons, `purchase:` config block, `checkoutReady` JS,
  mailto fallback + "Checkout coming soon", `#checkout-note`.
- `id="roar-version"`, stamped `ROAR-Setup-x.y.z.exe` download URL, FAQ
  activation answer, skip link, `#pricing`/`#faq`/`#features` anchors.
- No secrets, no external assets (fonts/scripts/images all inline), page
  self-contained.

## Accessibility & performance budget

Text ≥4.5:1 on the darkest surface behind it (muted #A2A5B4 checked against
#08080D); focus-visible rings 3px accent; touch targets ≥44px; heading order
h1→h2→h3; aurora + typewriter + hover transitions all gated by
reduced-motion; only transform/opacity animate; no horizontal scroll at
375 px; single h1.

## Verification

`tests/test_site_*` green; live checks in the Browser pane at 1280/768/375:
no console errors, no horizontal overflow, buy buttons resolve, contrast
spot-checks via computed styles; ultracode adversarial review workflow
(design vs UUPM checklist, a11y, invariants, copy) before push; Pages deploy
verified live.
