# Read Aloud development and release setup

ROAR's main process remains on Python 3.14. Kokoro runs in a separate supervised
Python 3.12 process because `kokoro==0.9.4` declares Python 3.10–3.12 support.
Do not add Kokoro, Misaki, Transformers, or PyTorch to `requirements.txt`.

## Provision the optional runtime

Install the main requirements as usual, ensure Python 3.12 is available, then
explicitly create the isolated runtime:

```powershell
py -3.12 scripts\prepare_kokoro_runtime.py --yes
```

This installs the exact direct pins in `requirements-tts.txt` into
`%LOCALAPPDATA%\ROAR\tts\runtime`. Generate a locked transitive inventory and
run license/vulnerability review before distributing a runtime.

## Prepare a voice pack

The application never downloads models. A release engineer may prepare a pack
on a connected workstation:

```powershell
py -3.12 scripts\prepare_kokoro_voice_pack.py `
  --download --destination C:\staging\roar-kokoro
```

Or prepare from an already populated offline source:

```powershell
py -3.12 scripts\prepare_kokoro_voice_pack.py `
  --source C:\upstream\Kokoro-82M --destination C:\staging\roar-kokoro
```

Both paths verify the canonical manifest. Import the resulting directory from
Settings. The pinned upstream revision and file hashes are in
`tts/assets/kokoro-model-manifest.json`.

## Test

Normal CI is model-free:

```powershell
venv\Scripts\python.exe -m pytest -q -m "not kokoro_model"
```

The real test is opt-in and never downloads:

```powershell
$env:ROAR_KOKORO_TEST_PACK="$env:LOCALAPPDATA\ROAR\tts\kokoro"
venv\Scripts\python.exe -m pytest -q -m kokoro_model `
  tests\test_kokoro_integration.py -s
```

Run the offline benchmark with:

```powershell
venv\Scripts\python.exe scripts\benchmark_kokoro_tts.py `
  --pack "$env:LOCALAPPDATA\ROAR\tts\kokoro"
```

The engine contract lives in `tts/types.py`; tests should normally use
`FakeTTSEngine` and `NullPlayback`. Settings-process tests must continue to
prove that no TTS ML modules are imported.
