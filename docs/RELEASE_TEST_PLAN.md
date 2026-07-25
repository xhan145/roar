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

4. Confirm `THIRD_PARTY_NOTICES.md`, `tts/worker.py`, and
   `tts/assets/kokoro-model-manifest.json` exist in `dist/ROAR`.
5. Confirm `kokoro`, `misaki`, `torch`, `transformers`, and all model/voice
   `.pth`/`.pt` files are absent from the main app bundle.

### Optional Read Aloud component

The current source supports explicit offline pack import rather than a WiX
feature. Before distributing a separate `ROAR Local Voice Pack`:

1. On Python 3.12, run `scripts/prepare_kokoro_runtime.py --yes`.
2. On a connected release workstation only, run
   `scripts/prepare_kokoro_voice_pack.py --download --destination <staging>`.
3. Disconnect networking and import `<staging>` from Settings -> Read Aloud.
4. Verify every manifest SHA-256, the pinned revision, all four voices, Stop,
   repeated Stop/Start, worker exit, and removal.
5. Sign the runtime/pack installer and include the complete corresponding
   license texts and upstream notices. This is a release blocker until the
   optional installer and its uninstall/upgrade behavior are tested.

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

- [ ] Read Aloud absent: all controls explain the missing component; normal
      dictation, Settings, startup, and shutdown remain unaffected.
- [ ] Read Aloud offline: disable network before launch; preview every voice,
      read a long document, pause/resume, Stop during synthesis and playback,
      then repeat quickly without stale audio.
- [ ] Start dictation during playback: speech stops before microphone capture.
      Attempt Read Aloud during recording: it is calmly rejected.
- [ ] Selection privacy: Notepad selection works; password fields and unknown
      UIA security state are refused; clipboard fallback is off by default.
- [ ] Keyboard/Narrator: reach all Read Aloud controls, hear meaningful names
      and status changes, use the preview-before accept/repeat/cancel dialog,
      and confirm visible focus in normal and high-contrast modes.

## After tagging

Push main + tags; relaunch the installed app; verify Check for updates says
"You're up to date".
