# ROAR — Commercial Release Checklist

Gate for any release that charges money. Anything unticked in **Blockers** stops
the release. See `COMMERCIAL_SECURITY_REVIEW.md` for evidence and
`REPOSITORY_COMMERCIAL_AUDIT.md` for the divergences from the original brief.

## Status at v0.22.0

The commercial **architecture** is complete and enforced; the **commercials
themselves are still placeholders**. ROAR is not ready to take money until
§ "Before charging" is done.

## Blockers (must all be true)

| ✔ | Blocker | v0.22.0 |
|---|---|---|
| ✅ | ROAR launches with no licence | Core is the default; startup grant is exception-wrapped |
| ✅ | Core dictation works with no licence | `ALWAYS_FREE` checked first, in every edition |
| ✅ | Works offline with no licence | No network in any licensing path |
| ✅ | Privacy controls work in Core | Never gated, any edition |
| ✅ | History deletion works in Core | Never gated |
| ✅ | Audio deletion works in Core | Never gated |
| ✅ | Missing licence → Core | `reason="missing"` |
| ✅ | Invalid licence → Core, no crash | Every entry point try/except → Core |
| ✅ | Valid Pro unlocks Pro | `test_prompt_for_pro_feature`, entitlement tests |
| ✅ | Valid Developer unlocks Pro + Developer | `test_developer_includes_pro` |
| ✅ | Valid Supporter unlocks Developer | `test_supporter_includes_developer` |
| ✅ | Validation needs no internet | Local file + local crypto only |
| ✅ | Validation reads no user content | AST import guard |
| ✅ | No private key in repo/installer | Tree scan test |
| ✅ | Dev licences rejected in production builds | `test_production_build_rejects_a_dev_signed_license` |
| ✅ | Licence import is atomic | temp + `os.replace` |
| ✅ | Failed import preserves a valid licence | `test_failed_import_preserves_existing_valid_license` |
| ✅ | Upgrade prompts only on intentional interaction | `prompt_for` returns None for free features; no auto-open |
| ✅ | No upgrade prompt at startup/during dictation | `test_no_upgrade_prompt_opens_at_startup` |
| ✅ | Existing config keeps loading | `test_old_config_still_loads_and_gets_commercial_defaults` |
| ✅ | Upgrades preserve the licence | `%APPDATA%` + MSI replaces program files only |
| ✅ | History clear doesn't remove the licence | Separate path; `test_remove_returns_core_and_keeps_user_content` |
| ✅ | Paid settings preserved on a trip to Core | `test_unentitled_code_mode_steps_down_without_touching_config` |
| ✅ | Docs match behaviour | Never-shipped features marked **planned**, never claimed |
| ✅ | Automated tests pass | **456 green** |
| ✅ | Packaging checks pass | `tests/test_commercial_packaging.py` |

## Before charging (open — these are the real remaining work)

- [ ] **Replace the dev public key** in `commercial_config.LICENSE_PUBLIC_KEY_PEM`
      with the production key, and set `IS_PRODUCTION = True`. Until then a
      dev-signed licence is accepted (by design, for local end-to-end testing).
- [ ] **Replace placeholder purchase URLs** — `https://example.com/roar/{pro,
      developer,supporter}` — and `SUPPORT_EMAIL` (`support@example.com`).
      Marked `# TODO before launch` in `commercial_config.py`.
- [ ] Stand up fulfilment that signs licences with the **offline** private key.
      It must never receive transcript/audio/usage data — only an order.
- [ ] Decide the refund window and reflect it in `docs/REFUND_POLICY.md`.
- [ ] Verify the purchase → licence-email → import flow end-to-end once.

## Release build (order matters)

`build_msi.sh` does **not** run PyInstaller. Skipping step 1 ships **old code
under a new version stamp** (this actually happened during v0.21.0):

1. `venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm`
2. `bash scripts/build_msi.sh`
3. `bash scripts/build_setup.sh`

Verify before shipping:
- `dist/ROAR/ROAR.exe` mtime is from **this** build
- version stamp matches `paths.APP_VERSION`
- `dist/ROAR-Setup-<version>.exe` exists and is signed as expected
- disk: the 7z step needs ~5–6 GB free; delete the superseded
  `dist/ROAR-Setup-*.exe` first

## Never (product invariants)

Charging for any of these is a release blocker, not a decision:
basic dictation · offline use · privacy controls · history deletion · audio
deletion · retention toggles. Subscriptions, mandatory accounts, launch nags,
dictation interruption, recurring server checks, countdowns/"trial expired".
