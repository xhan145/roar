# Read Aloud troubleshooting

## “Local Voice Pack is not installed”

The normal ROAR installer intentionally omits the model. Obtain the reviewed
offline pack from the project release channel and use
Settings -> Read Aloud -> Install / Import. ROAR verifies the pinned manifest,
file sizes, SHA-256 values, paths, and regular-file type before an atomic
install. It will not download a replacement.

## “Kokoro Python 3.12 runtime is not installed”

Kokoro 0.9.4 does not support ROAR's main Python 3.14 process. For development,
install Python 3.12 and run:

```powershell
py -3.12 scripts\prepare_kokoro_runtime.py --yes
```

The isolated runtime is placed under `%LOCALAPPDATA%\ROAR\tts\runtime`.
`ROAR_TTS_PYTHON` is a developer-only override for testing another interpreter.
Do not point it at an untrusted executable.

## Slow first speech

The model loads lazily. On the validated CPU system cold load was about
22.2 seconds; warm synthesis was faster than real time. Enable preload only if
you accept the startup memory/load cost. The configured idle timeout unloads
the worker.

## No selection is read

Keep text selected and invoke Read Selected Text while the target application
still has focus. Some applications do not expose a UI Automation selection.
ROAR intentionally refuses password/protected/unknown fields. The separately
opt-in Ctrl+C fallback cannot preserve image/file/custom clipboard payloads, so
it refuses them rather than destroying them.

## No audio or wrong output

Choose System default or an available output device in Settings and press Save,
then use an editable voice preview. Device changes affect the next request. A
device removed after saving produces a calm error; select another device.

## Recovery

Press Stop, then retry. Stop is idempotent. A crashed worker is unloaded and
can be started on the next request. If verification fails, re-import a trusted
pack; partial staging directories are removed and never become active.

Safe Diagnostics may contain engine version, model status/version, voice ID,
language, output-device ID, sample rate, latency, and error category. It never
contains text, phonemes, clipboard/selection content, generated audio, or a
full private model path.
