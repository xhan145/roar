# Single-File Setup Exe — Design

**Date:** 2026-07-04
**Status:** approved (option: 7-Zip SFX, over zip and WiX Burn)
**Scope:** build tooling only — no app code, no version bump. Artifact wraps
the current MSI.

## Goal

One distributable file. The external-CAB MSI (forced by the 2 GB `.msi`
format cap) is five files that must travel together; wrap them into
`dist/ROAR-Setup-<version>.exe` — double-click → extracts to temp → MSI
installs with a progress bar → temp cleaned up.

## Why 7-Zip SFX

- WiX Burn (canonical) rejected: WiX 3.14's attached containers have known
  >2 GB failures — the same class of bug that broke the embedded-CAB MSI —
  and avoiding that means migrating to the WiX v5 toolchain.
- Zip rejected by user: two-step install.
- 7z format has 64-bit offsets (no 2 GB cliffs); the machine already has
  7-Zip; store-mode archiving is fast because the CABs are already mszip.

## Mechanics — `scripts/build_setup.sh`

1. Ensure `build/7zsd/7zSD.sfx`: download `https://www.7-zip.org/a/lzma1900.7z`
   once and extract `bin/7zSD.sfx` with the installed `7z.exe`
   (`C:\Program Files\7-Zip\7z.exe`; fail with a clear message if absent).
   LZMA SDK 19.00 is the last release shipping the prebuilt installer stub —
   newer 7z-extra/SDK packages carry source only; the old stub reads modern
   7z archives fine.
2. Archive `dist/ROAR-<v>.msi` + `dist/roar*.cab` into a temp `payload.7z`
   with `-t7z -mx0` (store — contents are already compressed).
3. Write UTF-8 `config.txt`:
   `;!@Install@!UTF-8!` / `Title="ROAR <v>"` /
   `RunProgram="msiexec /i \"%%T\\ROAR-<v>.msi\" /qb"` / `;!@InstallEnd@!`
   (`%%T` = SFX temp dir; `/qb` = unattended basic-UI progress bar.)
4. Concatenate `7zSD.sfx + config.txt + payload.7z` →
   `dist/ROAR-Setup-<v>.exe.building`, atomic rename, purge superseded
   `ROAR-Setup-*.exe`, delete `payload.7z`.

Version comes from `paths.APP_VERSION` like `build_msi.sh`. The script is
run per release AFTER `build_msi.sh`; it fails loudly if the MSI or cabs are
missing.

## Verification

Kill ROAR + webviews, run the setup exe, wait for msiexec to finish
(AllowSameVersionUpgrades makes a same-version reinstall safe), then assert:
single ROAR product at the current version, installed probe green, config +
history intact. Note: an unsigned exe downloaded from the web will trip
SmartScreen; local use has no mark-of-the-web, so no warning.

## Docs

README gets a one-line note that `ROAR-Setup-<v>.exe` is the single-file
installer and the msi+cabs remain usable directly if kept together.
