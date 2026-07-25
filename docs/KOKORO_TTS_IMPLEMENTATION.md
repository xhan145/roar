# ROAR Read Aloud — Kokoro TTS implementation plan

Status: implementation plan recorded before runtime changes  
Scope: ROAR Core, local-only, optional Kokoro-82M voice pack

## Repository findings

- ROAR is a Python tray application. `app.py` owns the `pystray` menu, global
  hotkeys, the dictation worker queue, model lifetime, and shutdown.
- Settings run in a separate lightweight `pywebview` process
  (`settings_ui.py` + `settings.html`). That process must not import either the
  STT or TTS machine-learning stack.
- The development environment and current application environment use Python
  3.14. The official `kokoro` 0.9.4 package declares Python 3.10–3.12 support,
  so Kokoro cannot safely be added to the existing process.
- PyTorch is not an existing ROAR dependency. `faster-whisper` uses
  CTranslate2. Adding PyTorch to the main PyInstaller payload would materially
  increase its size and create interpreter/dependency conflicts.
- Microphone capture and short feedback tones use `sounddevice`. There is no
  long-form output abstraction, output-device selector, or existing TTS
  implementation.
- The STT model is constructed once and kept warm by a daemon worker. Jobs are
  serialized through a `queue.Queue`; shutdown sends a sentinel and joins the
  worker.
- Source runs store models in `models/`. Frozen builds store models under
  `%LOCALAPPDATA%\ROAR\models`. Settings are under `%APPDATA%\ROAR`; history,
  audio, status, logs, and per-user model data are under
  `%LOCALAPPDATA%\ROAR`.
- Active-window identity, process name, and title are available through
  `window_focus`. Windows UI Automation is not currently used. Existing
  clipboard restoration in `inject_windows.py` is time-based and does not have
  sequence-number race protection, so it is not suitable for selected-text
  reading.
- Windows hotkeys use the `keyboard` package. Existing collision checks only
  ensure the two dictation chords differ; Read Aloud commands need validation
  against every configured chord.
- Live status and diagnostics are allowlist-only. TTS operational fields must
  be explicitly allowlisted, while text, phonemes, selected content, clipboard
  data, audio, and full private paths remain excluded.
- Packaging is PyInstaller one-dir plus WiX 3 MSI and a 7-Zip setup wrapper.
  User data under AppData survives normal upgrades. The current installer has
  no optional feature-pack mechanism.

## Chosen architecture

Kokoro will run in a supervised optional worker process using newline-delimited
JSON over the worker's standard input/output pipes. It will not open a network
listener. This isolates Python 3.12, PyTorch, Misaki, and Kokoro from ROAR's
Python 3.14/CTranslate2 process and keeps the settings process lightweight.

The runtime will be backend-neutral:

```text
TTSService
├── TTSEngine protocol
├── KokoroEngine (supervised pipe worker client)
├── FakeTTSEngine (tests)
├── TTSRequest / AudioChunk / CancellationToken
├── TTSPlaybackController (sounddevice OutputStream)
├── TextChunker
├── VoiceCatalog
├── TTSModelManager (manifest/hash/path validation)
└── deterministic TTSState events
```

`TTSService` will own one engine, serialize requests, use bounded queues, reject
stale generations after cancellation, expose pause/resume/stop, and keep both
synthesis and playback off the UI thread. Playback uses 24 kHz mono float32
audio in memory; generated speech is not written to disk.

The worker will:

- start only on explicit Read Aloud use or opt-in preload;
- be launched with a configured Python 3.12 runtime, with a startup timeout;
- set Hugging Face/Transformers offline environment flags;
- construct `KModel` from the verified local `config.json` and
  `kokoro-v1_0.pth`;
- pass a verified local voice `.pt` path to `KPipeline`, avoiding its download
  path;
- use `torch.load(..., weights_only=True)` through the official API;
- emit structured state, audio, metrics, and error messages without text or
  phonemes;
- accept cancellation and terminate with ROAR;
- be restartable after a crash.

English (`en-us`) is the first production language. Misaki English remains
usable when eSpeak-NG is absent; out-of-dictionary fallback may be reduced.
eSpeak-NG will not be bundled or made mandatory. Broader languages remain
disabled pending runtime and redistribution review.

