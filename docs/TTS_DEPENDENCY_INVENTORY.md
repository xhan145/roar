# Read Aloud dependency and redistribution inventory

This is engineering inventory, not legal advice. A release owner must review
the complete resolved environment, upstream NOTICE/license files, voice/model
terms, security posture, and installer presentation before distribution.

## Direct optional runtime pins

| Component | Version | Observed license metadata | Purpose |
|---|---:|---|---|
| Kokoro | 0.9.4 | Apache-2.0 | TTS API/model runtime |
| Misaki | 0.9.4 | Apache-2.0 | English text/phoneme frontend |
| PyTorch | 2.7.1 | BSD-3-Clause | Tensor inference |
| Transformers | 4.53.2 | Apache-2.0 | Kokoro runtime dependency |
| huggingface-hub | 0.33.4 | Apache-2.0 | Dependency only; offline flags and local paths prevent runtime fetching |
| Loguru | 0.7.3 | MIT | Kokoro dependency; worker removes default handlers |
| NumPy | 2.2.6 | BSD-3-Clause | Audio arrays |
| Click | 8.2.1 | BSD-3-Clause | Explicit compatibility pin |

The resolved environment also includes spaCy 3.8.14 (MIT) and other
transitives. `pip freeze`/SBOM, full license texts, NOTICE propagation, and
vulnerability scanning are still mandatory release tasks.

## Main application additions

| Component | Version | Observed license metadata | Purpose |
|---|---:|---|---|
| UIAutomation for Python | 2.0.29 | Apache-2.0 | Safe selected-text access |
| comtypes | 1.4.16 | MIT | Windows UI Automation COM bridge |
| python-sounddevice | 0.5.5 | MIT | Existing playback/capture wrapper |
| PortAudio | bundled transitively | PortAudio license (MIT-style) | Audio I/O |

## Model and voices

Kokoro-82M v1.0 config, model weights, and the four pinned English voice files
are reported upstream as Apache-2.0. ROAR pins revision
`8542409da2986c0ab5d41b3cf0411f7a58caab38` and records SHA-256/size/origin per
file in the canonical manifest. The manifest and the upstream license/NOTICE
must accompany a distributed pack. The preparation script copies ROAR's full
Apache-2.0 text into the pack, and that copy is itself size/hash verified.

Misaki can optionally use eSpeak-NG for fallback phonemization. ROAR does not
bundle it and does not require it for the English MVP. If a future distribution
adds eSpeak-NG, its GPL-3.0-or-later obligations and process/linking boundary
require a separate review.

## Supply-chain controls

- The application does not download dependencies or models.
- Pack imports are fixed-manifest, exact-size, SHA-256 verified, regular-file
  only, traversal/reparse/symlink rejecting, staged, and atomic.
- Official PyTorch weight loading is `weights_only=True`.
- The worker is isolated and receives local explicit model/voice paths.
- Release preparation uses pinned direct requirements and a pinned model
  revision, but hashes for every Python wheel and a complete transitive lock are
  not yet checked into source. That is a release blocker for a distributable
  optional runtime.
