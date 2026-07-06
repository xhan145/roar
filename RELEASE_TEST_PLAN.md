# ROAR Release Test Plan

Run before tagging or shipping:

1. `py -3.12 -m pytest`
2. `venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm`
3. `scripts/build_msi.sh`
4. `scripts/build_setup.sh`

Manual Windows checks:

- Launch offline with no network connection.
- Launch with missing/corrupt `config.json`; app should use defaults.
- Launch with missing/corrupt `history.db`; recoverable corruption should be moved aside.
- Launch without a microphone; settings and a calm error should remain available.
- Dictate into Notepad without a license.
- Start recording in one app, switch focus, and confirm ROAR does not type.
- Enable paste fallback, dictate, and confirm clipboard contents are restored.
- Use scratch-that in the original target, then try it after changing focus.
- Verify Privacy controls, Clear history, and audio-retention controls are available in Core.
- Open Settings in system, light, and dark appearance.
- Copy Safe Diagnostics and confirm no transcript, clipboard, snippet, vocabulary, audio, full window title, or license secret is present.
- Import a snippet pack containing `{clipboard}` and confirm the UI warns about clipboard use.
- Confirm Code mode symbol dictation does not affect Clean prose mode.
- Install `dist/ROAR-Setup-<version>.exe`, launch offline, then upgrade over an existing install and verify config/history/license data are preserved.
