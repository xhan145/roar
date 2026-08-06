# Task 5 report — verified Windows and Linux download cards

## Scope

Implemented the Task 5 static download experience only: `site/index.html`, the same-origin manifest controller and Node tests, the Linux Preview guide, the design record, and site-contract tests. `VERSIONS.md`, packaging, workflows, and purchase-success were not edited.

## RED evidence

1. Added `tests/test_site_downloads.py` before implementation. Running
   `C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest tests/test_site_downloads.py -v`
   produced five expected failures: no `#download` section/cards, CTA hrefs were `#`, no module, and the stale installer/checkout copy was still present.
2. Added `site/downloads.test.mjs` before `site/downloads.mjs`. Running
   `node --test site/downloads.test.mjs` failed with `ERR_MODULE_NOT_FOUND` for the missing module.
3. The first implementation run left the digest abbreviation one character too long; the Node test failed with the expected assertion. The implementation was reduced to the tested abbreviation.
4. Added a clipboard-unavailable test before `writeChecksum`; Node failed because the expected export did not exist. The implementation now fails closed and selects the digest manually in the DOM fallback.
5. Added the non-UTC release-date test before validation; it failed because `parseManifest` accepted the malformed record. Validation now rejects malformed available records before rendering.

## GREEN evidence

- `node --test site/downloads.test.mjs` — 9 passed.
- `C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest -p no:cacheprovider` over every `tests/test_site_*.py` file — 37 passed.
- `git diff --check` — passed.

The first combined site-test invocation executed all 32 then hit an `OSError: [Errno 28] No space left on device` while pytest wrote its cache. The scoped, regenerable `.pytest_cache` was removed, recovering space; the final no-cacheprovider run is the authoritative green result above.

## Behavior delivered

- Two equal-weight cards always show explicit Windows Stable and Linux Preview choices. No user-agent or platform detection/preselection exists.
- Only `data/releases.json` is fetched. Parsing requires schema version 1, `xhan145/roar`, both records, HTTPS GitHub release URLs, dates, exact checksums, and positive sizes.
- Bad/failing metadata disables both actions and exposes a repository Releases recovery link; it never guesses a package URL.
- Windows exact release details originate exclusively from the manifest. Linux remains unavailable unless a valid Linux record is present.
- Clipboard feedback is initiated only by the copy control. Full digests remain available for copying and manual selection; each card has a polite live status.
- Existing CTA routes now point to the safe `#download` anchor before JavaScript runs. Checkout/pricing behavior remains unchanged aside from removed stale rendered fallback copy.
- Linux documentation accurately limits the Preview to x86_64/X11, notes Ubuntu 24.04 automated smoke scope and real-device gates, and makes no GPU or Wayland claim.

## Self-review

Reviewed the scoped diff for the product constraints. There are no release-download URLs in static markup, no download event/beacon/analytics path, no external assets/frameworks, and no cloud/account/subscription/app-telemetry implication. The module only contacts its same-origin manifest; consent-gated GA remains the sole optional website analytics seam. CSS retains ROAR tokens/system fonts and adds the documented semantic states, visible focus, 44 px controls, and responsive 375/768/1024/1440 rules.

Browser/server visual verification is intentionally left for Task 7, per the Task 5 handoff boundary.

## Fix round 1 — reviewer regressions

### RED evidence

1. Added Node regressions for a normalized-invalid `2026-02-31T19:20:31Z` date and platform-swapped Windows/Linux records. Once the DOM helper was introduced, these tests showed the previous parser accepted contracts outside the schema/generator platform identity rules.
2. Added an exact-schema-field Node regression. It failed because the former parser ignored an added manifest field.
3. Added a minimal-fake DOM regression for the clipboard failure path. The initial Node run failed because `manuallySelectChecksum` did not exist; the test requires selected text to become the full 64-character digest and the polite status to exactly state manual-copy recovery.
4. Added a parsed HTML no-JavaScript recovery-link test. It failed with `StopIteration` because no `<noscript>` Releases route existed.

### GREEN evidence

- `node --test site/downloads.test.mjs` — 13 passed.
- `C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest -p no:cacheprovider` over every `tests/test_site_*.py` file — 38 passed.
- `git diff --check` — passed.

### Fixes

- `parseManifest` now requires the schema's exact top-level/platform keys, a valid UTC calendar date, exact unavailable shapes, and exact Windows Stable/x86_64/exe or Linux Preview/x86_64/AppImage naming, package, channel, and release-asset URL contracts.
- Clipboard fallback changes the checksum node to the full digest before selecting it, while normal successful rendering remains abbreviated and keeps the full digest in accessible metadata.
- A visible no-JavaScript message links directly to the repository Releases page; JavaScript behavior remains unchanged.