## Voice pack and provenance

The optional `ROAR Local Voice Pack` is a directory with a pinned manifest,
Kokoro config, model weights, and a conservative English voice set. Import is
an explicit Settings action. ROAR will copy only manifest-listed regular files
into a staging directory, reject traversal/symlink/reparse-point inputs, verify
size and SHA-256, and atomically replace the installed pack. No model download
will occur in the app or worker.

The pinned upstream is `hexgrad/Kokoro-82M`, model v1.0, revision
`8542409da2986c0ab5d41b3cf0411f7a58caab38`. The manifest records every file's
SHA-256, size, origin, and license, including a complete Apache-2.0 text copied
into the offline pack. Removal deletes only the installed TTS pack, never
dictation models or settings. The per-user voice-pack location survives normal
MSI upgrades.

## UI and command integration

Settings gains a keyboard-operable `Read Aloud` view using existing controls
and responsive CSS. The bridge exposes configuration, pack status/import/
removal, output devices, voice preview/stop, clipboard read, typed-text read,
and stop-all commands without importing Kokoro/PyTorch.

Text-bearing commands cross from Settings to the tray through a private,
authenticated per-user Windows named pipe with a bounded schema. No request
content is written to disk, and there is no localhost network server. Commands
are never written to status or diagnostics. Clipboard reading is explicit.
Selected-text retrieval prefers Windows UI Automation and fails closed for
password/protected/unknown fields. An optional explicit copy fallback uses
clipboard sequence numbers and restores only if no newer clipboard write won
the race.

Config adds validated Read Aloud defaults. All privacy-sensitive behavior is
off by default. Read Aloud is always a Core capability and does not call the
entitlement system.

Global Read Aloud hotkeys are optional and empty by default. When configured,
they are checked for collisions with dictation and other Read Aloud commands.
Stop is registered globally whenever configured and remains effective during
speech.

## STT/TTS arbitration

- Starting dictation stops TTS immediately by default.
- Starting TTS while recording is rejected with a calm status message.
- Read-back defaults to Off and adds no work to the normal dictation path.
- Read-after-insertion queues the finalized transcript after injection.
- Preview-before-insertion requires a small accept/repeat/cancel flow; it will
  not insert until accepted.
- Playback never enters the microphone/transcription queue. Output stops before
  microphone capture begins to reduce acoustic feedback.

## Test and hardening plan

1. Add pure tests for config bounds/migration, state transitions, chunking,
   Unicode and length limits, voice compatibility, sample validation, manifest
   verification, corrupt/missing packs, diagnostics/log redaction, hotkey
   collisions, clipboard sequence races, and safe-selection failures.
2. Add deterministic fake-engine/playback tests for queue bounds, cancellation,
   pause/resume, repeated requests, error recovery, shutdown, and STT/TTS
   arbitration.
3. Add opt-in `kokoro_model` tests that require an already installed local pack
   and never download.
4. Extend settings import-safety and smoke tests so the lightweight process
   cannot import `kokoro`, `torch`, `misaki`, or the worker runtime.
5. Add an offline benchmark reporting load time, warm latency, first audio,
   synthesis/audio duration, real-time factor, memory/backend, voice, and input
   length without timing assertions.
6. Red-team path traversal, reparse points, hash bypass, arbitrary pickle
   loading, worker orphaning, stale queues, giant input, clipboard races,
   privacy leakage, and licensing/entitlement regressions.

## Packaging plan

The main app ships the backend-neutral client, worker script, manifest template,
notices, and import tooling, but not PyTorch/model binaries. A separate
versioned offline voice-pack build uses Python 3.12 and pinned
`requirements-tts.txt`. It is distributed as an optional component after its
size and licenses are reviewed. The main MSI preserves `%LOCALAPPDATA%\ROAR\tts`
on upgrade and leaves it on uninstall by default; Settings provides explicit
removal. Installer documentation will identify this behavior and the remaining
WiX optional-component work.

## Release gates

No release is ready until cancellation is prompt, stale queued speech is
impossible, missing TTS components cannot affect dictation, no content reaches
logs/diagnostics/status, secure-field selection fails closed, model files are
hash-verified, the worker exits with ROAR, normal CI remains model-free, and
keyboard/screen-reader manual checks are recorded.
