# ROAR Windows + Linux Download Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a review-ready static Windows Stable and Linux Preview download experience whose metadata is generated from verified GitHub release assets, plus reproducible Linux AppImage build and release plumbing that does not publish automatically.

**Architecture:** A dependency-free Python generator converts GitHub Releases JSON into one schema-versioned static manifest with independent platform channels. The static site renders two explicit cards from that same-origin manifest without OS detection or click tracking. A Linux-specific PyInstaller/AppImage build and Ubuntu 24.04 workflow produce and smoke-test the canonical package, while a human-controlled workflow input is the only path that can attach files to an existing prerelease.

**Tech Stack:** Python 3.12+/stdlib, pytest, JSON Schema documentation, static HTML/CSS/ES modules, Node's built-in test runner, PyInstaller 6.21.0, AppImageTool 1.9.1, Bash, GitHub Actions, Xvfb.

## Global Constraints

- Branch: `codex/linux-download-site`; work only in the existing isolated worktree.
- Do not tag, create or publish a release, merge, deploy, or push release assets while executing this plan.
- No cloud transcription, account, subscription, app telemetry, recurring online licence check, download tracking, or client-side OS fingerprinting.
- Do not modify pricing or configured checkout URLs; remove only demonstrably stale fallback copy.
- Do not weaken Windows runtime/build behavior or change licence access to transcript, audio, history, snippets, or vocabulary data.
- Core dictation, privacy controls, history deletion, and audio deletion remain free.
- Linux stays visibly labelled `Preview`; make only claims proven by repository tests and package verification.
- Canonical Linux filename: `ROAR-Linux-<paths.APP_VERSION>-x86_64.AppImage`.
- Site supports 375, 768, 1024, and 1440 px widths, WCAG AA contrast, visible keyboard focus, reduced motion, and practical 44-by-44 px targets.
- Keep the current logo, system font stack, lavender/white/near-black identity, static architecture, and existing checkout behavior.
- Every behavior change follows red-green-refactor; configuration/workflow contracts receive failing contract tests before edits.
- Tests must exercise parsed/executed artifacts and observable outcomes. Do not use raw source-substring checks where parsing, importing, or running the artifact can prove the contract.
- Use `C:\Users\xhan1\flowlocal\venv\Scripts\python.exe` for Windows pytest commands in this worktree.
- Baseline exception: `tests/test_smoke.py` fails only while another ROAR process owns the singleton; all other baseline tests must remain green.

## File map

- `scripts/generate_site_release_manifest.py`: fetch/parse/select/validate release metadata and CLI.
- `site/data/releases.schema.json`: public schema version 1.
- `site/data/releases.json`: checked-in, deployable snapshot; Windows current, Linux unavailable until a real asset exists.
- `tests/fixtures/releases/*.json`: deterministic GitHub API inputs.
- `tests/test_release_manifest.py`: generator behavior and error contracts.
- `.github/workflows/pages.yml`: build-time manifest generation and release-triggered refresh.
- `tests/test_pages_workflow.py`: Pages permissions/triggers/generation contract.
- `roar-linux.spec`: Linux-only frozen app collection.
- `requirements-linux-build.txt`: pinned package-build dependency.
- `linux/build_appimage.sh`: canonical package build and checksum.
- `linux/verify_appimage.sh`: frozen/AppImage smoke and checksum verification.
- `tests/test_linux_packaging.py`: packaging/script/spec contract.
- `.github/workflows/linux-preview.yml`: Ubuntu 24.04 tests, package build, workflow artifact, optional explicit upload to an existing release.
- `tests/test_linux_preview_workflow.py`: workflow safety and release-authority contract.
- `site/downloads.mjs`: pure manifest formatting/validation plus download-card controller.
- `site/downloads.test.mjs`: pure JavaScript behavior tests.
- `site/index.html`: download section, card markup, CSS, copy, and existing CTA routing.
- `site/linux/index.html`: narrow installation, verification, and known-limitations page.
- `site/purchase/success.html`: script-free link back to the canonical download section.
- `site/DESIGN.md`: adopted UI/UX tokens and component rules.
- `tests/test_site_downloads.py`: static copy/privacy/accessibility/download-card contract.
- `scripts/roar_versions.py`, `tests/test_roar_versions.py`, `VERSIONS.md`: remove site asset stamping and record current publication without absolute-path drift.
- `docs/LINUX.md`, `README.md`, `CHANGELOG.md`: honest package/release instructions and Preview boundaries.

