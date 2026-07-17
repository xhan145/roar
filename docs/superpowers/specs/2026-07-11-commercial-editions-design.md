# ROAR Commercial Editions, Licensing & Entitlements

**Date:** 2026-07-11
**Release target:** v0.22.0
**Status:** Approved
**Branch:** `feature/commercial-editions`

## Context — this is NOT greenfield

~two-thirds of the requested architecture shipped in v0.17.0 and is live on `main`
with **37 passing commercial tests**. This spec *completes and wires* it; it does
not rebuild it.

**Already exists (reuse, do not recreate):**
- `entitlements.py` — pure edition model + entitlements (`normalize_edition`,
  `allowed`/`can_use`, `features_for_edition`, `requires_upgrade`,
  `minimum_edition_for`). No I/O, no UI.
- `license.py` — offline Ed25519: `SignatureVerifier` iface,
  `CryptographySignatureVerifier`, `_NullVerifier`, `canonical_bytes`,
  `parse_license`, `validate_license`, `load_license`, `get_current_edition`.
  64 KB cap, verify-before-trust, dev-license rejection when `IS_PRODUCTION`.
- `commercial_config.py` — prices, purchase URLs (placeholders), `IS_PRODUCTION`,
  bundled public key.
- `upgrade_prompts.py` — upgrade copy helper (`all_copy()`), not wired.
- `scripts/dev_generate_license.py`, `scripts/verify_license_file.py`.
- Docs: MONETIZATION, FEATURE_MATRIX, LICENSE_ARCHITECTURE, PRICING,
  REFUND_POLICY, LICENSING, FAQ, PRIVACY_PROMISE, CHECKOUT_SETUP, and
  COMMERCIAL_READINESS_CHECKLIST (in `docs/`).

**The real gaps:**
1. **No `paths.license_path()`** — `get_current_edition()` is called with no path,
   so the edition is **always Core today**. The license is never loaded from disk.
2. No license **service** (import / paste / remove / atomic write / refresh).
3. No **activation UI** (the Settings card is display-only).
4. No **wired upgrade component**.
5. **Gates are OFF** — `entitlements` is referenced by no runtime code.
6. No `docs/commercial/`, no audit doc, no security review, no release checklist.

## Decisions (locked with the user)

| Decision | Resolution |
|---|---|
| **Pricing** | **Keep the repo's $29 / $49 / $99.** The prompt's $19/$29/$49 table is **stale** — the user explicitly set 29/49/99 earlier and a test asserts it. Record the divergence in the audit; change no prices. |
| **Gates** | **ON**, with grandfathering. |
| **Grandfathering** | **One-time legacy grant at upgrade.** |
| **Sequence** | All four sub-projects in order, autonomously. |
| **Unknown features** | **Keep fail-OPEN** (documented divergence from the prompt — see below). |
| **Feature IDs** | **Keep the repo's dotted IDs** (`formatting.smart`), not the prompt's flat IDs. Renaming would churn the module + 37 tests + docs for no benefit. Documented divergence. |

### Documented divergence: unknown features fail OPEN

The prompt requires fail-closed. The repo deliberately fails **open** (allow +
warn), guarded by `KNOWN_FEATURES` + a registration test. We keep fail-open
because its worst case is *a paid feature leaking free* (a revenue bug), whereas
fail-closed's worst case is *accidentally locking a Core feature* — which is
release blocker #1/#2 and breaks the product promise. The guard test prevents
drift either way. Recorded in the audit.

## The grandfathering model (the crux)

**Every paid-target feature already ships free in v0.21.0** (Snippets +
variables, smart/context-aware formatting, advanced cleanup, vocabulary
suggestions, milestones, app profiles, code mode + CODE_SYMBOLS, history
filters, settings import/export). Gating them without grandfathering would take
features from existing users of a public, free app.

**Mechanism** — `legacy_grant.py`:
- On first launch of the gated build, if a **pre-existing install** is detected
  (an existing `config.json` with no `commercial_schema` marker), write a
  **one-time** grant listing exactly the paid-target features that shipped free.
- Then stamp `commercial_schema: 1` into config → **idempotent**; never re-runs.
- **New installs** (no prior config) get **no grant** → gated normally.

