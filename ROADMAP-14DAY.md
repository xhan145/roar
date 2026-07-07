# ROAR — 14-Day Commercial Hardening Roadmap

Turn the existing commercial *scaffold* (offline Ed25519 licensing, entitlements,
docs — all present on `main`, gates OFF) into a launch-ready one-time-payment
product **without** compromising the privacy promise. Docs-first; code follows in
small, reviewable steps.

## Non-negotiables (never violated by any day below)
- Local-first Windows dictation. No cloud transcription. No telemetry. No account.
- **One-time payment only.** No subscription.
- **Core dictation is free.** Privacy controls, history deletion, audio deletion,
  offline use, and basic local dictation are **never paid-only**.
- Paid gates unlock **workflow power only**.

## Pricing (finalized)
| Edition | Price | Positioning |
|---|---|---|
| ROAR Core | Free | Private local dictation |
| ROAR Pro | **$29 one-time** | Smarter local dictation |
| ROAR Developer Pack | **$49 one-time** | Code-aware voice layer |
| Supporter License | **$99 one-time** | Everything in Developer, supports development |

> **Code sync — DONE:** `commercial_config.py` `*_PRICE_USD` constants and
> `tests/test_commercial_config.py` are now at 29/49/99, matching the docs. The
> derived surfaces (`settings_ui.license_info`, `upgrade_prompts`) update
> automatically. Gates remain OFF — no behavior change beyond displayed prices.

## Day-by-day

**Day 1 — Pricing + entity kickoff.**
- ~~Bump `commercial_config.py` prices to 29/49/99 and update `test_commercial_config.py`.~~ **DONE.**
- Start entity/IP work per [docs/FOUNDER_COMPANY_READINESS.md](docs/FOUNDER_COMPANY_READINESS.md)
  (entity choice, founder agreement, IP assignment, company-owned repo/domain/payment).

**Day 2-3 — Production licensing keys.**
- Generate a **production** Ed25519 keypair; private key into a secret manager
  (never the repo). Swap the dev public key in `commercial_config.LICENSE_PUBLIC_KEY_PEM`.
- Flip `IS_PRODUCTION=True` in the release build; confirm dev-signed licenses are
  rejected. See [docs/LICENSE_ARCHITECTURE.md](docs/LICENSE_ARCHITECTURE.md).

**Day 3-4 — Checkout (manual first).**
- Pick a processor (Lemon Squeezy recommended — merchant of record handles VAT).
  Manual license fulfillment first via `scripts/dev_generate_license.py` with the
  production key. See [docs/CHECKOUT_SETUP.md](docs/CHECKOUT_SETUP.md).

**Day 4-6 — Paid beta.**
- Small cohort, hand-issued licenses. Prove the full path (buy → email → import →
  edition unlocks offline). Collect refund/support signal against
  [docs/REFUND_POLICY.md](docs/REFUND_POLICY.md).

**Day 6-9 — Gate wiring (careful).**
- Wire `entitlements.py` to a FEW paid workflow features (see FEATURE_MATRIX).
  **Grandfather existing users**; keep Core + all privacy/delete/offline free.
  Only after offline licensing is proven end-to-end.

**Day 9-11 — License UX.**
- Complete the calm Settings license panel + tasteful upgrade prompts (intentional
  clicks only; never on launch, never during dictation; no dark patterns).

**Day 11-13 — Release gates (below) + RC.**
- Run the full testing-gate checklist. Tag `v1.0.0-rc1`.

**Day 13-14 — Launch.**
- Fix RC findings; tag `v1.0.0`; publish installer + pricing page.

## Testing gates before release (all must pass)
- `pytest` fully green (or documented environmental-only failures).
- Settings + tray smoke; installer smoke (fresh/upgrade/uninstall/reinstall).
- **Core runs with no license**; missing/invalid license → Core, not a crash.
- License validation works **offline**; dev-signed license **rejected** in prod.
- Privacy controls + history/audio deletion confirmed **free** in every edition.
- Copy hygiene (no subscription/account/cloud claims except the reassurances).
- **No network in the transcription path**; no transcript in logs/status/diagnostics.
- Version parity (`scripts/roar_versions.py --check`) clean.

## Branch strategy
Two agents, isolated branches, small PRs, merge to `main`. Full rules in
[AGENTS.md](AGENTS.md).