---

### Task 1: Release manifest source of truth

**Files:**
- Create: `scripts/generate_site_release_manifest.py`
- Create: `site/data/releases.schema.json`
- Create: `site/data/releases.json`
- Create: `tests/fixtures/releases/current.json`
- Create: `tests/fixtures/releases/windows-and-linux.json`
- Create: `tests/fixtures/releases/invalid.json`
- Create: `tests/test_release_manifest.py`

**Interfaces:**
- Produces: `build_manifest(releases: list[dict], repository: str, generated_at: str) -> dict`
- Produces: `validate_manifest(manifest: dict) -> None`, raising `ManifestError`
- Produces CLI: `python scripts/generate_site_release_manifest.py --repository xhan145/roar [--input PATH] --output PATH [--generated-at ISO]`
- Produces schema-version-1 `platforms.windows` and `platforms.linux` records consumed by Tasks 2 and 5.

- [ ] **Step 1: Write fixture data and failing selection tests**

Create realistic GitHub release-list fixtures. The current fixture must contain
the verified `v0.35.2` Windows release and no Linux asset. The dual fixture must
also contain a newer draft (ignored), an ordinary prerelease without an AppImage
(ignored), and a valid prerelease asset named
`ROAR-Linux-0.35.2-x86_64.AppImage` with a positive size and
`digest: "sha256:<64 lowercase hex>"`.

```python
def test_channels_are_selected_independently(load_fixture):
    manifest = build_manifest(
        load_fixture("windows-and-linux.json"),
        "xhan145/roar",
        "2026-08-06T12:00:00Z",
    )
    assert manifest["platforms"]["windows"]["channel"] == "stable"
    assert manifest["platforms"]["windows"]["version"] == "0.35.2"
    assert manifest["platforms"]["linux"]["channel"] == "preview"
    assert manifest["platforms"]["linux"]["package_type"] == "AppImage"

def test_missing_linux_release_fails_closed(load_fixture):
    linux = build_manifest(
        load_fixture("current.json"), "xhan145/roar", "2026-08-06T12:00:00Z"
    )["platforms"]["linux"]
    assert linux == {"available": False, "channel": "preview"}
```

- [ ] **Step 2: Run the tests and verify RED**

Run:
`C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest tests/test_release_manifest.py -v`

Expected: collection fails because `scripts.generate_site_release_manifest`
does not exist.

- [ ] **Step 3: Add failing validation and ambiguity tests**

Cover: invalid JSON root, draft filtering, wrong host/scheme, zero size, missing
digest, malformed digest, asset version/tag mismatch, two matching assets,
deterministic `generated_at`, normalized SHA-256, and exact Windows metadata from
the current fixture. Name each test after one behavior.

```python
@pytest.mark.parametrize("field,value", [
    ("asset_size_bytes", 0),
    ("sha256", "not-a-digest"),
    ("asset_url", "http://example.test/file.exe"),
])
def test_available_record_rejects_invalid_asset_metadata(field, value):
    record = valid_windows_record()
    record[field] = value
    with pytest.raises(ManifestError):
        validate_manifest(base_manifest(windows=record))
```

- [ ] **Step 4: Implement the minimal dependency-free generator**

Use exact regexes:

```python
WINDOWS_ASSET = re.compile(r"^ROAR-Setup-(\d+\.\d+\.\d+)\.exe$")
LINUX_ASSET = re.compile(r"^ROAR-Linux-(\d+\.\d+\.\d+)-x86_64\.AppImage$")
DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
```