**Hard invariants:**
- A grant **never** confers an *edition* — only a set of feature IDs. The signed
  license remains the sole path to an edition (release blocker #7 respected).
- A grant **never** confers a feature that never shipped free. `vocabulary.project`,
  `snippets.developer_packs`, `files.tagging` are **planned** and stay
  Developer-only for everyone.
- Honest limit (documented): the grant is local unsigned state. All local-only
  licensing is honor-based — ROAR has no server by design. The grant cannot
  escalate to an edition, which bounds the blast radius.

**Granted set** (shipped-free paid-target features):
```
snippets.packs, snippets.variables_extended, formatting.smart,
cleanup.advanced, vocabulary.suggestions, milestones.advanced,
history.filters, settings.import_export, profiles.apps,
profiles.per_app_language, code.mode, code.symbols
```

## Architecture

### 1. `entitlements.py` (modify — stays pure)
```python
allowed(feature, edition=None, legacy_grants=frozenset()) -> bool
requires_upgrade(feature, edition=None, legacy_grants=frozenset()) -> bool
features_for_edition(edition=None, legacy_grants=frozenset()) -> set[str]
```
A feature is allowed if: always-free **or** unknown (warn) **or** in the
edition's set **or** in `legacy_grants`. Grants are passed **in** — the module
keeps zero I/O, no UI imports, and full determinism.

### 2. `paths.py` (modify)
```python
def license_path() -> str        # %APPDATA%\ROAR\license.json  (frozen) / repo root (source)
def legacy_grant_path() -> str   # %APPDATA%\ROAR\legacy_grant.json
```
Beside `config.json` (APPDATA), **not** in the LOCALAPPDATA data dir that holds
history/audio — so history clear / privacy reset / audio delete can never touch
them, and normal upgrades preserve them.

### 3. `legacy_grant.py` (new)
```python
GRANTED_FEATURES: frozenset[str]
def is_legacy_install(cfg) -> bool          # pure: no commercial_schema marker
def grant_for(cfg) -> frozenset[str]        # pure decision
def load_grants(path=None) -> frozenset[str]
def ensure_grant(cfg, path=None, log=print) -> frozenset[str]   # one-time write + stamp
```
Pure decision separated from I/O. Never raises; any error → empty grants.

### 4. `license_service.py` (new)
```python
get_status() -> dict     # edition, valid, reason, license_id_redacted, customer_name,
                         # valid_for_major, verified_offline: True
get_active_edition() -> str
import_license(source) -> dict   # source = pasted text or file path
remove_license() -> dict
refresh() -> None
```
- **Atomic import**: reject oversized input **before** parsing → validate → only
  on `valid` write to a temp file in the same dir + `os.replace`. A failed import
  **never** overwrites an existing valid license.
- In-process cache only, invalidated by `import`/`remove`/`refresh`.
- Any error → Core. Never raises.
- Redacts the license ID for display (`ROAR-PRO-XXXX…1234`).

### 5. Gating (modify — backend entry points)
All checks route through `entitlements.allowed(...)`. Gate in the **backend**
(settings bridge + pipeline), never by hiding HTML only.

**Preserve paid config when unlicensed**: e.g. `format_mode == "code"` stays in
config, but the pipeline resolves to `clean` when the entitlement is absent.
Restoring a license reactivates it with no reconfiguration.

### 6. Upgrade component (modify `upgrade_prompts.py` + settings)
One reusable component taking `(feature_name, required_edition, description,
purchase_url)`. Shown **only** on intentional paid-feature interaction. Never at
startup, never during dictation, never blocks Settings/privacy/deletion. URLs come
from `commercial_config` constants — never hard-coded per call site.

### 7. Config (modify `config.py`)
```json
{"license_notifications": true,
 "purchase_urls": {"pro": "...", "developer": "...", "supporter": "..."},
 "commercial_schema": 1}
```
Old configs load unchanged; missing keys get defaults; unknown keys never crash.
The **signed license is authoritative** — no manually-editable trusted edition key.

## Testing (on top of the existing 37)

- **Legacy grant**: legacy install → granted; fresh install → no grant;
  idempotent (second run doesn't re-grant); never grants an edition; never grants
  a never-shipped feature.
- **Entitlements**: every Core feature free in every edition; Pro ⊂ Developer ⊂
  Supporter; Developer-only unavailable in Pro; grants re-allow; privacy/history-
  delete/audio-delete free in **every** edition (regression).
- **License service**: missing → Core; corrupt → Core; import refreshes edition;
  remove → Core; **failed import preserves an existing valid license**; oversized
  paste rejected; import is atomic; license survives config migration.
- **Gates**: each gated feature blocked in Core, allowed with license or grant;
  paid config preserved when unlicensed.
- **UI smoke**: License section renders with no license and with each edition;
  invalid/oversized paste doesn't crash; buttons use configured URLs; **no
  upgrade prompt at startup**; privacy + dictation reachable in Core.
- **Packaging**: public key present; **no private key**; dev fixtures excluded;
  purchase URLs present; production build rejects dev licenses.
- **Prohibited language**: shipping copy contains no "subscription", "lifetime",
  "trial expired", "monthly plan", "annual plan".

## Docs

Create `docs/commercial/` for the **new** docs: **REPOSITORY_COMMERCIAL_AUDIT.md**
(incl. all divergences), **COMMERCIAL_SECURITY_REVIEW.md**, **RELEASE_CHECKLIST.md**.

**Do NOT move the existing commercial docs.** MONETIZATION / FEATURE_MATRIX /
LICENSE_ARCHITECTURE / PRICING / REFUND_POLICY stay at `docs/*.md`: they are
referenced by `tests/test_commercial_privacy.py`, `README.md`, `AGENTS.md`,
`ROADMAP-14DAY.md`, the `entitlements.py` docstring, and prior specs — moving
them would break a test and six references for no benefit. The prompt permits
"adapting paths to repository conventions", and flat `docs/` **is** this repo's
convention. The audit records the layout. FEATURE_MATRIX (in place) records the
grandfathering decision and marks never-shipped features **planned**.

## Sub-projects (sequenced; full suite after each)

1. **Audit + docs** — audit doc, `docs/commercial/` reorg, matrix + divergences.
2. **License service + activation UI** — `paths`, `license_service.py`, Settings
   License section (paste / import / remove / buy). No gating risk.
3. **Legacy grant + gates + upgrade component** — the risky product change.
4. **Security review + packaging checks** — security doc + packaging tests.

## Constraints (verbatim, non-negotiable)

- Core dictation, offline use, privacy controls, history/audio deletion, and
  retention controls are **never** gated, in any edition.
- Licensing never reads transcript/audio/clipboard/history/vocabulary/snippet
  content or window titles, and never touches the network.
- No subscription, no account, no launch nag, no dictation interruption, no
  recurring server check, no countdown/scarcity/"trial expired".
- Missing/malformed/invalid licenses → Core, never a crash.
- Private signing key never in repo or installer; dev licenses rejected in
  production builds.
- Existing user data + settings survive upgrades; history/privacy/audio clears
  never delete the license.
