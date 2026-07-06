# ROAR release test plan

Run before tagging. Automated first, then the manual Windows checks that can't
be automated.

## Automated (must pass ×2 in a row)

```
venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_transcriber_gpu.py
```

Kill `ROAR.exe` + its `msedgewebview2.exe` children first — a running instance
holds the single-instance/settings mutexes and flakes the two smoke tests.
`tests/test_transcriber_gpu.py` needs CUDA; run it on GPU machines only.

## Build train (serialized, never two MSI builds at once)

1. `venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm`
   - Expect a WARNING if `models-seed/` is absent (languages won't be bundled).
2. `bash scripts/build_msi.sh` → `dist/ROAR-<v>.msi` + `roar1..N.cab`
   (external cabs are REQUIRED — the .msi format is capped at 2 GB; the files
   must travel together).
3. `bash scripts/build_setup.sh` → single-file `dist/ROAR-Setup-<v>.exe`.

## Frozen smoke probe

`dist/ROAR/ROAR.exe --settings --smoke`, then read the tail of
`%LOCALAPPDATA%\ROAR\roar.log`. Expect one line:
`settings probe navs=… version=<v> … diag=1 themeok=1` with every flag =1.
(The probe writes to the log — windowed exes have no stdout.)

## Install / upgrade

- With ROAR fully stopped: `msiexec /i dist\ROAR-<v>.msi /qn`
  (use `/qn`; the setup exe's `/qb` pops a blocking Files-in-Use dialog if
  anything lingers). Exit code 0.
- `Get-CimInstance Win32_Product -Filter "Name='ROAR'"` shows exactly one
  product at the new version.
- Data intact: history row count unchanged; `config.json` hotkey/device
  untouched; `badge_unlocks` preserved.
- Launch the installed exe: log shows `hotkeys registered` + `tray ready`,
  exactly one ROAR.exe process.

## Manual Windows checks (no automation possible)

- [ ] Offline launch: disable network, launch, dictate — everything works;
      Check for updates shows a calm error.
- [ ] Missing microphone: unplug/disable mic, hold hotkey — calm balloon, no
      crash.
- [ ] Dictate into Notepad (default profile: capitalized), VS Code (verbatim,
      lowercase), WhatsApp Web in Chrome (casual).
- [ ] Double-tap hands-free: lock on, speak, tap to stop.
- [ ] "Scratch that" removes the last dictation; refuses after clicking into
      another window (error tone).
- [ ] Focus guard: start dictating, click a different window before releasing —
      "Focus changed — ROAR did not type." and nothing was typed.
- [ ] Appearance: Dark / Light / Match Windows all render legibly (spot-check
      every tab).
- [ ] Safe Mode: overlay+preview off, paste on; message lists prior values.
- [ ] Copy Safe Diagnostics: report contains no transcript/paths/usernames.
- [ ] CPU-only machine (or force_device=cpu): model loads on CPU, dictation
      works (slower).

## After tagging

Push main + tags; relaunch the installed app; verify Check for updates says
"You're up to date".