Sort eligible releases by `published_at` descending. Accept only GitHub HTTPS
`browser_download_url` values whose path is under
`/xhan145/roar/releases/download/`. Emit these available-record keys exactly:
`available`, `channel`, `version`, `release_name`, `published_at`,
`architecture`, `package_type`, `asset_name`, `asset_url`, `asset_size_bytes`,
`sha256`, and `release_notes_url`; add `tested_environments` and
`known_limitations_url: "/linux/"` to Linux. Use
`urllib.request` with `Accept: application/vnd.github+json`,
`X-GitHub-Api-Version: 2022-11-28`, and optional bearer `GH_TOKEN` only in the
CLI fetch layer.

- [ ] **Step 5: Add schema version 1 and validate output against equivalent code checks**

The schema must set `additionalProperties: false`, require all available-record
fields, constrain `sha256` to `^[0-9a-f]{64}$`, constrain sizes to `minimum: 1`,
use `format: uri`/`date-time`, and use `oneOf` for available versus unavailable
records. `validate_manifest()` mirrors those security-critical constraints with
stdlib code so runtime generation does not require `jsonschema`.

- [ ] **Step 6: Verify GREEN and generate the checked-in current snapshot**

Run the focused pytest command, then:

```powershell
& 'C:\Users\xhan1\flowlocal\venv\Scripts\python.exe' scripts/generate_site_release_manifest.py --repository xhan145/roar --input tests/fixtures/releases/current.json --output site/data/releases.json --generated-at 2026-08-06T12:00:00Z
```

Expected: tests pass; snapshot reports verified Windows metadata and Linux
`available: false`.

- [ ] **Step 7: Commit**

```bash
git add scripts/generate_site_release_manifest.py site/data tests/fixtures/releases tests/test_release_manifest.py
git commit -m "feat(site): generate verified release metadata"
```

---

### Task 2: Pages generation and refresh contract

**Files:**
- Modify: `.github/workflows/pages.yml`
- Create: `tests/test_pages_workflow.py`

**Interfaces:**
- Consumes: Task 1 CLI and `site/data/releases.json`.
- Produces: Pages artifact containing a freshly generated manifest on site pushes, manual runs, and published/edited release events.

- [ ] **Step 1: Write failing workflow contract tests**

Parse the workflow with `yaml.load(..., Loader=yaml.BaseLoader)`. Locate the
deploy job's steps by their `name`/`uses` fields and assert the generation step
precedes the upload step, has the expected CLI arguments, and receives
`GH_TOKEN`. Assert the parsed `on.release.types` sequence is exactly
`["published", "edited"]`.

Also assert `contents: read`, `pages: write`, `id-token: write`, Python setup,
and push paths for the generator/schema/workflow itself.

- [ ] **Step 2: Run the focused test and verify RED**

Run:
`C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest tests/test_pages_workflow.py -v`

Expected: missing generation step and release trigger.

- [ ] **Step 3: Update Pages workflow minimally**

Add:

```yaml
on:
  release:
    types: [published, edited]
```

Include `scripts/generate_site_release_manifest.py` and the schema in push
paths. Add setup-python and this step before artifact upload:

```yaml
- name: Generate verified release metadata
  env:
    GH_TOKEN: ${{ github.token }}
  run: >-
    python scripts/generate_site_release_manifest.py
    --repository ${{ github.repository }}
    --output site/data/releases.json
```

- [ ] **Step 4: Verify GREEN and offline fixture generation**

