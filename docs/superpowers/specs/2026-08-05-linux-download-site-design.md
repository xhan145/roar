# ROAR Windows + Linux Download Experience Design

**Date:** 2026-08-05  
**Status:** approved by the execution prompt  
**Branch:** `codex/linux-download-site`

## Goal

Give `getroar.tech` an explicit, trustworthy Windows Stable and Linux Preview
download experience backed by release metadata that cannot drift from GitHub.
Prepare a reproducible Linux package and release workflow without publishing a
release, tagging, merging, or deploying automatically.

ROAR remains local-first: no account, cloud transcription, subscription, app
telemetry, recurring licence check, download tracking, or operating-system
fingerprinting is introduced.

## Repository and release audit

- Audit base: `295f1d2fdd04dc54095c9b4568e1fbef150ea803` on `main`.
- Work began in an isolated linked worktree on
  `codex/linux-download-site`. The first branch commit only ignores the local
  `.worktrees/` directory.
- `AGENTS.md` is present; `CLAUDE.md` is not present.
- Canonical desktop version: `paths.APP_VERSION == "0.35.2"`.
- Live latest release, queried from GitHub on 2026-08-06:
  - tag `v0.35.2`, published `2026-08-03T19:20:31Z`;
  - asset `ROAR-Setup-0.35.2.exe`;
  - 908,794,228 bytes;
  - SHA-256
    `ed7180f00bd4a3c923c97eeb8b84c43f263b0fced9aa38d903489eed4ad768e3`.
  This exactly matches the prompt's audit reference.
- GitHub has no published Linux release asset. Remote branches contain no
  additional Linux packaging branch.
- `VERSIONS.md` had stale published metadata (`v0.35.0`) and records local
  absolute source paths. Running `scripts/roar_versions.py --check --github`
  confirms desktop source/release parity but rewrites that local path.
- The Pages workflow uploads `site/` without a build step. It runs only for
  `site/**` changes or manual dispatch, so releases cannot refresh site metadata.
- The public site is one static HTML file with inline CSS/JavaScript plus a
  script-free purchase-success page. It hardcodes the versioned Windows asset in
  both pages, calls a roughly 909 MB installer “small,” and keeps stale manual
  checkout fallback markup even though every paid edition has a payment link.
- Site baseline: 32 focused site tests pass.
- Full repository baseline using the documented existing virtual environment:
  1,039 passed, 3 skipped, and the single documented environmental failure in
  `tests/test_smoke.py` because another ROAR process holds the singleton lock.
- Version parity baseline passes for ROAR Desktop; the separately versioned
  Android checkout is absent from this worktree.
- Existing build commands:
  - Windows: `venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm`,
    `bash scripts/build_msi.sh`, then `bash scripts/build_setup.sh`.
  - Linux source setup: `bash linux/setup.sh`; launcher: `linux/roar`.
  - Linux package recipe: `bash linux/build_appimage.sh`.
  - Site: no current build; Pages uploads `site/` directly.

### Linux readiness classification

**3. Partially implemented.**

Evidence for runtime progress:

- Linux seams exist for XDG paths, autostart, focused-window discovery, global
  hotkeys, injection, singleton locking, and acceleration selection.
- 37 Linux-focused portable tests pass on Windows.
- `requirements-linux.txt`, `linux/setup.sh`, a launcher, desktop entry, docs,
  and an AppImage shell recipe exist.

Evidence against “functional and packaged” or “functional but not packaged”:

- `docs/LINUX.md` calls the AppImage recipe unverified and source-only.
- No Linux CI job or published Linux asset exists.
- `linux/build_appimage.sh` invokes ad-hoc PyInstaller arguments instead of a
  Linux spec and therefore omits packaging data/hidden-import decisions made in
  `roar.spec`.
- The recipe does not verify the frozen application, the AppDir, the AppImage,
  checksums, or release naming; it installs an unpinned build tool at build time.
- The audit found no repository evidence of a real microphone, hotkey, injection,
  settings, or packaged-app smoke run on Linux. Existing “verified” module
  comments are not sufficient evidence.

