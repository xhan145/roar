# ROAR — Commercial Security & Privacy Review

**Date:** 2026-07-11 · **Scope:** v0.22.0 commercial layer
(`entitlements.py`, `license.py`, `license_service.py`, `legacy_grant.py`,
`access.py`, `commercial_config.py`, `upgrade_prompts.py`, the Settings License
section, and packaging)

Every "PASS" below was **verified by a check that was actually run** — a test, a
grep over tracked files, or a hand-trace — not asserted from intent. Where the
guarantee is weaker than it looks, it says so.

## Verdict

No release blockers found in the commercial layer. Two accepted, documented
limitations (§ "Honest limits").

## Findings

| # | Risk | Status | Evidence |
|---|---|---|---|
| 1 | Embedded private key | **PASS** | `git grep` for all PRIVATE KEY markers over tracked files → none. Automated: `test_no_private_key_anywhere_in_the_source_tree` scans the whole source tree every run |
| 2 | Test/dev key accepted in production | **PASS** | `validate_license(..., is_production=True)` returns `dev_rejected` for an `env=dev` payload. Automated: `test_production_build_rejects_a_dev_signed_license` proves it is accepted in a dev build and refused in a production one |
| 3 | Signature bypass | **PASS** | Ed25519 via `cryptography`; no hand-rolled comparison. `_NullVerifier` fails closed when no backend exists. Wrong-key licence rejected (`test_a_license_signed_by_the_wrong_key_is_rejected`) |
| 4 | Unsigned edition trusted | **PASS** | `validate_license` verifies the signature **before** reading any field; an unsigned payload returns `unsigned`. Tests: `test_failed_import_of_unsigned_preserves_existing`, `test_tampered_payload_is_core` (edition escalated without re-signing → `bad_signature`, Core) |
| 5 | Unsafe JSON parsing | **PASS** | `json.loads` only, inside `try/except`, on a size-capped string. No `eval`, no pickle, no custom decoder |
| 6 | Oversized payload | **PASS** | 64 KB cap enforced **before** parsing in both `license.parse_license`/`load_license` and `license_service._coerce_source`, plus a bridge-level check. Tests: `test_oversized_license_is_core`, `test_oversized_paste_rejected_before_parsing` |
| 7 | Deeply nested / hostile payload | **PASS** | Bounded by the 64 KB cap; only scalar fields are read, and only after signature verification. Unknown fields are ignored |
| 8 | Path traversal / arbitrary file import | **PASS (bounded)** | Import treats input as a path **only if `os.path.isfile()`** is true, so a paste that merely looks path-ish is never opened. The user chooses the file via the OS dialog; ROAR only **reads** it. It never writes outside `license_path()` |
| 9 | Insecure temp files | **PASS** | `tempfile.mkstemp` (0600, unpredictable name) **in the destination directory**, then `os.replace`. No world-writable temp, no predictable name. `test_import_leaves_no_temp_files` |
| 10 | Non-atomic write / license corruption | **PASS** | Validate → temp → `os.replace` (atomic on Windows + POSIX). A failed import provably leaves an existing valid licence untouched (`test_failed_import_preserves_existing_valid_license`) |
| 11 | Licensing reads transcripts | **PASS** | AST import scan over every commercial module (`test_commercial_modules_import_no_user_data_or_network`) forbids `history`/`audio`/`transcriber`/`recorder`/`clipboard`. Extended this release to cover `license_service.py` and `legacy_grant.py` |
| 12 | Licensing reads audio / clipboard / history / vocabulary | **PASS** | Same guard as #11 |
| 13 | Accidental network call | **PASS** | Same guard forbids `socket`/`urllib`/`requests`/`http` in commercial modules. `test_network_hygiene` independently caps the whole app's outbound calls to the click-only update check + the opt-in GPU download |
| 14 | Recurring / online licence check | **PASS** | Validation is pure local file + in-process crypto. No network code path exists to call |
| 15 | Full licence leaked in logs / diagnostics | **PASS** | Only `redact_license_id()` output (`ROAR…1234`) is surfaced; the raw payload is never logged. `diagnostics.redact_diagnostics` drops `signature`/`email`/transcript-like keys (`test_redact_diagnostics_removes_transcript_like_fields`). `test_redact_license_id` |
| 16 | Customer info leakage | **PASS** | `customer_name` is displayed **only after** the signature verifies, and only in the local Settings window. Untrusted payloads surface no fields at all (`test_tampered_payload_is_core` asserts `license_id == ""`) |
| 17 | Upgrade bypass | **PASS (by design)** | Gates live at backend entry points (`app._effective_formatting`, `_rebuild_hotwords`), not in markup. The UI's `feature_access()` only *explains* a lock |
| 18 | UI-only enforcement | **PASS** | Hiding a control changes nothing: the pipeline resolves `code`→`clean` and withholds snippets/profiles server-side regardless of what the UI shows |
| 19 | Env-var / debug backdoor | **PASS** | No `getenv`/`environ` read in any commercial module (grep verified; the only match is a comment) |
| 20 | Installer removes licences | **PASS** | Licence lives at `%APPDATA%\ROAR\license.json`; the MSI replaces program files only. History clear / privacy reset / audio delete operate on `%LOCALAPPDATA%\ROAR` and cannot reach it (`test_remove_returns_core_and_keeps_user_content`) |
| 21 | Installer ships secrets / accepted sample licence | **PASS** | No private key and no `license.json` tracked (`test_no_installed_license_or_grant_is_committed`); `roar.spec` bundles no dev tooling (`test_pyinstaller_spec_does_not_bundle_dev_tooling_or_keys`); dev scripts are imported by no app module (`test_dev_scripts_not_imported_by_any_app_module`) |
| 22 | Malformed licence crashes the app | **PASS** | Every entry point is `try/except` → Core. Startup grant is wrapped so commercial plumbing can never break launch. Tests cover empty/garbage/truncated/oversized/wrong-key/wrong-major/unsupported-edition |
| 23 | Core promises silently gated | **PASS** | `ALWAYS_FREE` is checked first in `allowed()` and can never be overridden by edition or grant. Regression: `test_core_features_free_in_every_edition_regardless_of_grants`, `test_core_keeps_every_promise_with_no_license_and_no_grant` |
| 24 | Unsigned value unlocks an **edition** | **PASS** | The legacy grant is feature IDs only; `test_grant_never_names_an_edition` and `test_grant_does_not_make_the_user_pro` pin it. Only a verified signature sets an edition |
| 25 | Hand-edited grant escalates privileges | **PASS (bounded)** | `load_grants` intersects the file against `GRANTED_FEATURES`, so junk/never-shipped entries are dropped (`test_hand_edited_grant_cannot_widen_beyond_shipped_free_set`) |