Run the focused test and Task 1 tests. Run the generator with the current fixture
once more and confirm `git diff --exit-code site/data/releases.json`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/pages.yml tests/test_pages_workflow.py
git commit -m "ci(site): refresh release metadata before Pages deploy"
```

---

### Task 3: Reproducible Linux AppImage package

**Files:**
- Create: `roar-linux.spec`
- Create: `requirements-linux-build.txt`
- Modify: `linux/build_appimage.sh`
- Create: `linux/verify_appimage.sh`
- Modify: `linux/roar.desktop`
- Create: `tests/test_linux_packaging.py`
- Modify: `tests/test_linux_launcher_assets.py`

**Interfaces:**
- Produces: `dist/ROAR-Linux-<version>-x86_64.AppImage`
- Produces: adjacent `.sha256` file formatted `<hex>  <filename>`.
- Consumes environment: `ROAR_LINUX_PYTHON` (default `.venv/bin/python`) and `APPIMAGETOOL`.
- Produces verifier CLI: `bash linux/verify_appimage.sh PATH_TO_APPIMAGE`.

- [ ] **Step 1: Write failing packaging contract tests**

Inspect the Linux spec as executable PyInstaller configuration where possible,
and run the shell recipe with fake `python`, PyInstaller, AppImageTool, and
`sha256sum` shims in a temporary copied fixture. Assert produced filenames,
invocations, and targeted cleanup from observable files/logs. Also assert the
Linux spec includes `settings.html`, `transcript.html`,
`fob.png`, `assets`, `licenses`, `THIRD_PARTY_NOTICES.md`, and the TTS worker/
manifest; excludes Windows-only `uiautomation`, `comtypes`, `PyAudioWPatch`,
DirectML, and Vulkan modules; uses a distinct `ROAR-linux` collection directory;
and never imports `scripts.version_info`.

Assert that the build script:

- never runs `pip install`;
- obtains the version from `paths.APP_VERSION`;
- rejects non-Linux/non-x86_64 hosts;
- invokes `PyInstaller` with `roar-linux.spec`;
- requires `APPIMAGETOOL` rather than downloading an unverified executable;
- creates the exact canonical filename and SHA-256 sidecar;
- never removes `dist/ROAR`, Windows MSI/CAB, or Windows setup files.

Assert `requirements-linux-build.txt` contains exactly
`pyinstaller==6.21.0` plus comments.

- [ ] **Step 2: Run focused tests and verify RED**

Run:
`C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest tests/test_linux_packaging.py tests/test_linux_launcher_assets.py -v`

Expected: missing spec/verifier/build requirements and old ad-hoc recipe failures.

- [ ] **Step 3: Implement `roar-linux.spec`**

Follow `roar.spec` for shared data but use Linux-only hidden imports. Collect
`faster_whisper`, `ctranslate2`, `av`, `onnxruntime`, and `webview`; include
`webview.platforms.gtk` and `gi` as hidden imports. Do not add a Windows icon or
Windows version resource. Name EXE/COLLECT `ROAR-linux` so Windows outputs remain
untouched.

- [ ] **Step 4: Replace the build recipe with a deterministic, targeted script**

The script must use arrays/quoted paths, create
`build/linux/ROAR.AppDir`, copy the frozen tree to `usr/bin/ROAR`, install
`linux/roar.desktop` as `ROAR.desktop`, install the existing purple logo as
`roar.png` and `.DirIcon`, and write this AppRun:

```sh
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export ROAR_APPIMAGE=1
exec "$HERE/usr/bin/ROAR/ROAR-linux" "$@"
```

Set `ARCH=x86_64` only for the appimagetool invocation. Build to a `.building`
path and rename only after success. Use `sha256sum` after the rename.

- [ ] **Step 5: Implement package verification**

`linux/verify_appimage.sh` must:

1. verify the sidecar with `sha256sum --check`;
2. run the bundled frozen binary `--smoke` under `xvfb-run -a` before packing
   when invoked by the build script;
3. run `APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a "$APPIMAGE" --smoke` after packing;
4. require the expected `ROAR: hotkeys registered` and `ROAR: smoke exit`
   markers and fail on `already running`;
5. use a temporary XDG config/data/runtime directory and clean it with a trap.

- [ ] **Step 6: Verify GREEN and shell syntax**

Run focused pytest, then:

```bash
bash -n linux/build_appimage.sh
bash -n linux/verify_appimage.sh
```

Expected: all focused tests pass and both scripts parse.

- [ ] **Step 7: Commit**

```bash
git add roar-linux.spec requirements-linux-build.txt linux/build_appimage.sh linux/verify_appimage.sh linux/roar.desktop tests/test_linux_packaging.py tests/test_linux_launcher_assets.py
git commit -m "build(linux): produce verified AppImage packages"
```

---

### Task 4: Ubuntu 24.04 preview workflow and honest Linux docs

**Files:**
- Create: `.github/workflows/linux-preview.yml`
- Create: `tests/test_linux_preview_workflow.py`
- Modify: `docs/LINUX.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: Task 3 build/verifier and canonical output names.
- Produces: verified workflow artifact on pull request/manual dispatch.
- Optional input `release_tag` may upload to an existing GitHub draft/prerelease; empty means no release mutation.

