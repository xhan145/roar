# Read Aloud privacy and data flow

Read Aloud is local-only. It creates no account, telemetry, HTTP server, remote
API request, or background model download.

## What text is accessed

- Typed preview text is used only when the user presses a Read button.
- Clipboard text is read only from an explicit Read Clipboard command.
- Selected text is read only from an explicit command or configured hotkey.
  ROAR first uses Windows UI Automation and reads only the exposed selection.
- Dictation text is read back only when the user selects an opt-in read-back
  mode. The default is Off.
- Repeat reuses only the last explicit in-memory request. It does not infer
  content from history, the active window, or the clipboard.

ROAR does not scrape whole windows. Password fields, credential processes, and
fields whose password/security state is unknown fail closed. The optional
Ctrl+C fallback is off by default. When enabled, it preserves text or an empty
clipboard and restores only if no newer user/application clipboard write won
the sequence-number race. It refuses non-text clipboard payloads that cannot be
faithfully restored.

## Local processing and retention

Text is sent from Settings to the tray through an authenticated per-user
Windows named pipe with a bounded command schema. The tray sends it to a
supervised Python 3.12 worker through standard input. The worker returns
24 kHz mono float32 audio through standard output. No TCP/UDP listener is
opened.

Generated audio is played from memory and is not written to disk. Text,
phonemes, selection data, clipboard data, and generated audio are excluded from
the status and diagnostics allowlists and structured logs. Crashes report only
categories and operational metrics.

The model pack and Python runtime are local files under
`%LOCALAPPDATA%\ROAR\tts`. They contain dependencies and model data, not user
text or generated speech. Normal MSI upgrades and uninstall leave these files
in place; Settings -> Read Aloud -> Remove Local Voice Pack removes only the
managed voice pack.

## Offline enforcement

The worker receives explicit local paths for config, weights, and voices and
starts with Hugging Face/Transformers offline flags. The application contains
no code path that downloads the TTS runtime or model. The release preparation
scripts are explicit operator tools and require affirmative command-line flags.