## Honest limits (accepted, not hidden)

1. **The legacy grant is local unsigned state.** A user could hand-create
   `legacy_grant.json` to re-enable the features that shipped free. This is
   accepted because: (a) those features **were** free in v0.21.0 — the grant
   restores nothing that wasn't already public; (b) the grant can never confer an
   edition, so never-shipped Developer features stay locked; (c) the file is
   intersected against a fixed allow-list. The blast radius is exactly "what a
   v0.21.0 user already had".
2. **Local-only licensing is honor-based.** ROAR has **no licence server by
   design** (no account, no recurring check). Any client-side check can be
   patched by a determined user. The design goal is an honest, frictionless
   purchase for people who want to pay — not DRM. Adding a server would break the
   product's central privacy promise and is explicitly out of scope.
3. **Unknown features fail OPEN** (documented divergence). An unregistered
   feature is allowed + warned rather than blocked, because fail-closed's failure
   mode is accidentally locking a **Core** feature (a release blocker), while
   fail-open's is a paid feature leaking free (a revenue bug). `KNOWN_FEATURES` +
   `test_referenced_features_are_registered` prevent drift.

## Redaction policy

- Licence IDs: `redact_license_id()` → `ROAR…1234`. Never log a full ID.
- Never log a licence payload, signature, or customer email.
- `diagnostics.redact_diagnostics` drops transcript/clipboard/signature/email
  keys before anything is copyable.

## Before charging real money

These are **not** code blockers, but must be done before a paid release (see
`docs/commercial/RELEASE_CHECKLIST.md`):

1. Replace the **dev** public key in `commercial_config.LICENSE_PUBLIC_KEY_PEM`
   with the real one and set `IS_PRODUCTION = True`.
2. Replace the placeholder purchase URLs (`https://example.com/roar/*`) and
   `SUPPORT_EMAIL`.
3. Keep the production private key **offline**, never in the repo, CI, or the
   installer; sign licences in the fulfilment service only.