- [ ] **Step 1: Write failing workflow safety tests**

Parse the workflow with `yaml.BaseLoader`. Assert the build job runs on
`ubuntu-24.04`, exposes only `contents: read`, and ends with an
`actions/upload-artifact@v4` step. Assert the attach job exposes
`contents: write`, depends on build, has the exact manual-dispatch guard, checks
an existing release's draft/prerelease flags, and uploads without any parsed step
that creates or publishes a release.

Also pin AppImageTool URL and digest exactly:

- URL: `https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage`
- SHA-256: `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`

Assert the workflow runs Linux-focused pytest, shell syntax, full package build,
verification, and uploads both AppImage and checksum.

- [ ] **Step 2: Run focused tests and verify RED**

Run:
`C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest tests/test_linux_preview_workflow.py -v`

Expected: workflow missing.

- [ ] **Step 3: Implement the workflow**

Triggers:

```yaml
on:
  pull_request:
    paths: ["linux/**", "roar-linux.spec", "requirements-linux*.txt", ".github/workflows/linux-preview.yml", "tests/test_*linux*.py"]
  workflow_dispatch:
    inputs:
      release_tag:
        description: Existing draft/prerelease tag to receive verified assets; leave empty for artifact-only build
        required: false
        type: string
```

Use two jobs. `build` has `contents: read`, performs every test/build/verification,
and uploads the workflow artifact. `attach` has `contents: write`, depends on
`build`, downloads that artifact, and is guarded with
`${{ github.event_name == 'workflow_dispatch' && inputs.release_tag != '' }}`.
Before upload, run `gh release view "$TAG" --json isDraft,isPrerelease` and fail
unless one flag is true. Use `gh release upload "$TAG" "$APPIMAGE" "$SHA" --clobber`.
Never create or publish a release.

- [ ] **Step 4: Update docs with proved boundaries**

Replace “unverified AppImage recipe” with exact build/verify commands. State:

- package architecture is x86_64;
- package CI target is Ubuntu 24.04 with automated Xvfb launch smoke;
- Linux remains Preview;
- Wayland is not supported by the current hotkey/injection implementation;
- real microphone, physical global-hotkey, and cross-app injection checks remain
  the manual release gate and are not implied by Xvfb smoke;
- checksum verification command is `sha256sum --check <file>.sha256`;
- no Linux release exists until a human creates a prerelease and runs the manual
  upload path.

Keep README Windows-first status accurate, add a short Linux Preview link, and
do not claim Linux GPU support.

- [ ] **Step 5: Verify GREEN, focused Linux tests, and docs claims**

Run the workflow test, the 37 Linux-focused tests, and `bash -n` on both package
scripts. Search site/docs for unsupported claims:

```bash
rg -n "Linux.*(CUDA|GPU)|Wayland.*supported|portable AppImage|verified on Ubuntu" README.md docs/LINUX.md site
```