The site must therefore remain honest: Linux is “Preview,” automated checks are
stated precisely, and no availability CTA appears until GitHub contains a
matching, checksummed Linux release asset.

## Approaches considered

### A. Keep hardcoded links and manually edit the site per release

Smallest code change, but it preserves the exact version-drift failure this task
must remove and makes Windows and Linux channels difficult to coordinate.

### B. Build-time release manifest plus a tested Linux release workflow

**Adopted.** A small Python generator consumes GitHub release JSON, selects the
Windows stable and Linux preview channels, validates asset names/digests, and
writes one schema-validated static manifest. Pages runs it before artifact
upload and also refreshes on release events. A Linux workflow builds and tests
the package, produces SHA-256 data, and can upload only to an already-created
release when a human explicitly supplies release authority.

This keeps the site static, avoids client-side GitHub API calls and OS detection,
and makes absence or malformed metadata a visible unavailable state rather than
a guessed link.

### C. Query GitHub from browser JavaScript on every visit

Rejected. It adds runtime failure/rate-limit behavior, weakens the static site's
determinism, exposes more network activity to visitors, and still needs complex
fallback logic. It is unnecessary when Pages can generate the data once.

## Release metadata architecture

`scripts/generate_site_release_manifest.py` owns channel selection and output.
Its testable core accepts a release-list document; its CLI can read a fixture or
query GitHub with an explicit repository and token. Network access is confined
to build/release workflows, never the desktop app or site visitor.

The checked-in `site/data/releases.json` is a deployable snapshot. Pages
regenerates it immediately before upload. `site/data/releases.schema.json`
documents and validates schema version 1.

Channel rules:

- Windows Stable: newest published, non-draft, non-prerelease release with one
  asset matching `ROAR-Setup-<version>.exe`, an HTTPS GitHub download URL, a
  positive size, and a GitHub SHA-256 digest.
- Linux Preview: newest published, non-draft prerelease with one asset named
  `ROAR-Linux-<app-version>-x86_64.AppImage` and the same metadata guarantees.
- If a channel has no valid release, emit `available: false` with no invented
  asset metadata. Invalid or ambiguous matching assets fail generation.
- `generated_at` is injected for production and fixed in tests for deterministic
  snapshots.
- Windows and Linux are independent channels and may point at different releases
  or versions.

The site fetches only its same-origin manifest. Static fallback copy remains
useful with JavaScript disabled. A failed fetch or invalid record preserves the
card, disables its download action, and announces a concise recovery message.

## Linux package and release plumbing

Add a Linux-specific PyInstaller spec and deterministic build script rather than
branching the application. The script:

1. requires a prepared Linux virtual environment and pinned build dependencies;
2. derives the application version from `paths.APP_VERSION`;
3. produces a canonical x86_64 AppDir and AppImage name;
4. includes the same required application assets, licences, and web UIs as the
   Windows package while excluding Windows-only integrations;
5. runs import and frozen `--smoke` checks under Xvfb;
6. extracts and smoke-checks the finished AppImage without requiring FUSE;
7. writes a SHA-256 sidecar and build metadata.

The GitHub Actions workflow uses Ubuntu 24.04 x86_64, runs Linux-focused tests,
builds the package, verifies it, and uploads a workflow artifact. A manual input
may attach the already-verified files to an existing draft/prerelease; the
workflow never creates or publishes a release and never tags or deploys.

Runtime claims remain narrow. Automated packaged launch/import checks support
the package and architecture claims. The site and Linux documentation label the
channel Preview and distinguish automated package verification from the manual
microphone/global-hotkey/cross-app-injection checks still required on real X11.

## Website information architecture

Preserve the current hero, logo, pricing, privacy, and feature story. Add one
focused download section directly after the hero CTA and route nav/hero/Core
download links to that section. The section contains two explicit cards:

1. **Windows — Stable**: primary card and CTA.
2. **Linux — Preview**: secondary card with a persistent Preview badge and a
   visible limitations link.

No platform is preselected. No user-agent or operating-system fingerprinting is
performed. Each card shows, in descending prominence:

- platform and status badge;
- availability and one-sentence support summary;
- download action or unavailable state;
- version, release date, package type, architecture, and exact human-readable
  size;
- release-notes link;
- abbreviated SHA-256 with a 44-by-44 copy control and a visible success/failure
  status;
- compact installation instructions disclosed beneath the metadata.

The purchase-success page links back to `index.html#download` instead of embedding
a versioned binary URL. It stays script-free so checkout parameters can never be
read; the main page owns the current download actions.

## Adopted UI/UX decisions

The UI/UX pass recommended a hero-centric, high-contrast, restrained design,
explicit system status, mobile card layouts, visible focus, 44 px targets,
text-plus-icon status communication, and error recovery. ROAR's existing palette,
system font stack, logo, and static implementation override suggested replacement
colors, remote Roboto, GSAP, or a framework.

- Retain `#08080D`, near-white text, lavender `#A78BFA`/`#7C6CF0`, and current
  logo. Add semantic preview/warning and unavailable surface tokens only.
- Use Material Design 3-inspired tonal surfaces, 16 px corners, compact status
  chips, and elevation through borders/shadows—not a generic SaaS rebuild.
- Desktop: two balanced columns; 768 px and below: one column; 375 px: full-width
  actions and wrapping metadata with no horizontal scroll.
- Metadata uses a definition-list/card pattern rather than a wide table.
- Status never relies on color alone. Preview and unavailable states include
  visible text and inline SVG icons.
- Copy feedback uses a polite `aria-live` region and restores the original label.
- Focus remains a 3 px lavender ring. Links are underlined where they are not
  button-shaped. Targets are at least 44 px where practical.
- Motion is limited to existing 150–300 ms micro-interactions. Metadata loading
  adds no decorative motion; `prefers-reduced-motion` continues to disable
  nonessential animation.
- The current animated aurora is retained because this is a targeted download
  enhancement, but no new blobs, gradients, glass layers, imagery, or animation
  are added.

Detailed retained/new tokens, component anatomy, responsive rules,
accessibility rules, motion rules, and do/do-not examples will live in
`site/DESIGN.md` beside the implementation.

## Error handling

- Generator: reject malformed JSON, missing required asset fields, ambiguous
  matches, non-GitHub/non-HTTPS URLs, invalid digests, and unsupported schema
  changes with actionable messages and a nonzero exit.
- Pages: generation failure blocks deployment; it never publishes stale guessed
  links.
- Site: fetch/parse failure shows both cards with safe unavailable messaging and
  a release-page recovery link. It never falls back to a versioned guess.
- Clipboard: prefer the async Clipboard API; on denial or unsupported contexts,
  select the checksum text and announce that manual copy is available.
- Linux workflow: any unit, import, build, frozen smoke, extracted AppImage smoke,
  checksum, or asset-name failure prevents upload.

## Testing and review

- Unit tests for release selection, independent channels, malformed/ambiguous
  data, missing Linux releases, digest normalization, sizes, deterministic
  timestamps, and schema-shaped output.
- Static site tests for no hardcoded versioned asset URLs, no OS detection, no
  download tracking, correct platform/status/metadata anatomy, stale-copy
  removal, script-free success page, and accessibility markers.
- JavaScript behavior tests or a browser fixture for manifest success, unavailable
  and network-error states, checksum copying, keyboard operation, and no console
  errors.
- Linux unit/import tests, shell syntax checks, PyInstaller build, frozen smoke,
  AppImage extraction/smoke, checksum verification, and workflow contract tests.
- Existing Windows, licensing/privacy, version-parity, checkout, and full test
  suites remain green except the documented live-instance smoke condition.
- Responsive browser verification at 375, 768, 1024, and 1440 px, including
  keyboard focus, reduced motion, and manifest error state.
- Scoped task reviews followed by one whole-branch review before handoff.

## Release and deployment boundary

This branch may build and verify local/workflow artifacts and make atomic commits.
It does not tag, create or publish a GitHub release, push release assets, merge to
`main`, or deploy Pages. Those remain explicit human release actions.