Expected: no unsupported positive claim; necessary limitation language may match.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/linux-preview.yml tests/test_linux_preview_workflow.py docs/LINUX.md README.md CHANGELOG.md
git commit -m "ci(linux): build preview packages without publishing"
```

---

### Task 5: Download cards, manifest controller, and design record

**Files:**
- Create: `site/downloads.mjs`
- Create: `site/downloads.test.mjs`
- Modify: `site/index.html`
- Create: `site/linux/index.html`
- Create: `site/DESIGN.md`
- Create: `tests/test_site_downloads.py`
- Modify: `tests/test_site_analytics.py`
- Modify: `tests/test_site_checkout.py`
- Modify: `tests/test_site_pricing.py`

**Interfaces:**
- Consumes: Task 1 manifest at `data/releases.json`.
- Produces pure JS: `formatBytes(bytes)`, `formatDate(iso)`, `parseManifest(value)`, and `platformView(record)`.
- Produces DOM bootstrap bound to `[data-release-platform="windows|linux"]`.

- [ ] **Step 1: Write failing parsed static-site tests**

Parse HTML with `html.parser` or an equivalent local parser and assert observable
elements/attributes rather than raw source substrings. Assert:

- a section `id="download"` has explicit Windows and Linux cards;
- visible `Stable` and `Preview` text exists in card markup;
- each card contains semantic metadata hooks for version, release date, package,
  architecture, size, checksum, release notes, install instructions, status,
  and action;
- copy controls are real `<button type="button">` controls with accessible names;
- an `aria-live="polite"` status exists per checksum interaction;
- nav, hero, and Core CTA point to `#download` before metadata loads;
- no `navigator.userAgent`, `navigator.platform`, OS-selection library,
  download-click listener, beacon, download event, or versioned release URL exists;
- stale “Small installer” and static “Card checkout is coming soon” copy is gone;
- the Linux card links to `linux/` for limitations;
- the page includes `downloads.mjs` as a module and maintains the existing consent-only analytics rule.

- [ ] **Step 2: Write failing pure JavaScript tests**

Using `node:test`:

```javascript
test('formatBytes reports exact binary size without calling a large file small', () => {
  assert.equal(formatBytes(908794228), '866.69 MiB');
});

test('unavailable channels produce a disabled recovery view', () => {
  assert.deepEqual(platformView({available:false, channel:'preview'}), {
    available: false,
    channel: 'preview',
    actionLabel: 'Linux Preview unavailable',
  });
});
```

Also cover invalid schema version, malformed available records, UTC date
formatting, Linux tested environments, and SHA abbreviation while preserving the
full digest for copy/accessibility.

- [ ] **Step 3: Run both suites and verify RED**

Run:

```powershell
& 'C:\Users\xhan1\flowlocal\venv\Scripts\python.exe' -m pytest tests/test_site_downloads.py -v
node --test site/downloads.test.mjs
```

Expected: missing module/section failures.

- [ ] **Step 4: Implement pure manifest parsing and card state**

`parseManifest` must require `schema_version === 1`, repository
`xhan145/roar`, and both platform records. It never guesses a URL. On any
validation/fetch error, render both cards unavailable and offer the repository's
Releases page as the recovery link.

Use the async Clipboard API only from copy-button clicks. On success announce
`Checksum copied`; on failure select the full checksum `<code>` text and announce
`Copy unavailable; checksum selected for manual copy`. Do not emit analytics or
custom download events.

- [ ] **Step 5: Add the focused two-card section and route existing CTAs**

Insert after the hero. Desktop uses two columns; at 768 px and below use one.
At 375 px actions are full width, metadata wraps, checksum code uses
`overflow-wrap:anywhere`, and no horizontal scroll appears. Use definition lists
for metadata, inline SVG icons, tonal surfaces, visible text badges, underlined
release/limitations links, and minimum 44 px controls.

Keep a safe initial DOM: Windows says metadata is loading; Linux says Preview
availability is checked from verified releases. JavaScript enhances it. Do not
preselect or hide a platform.

- [ ] **Step 6: Add Linux Preview install/limitations page**

Reuse the brand tokens without remote fonts, framework code, stock imagery, or
decorative animation. Document `chmod +x`, checksum verification, direct launch,
Ubuntu 24.04 automated package smoke, x86_64, X11 requirement, unsupported
Wayland path, and the manual real-device gates. Do not claim GPU support.

- [ ] **Step 7: Write `site/DESIGN.md` from the adopted UUPM decisions**

Include these exact sections: existing tokens retained, new semantic tokens,
download-card anatomy, metadata hierarchy, responsive behavior at 375/768/1024/
1440, accessibility rules, focus/touch rules, checksum feedback, unavailable/
error state, installation disclosure, motion/reduced-motion, do examples, do-not
examples, and rationale for each Material Design 3-inspired decision.

Retain `--bg`, `--surface`, `--surface-2`, `--border`, `--border-hi`, `--text`,
`--muted`, `--accent`, `--accent-2`, `--accent-ink`, `--ok`, `--r`, `--maxw`,
`--dur`, and `--ease`. Add semantic `--preview`, `--preview-bg`,
`--unavailable`, and `--focus-ring` values that meet WCAG AA in their actual
text/background pairs.

- [ ] **Step 8: Verify GREEN and existing site tests**

Run Node tests plus all `tests/test_site_*.py`. Run a local static server and
verify there are no console/network errors beyond the expected same-origin
manifest request and consent-controlled GA request.

- [ ] **Step 9: Commit**

```bash
git add site/index.html site/downloads.mjs site/downloads.test.mjs site/linux site/DESIGN.md tests/test_site_downloads.py tests/test_site_analytics.py tests/test_site_checkout.py tests/test_site_pricing.py
git commit -m "feat(site): add verified Windows and Linux download cards"
```

---

### Task 6: Remove remaining version drift and stale success-page link

**Files:**
- Modify: `site/purchase/success.html`
- Modify: `scripts/roar_versions.py`
- Modify: `tests/test_roar_versions.py`
- Modify: `tests/test_site_purchase_pages.py`
- Modify: `VERSIONS.md`

**Interfaces:**
- Consumes: Task 5 `index.html#download`.
- Produces: version parity that no longer treats generated release metadata as an echo of `paths.APP_VERSION`.
- Produces: script-free purchase page with no versioned asset URL.

- [ ] **Step 1: Write failing drift tests**

```python
def test_desktop_version_echoes_do_not_stamp_release_assets():
    echoes = rv.COMPONENTS[0]["echo"]
    assert all("site/" not in rel.replace("\\", "/") for rel, _ in echoes)

def test_purchase_success_routes_to_download_section_without_script():
    html = SUCCESS.read_text(encoding="utf-8")
    assert "../index.html#download" in html
    assert "ROAR-Setup-" not in html
    assert "<script" not in html.lower()
```

Add a dashboard test asserting the desktop source is stable (`.` or repository
identifier), never a machine-specific absolute path.

- [ ] **Step 2: Run focused tests and verify RED**

Run:
`C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest tests/test_roar_versions.py tests/test_site_purchase_pages.py -v`

Expected: site echoes and versioned success link remain.

- [ ] **Step 3: Remove site echoes and stabilize the dashboard source**

Delete the three `site/` echo patterns from the desktop component. In dashboard
output, render a source path relative to the desktop root when the component is
inside it (`.` for the desktop); preserve an explicit external path for a
separately checked-out Android component. Do not alter canonical version parsing,
release parity checks, or write behavior beyond those outputs.

- [ ] **Step 4: Change the success page link and refresh `VERSIONS.md`**

Set the download link to `../index.html#download` with text
`Choose your ROAR download`. Run version parity with the real Android checkout
explicitly supplied when it exists:

```powershell
$env:ROAR_ANDROID_DIR='C:\Users\xhan1\StudioProjects\roar-android'
& 'C:\Users\xhan1\flowlocal\venv\Scripts\python.exe' scripts/roar_versions.py --check --github
Remove-Item Env:ROAR_ANDROID_DIR
```

Expected: desktop publication is `v0.35.2`, source is stable, Android data is
preserved from its canonical checkout, and no site files change.

- [ ] **Step 5: Verify GREEN and commit**

Run both focused suites and `python scripts/roar_versions.py --check --github`
with the Android override. Then:

```bash
git add site/purchase/success.html scripts/roar_versions.py tests/test_roar_versions.py tests/test_site_purchase_pages.py VERSIONS.md
git commit -m "fix(release): remove hardcoded site version drift"
```

---

### Task 7: Full verification and release-ready review

**Files:**
- Modify only files required by verified failures or review findings.

**Interfaces:**
- Consumes every earlier task.
- Produces a clean, reviewed branch and exact release/deployment handoff; produces no public release or deployment.

- [ ] **Step 1: Run focused functional suites**

```powershell
& 'C:\Users\xhan1\flowlocal\venv\Scripts\python.exe' -m pytest tests/test_release_manifest.py tests/test_pages_workflow.py tests/test_linux_packaging.py tests/test_linux_preview_workflow.py tests/test_site_downloads.py tests/test_roar_versions.py -q
node --test site/downloads.test.mjs
```

- [ ] **Step 2: Run all existing site, Linux, privacy/licensing, checkout, and version gates**

```powershell
& 'C:\Users\xhan1\flowlocal\venv\Scripts\python.exe' -m pytest -q tests/test_site_*.py tests/test_*linux*.py tests/test_commercial_privacy.py tests/test_network_hygiene.py tests/test_license.py tests/test_entitlements.py tests/test_pricing.py tests/test_site_checkout.py
& 'C:\Users\xhan1\flowlocal\venv\Scripts\python.exe' scripts/roar_versions.py --check --github
```

- [ ] **Step 3: Run the full repository suite**

Run:
`C:\Users\xhan1\flowlocal\venv\Scripts\python.exe -m pytest -q`

Expected: every test passes, except `tests/test_smoke.py` may reproduce the
documented `ROAR: already running` environmental failure while a live instance
owns the singleton. If it does, run the suite excluding only that test and record
the exact evidence; do not kill the user's ROAR process without permission.

- [ ] **Step 4: Build and verify Linux package in Linux**

Prefer a local Ubuntu 24.04 container matching CI. Install the workflow's apt
dependencies, create the system-site-packages venv, install
`requirements-linux.txt` and `requirements-linux-build.txt`, verify the pinned
AppImageTool checksum, build, and run `linux/verify_appimage.sh`. If local Docker
is unavailable, run the same steps in the available WSL distro and report the
Ubuntu version precisely; do not relabel it as 24.04.

- [ ] **Step 5: Validate schema/snapshot and workflow syntax**

Regenerate the current manifest from the fixture and assert no diff. Run
`bash -n` for Linux and Windows build scripts. Parse every JSON file with Python
and every workflow with the available YAML parser or focused contract tests.

- [ ] **Step 6: Browser verification at required widths**

Serve `site/` locally. Verify 375, 768, 1024, and 1440 px layouts, keyboard-only
navigation/focus, checksum copy success and denied/fallback state, reduced motion,
manifest unavailable and fetch-error states, no horizontal overflow, no console
errors, and no download tracking/OS detection. Capture screenshots for visual
inspection; do not commit disposable screenshots.

- [ ] **Step 7: Run scoped code review and fix one finding wave**

Invoke `superpowers:requesting-code-review` with the full branch diff and the
design/plan paths. Give one fixer the complete actionable finding list, rerun
covering tests, and perform exactly one scoped re-review as required by
subagent-driven development.

- [ ] **Step 8: Verify repository cleanliness and atomic history**

Run `git diff --check`, `git status --short`, `git log --oneline origin/main..HEAD`,
and inspect every commit. No build output, model cache, private key, licence,
downloaded tool, or temporary review artifact may be tracked.

- [ ] **Step 9: Finish the branch without publishing**

Invoke `superpowers:verification-before-completion`, then
`superpowers:finishing-a-development-branch`. Present the review-ready branch,
test evidence, artifact name/checksum if locally built, remaining manual X11
hardware checks, and exact human release sequence. Do not merge, push, tag,
create/publish a release, attach an asset, or deploy Pages.
