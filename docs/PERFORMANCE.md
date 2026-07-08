# Performance & GPU acceleration

ROAR transcribes locally with faster-whisper / CTranslate2. Acceleration is
automatic, optional, and always falls back to CPU. No cloud, no telemetry, no
network in the transcription path.

## Backends
- **NVIDIA CUDA** — automatic when a CUDA GPU + the bundled cuBLAS/cuDNN wheels
  are present (no system CUDA toolkit needed). `float16` (Balanced) or
  `int8_float16` (Fast); both fit an 8 GB card with the default `distil-large-v3`.
- **CPU** — `int8`, `small.en`. Always available; the safety net. A CUDA load
  or inference failure falls back here automatically.
- **AMD / DirectML** — experimental and **currently unavailable** (see below).

## Presets (Settings → Transcription → Performance)
| Preset | Compute (GPU / CPU) | Beam | For |
|---|---|---|---|
| Fast | int8_float16 / int8 | 1 | Lowest latency |
| Balanced (default) | float16 / int8 | 1 | Current behavior — unchanged |
| Accurate | float16 / int8 | 5 | Best quality |

Presets tune **precision + beam width only, never the model**, so no preset ever
triggers a download. Also configurable: **Acceleration** (Auto / GPU / CPU) and
**Compute type** (Auto / float16 / int8_float16 / int8). Auto chooses the fastest
working local backend on this machine; if the GPU fails, ROAR falls back to CPU
and Diagnostics shows the reason.

## Measured (RTX 4060 Laptop, 8 GB; 4.9 s clip, p50)
| backend | model | infer ms | RTF |
|---|---|---|---|
| CPU int8 | small.en | 2079 | 0.42 |
| CUDA float16 (Balanced) | distil-large-v3 | 288 | 0.06 |
| CUDA int8_float16 (Fast) | distil-large-v3 | 259 | 0.05 |

CUDA is ~8× faster than CPU; the Fast preset is ~10% under Balanced. Reproduce
(offline, local models only):

```
venv/Scripts/python.exe scripts/benchmark_transcription.py
```

The model is loaded **once and kept warm** for the process lifetime (with a
startup warm-up inference) — it is never reloaded per dictation, only when you
change the model/language/acceleration settings. Real release-to-text latency is
instrumented and surfaced in Diagnostics + the Home dashboard.

## AMD / DirectML — honest status
ROAR's GPU acceleration uses **NVIDIA CUDA via CTranslate2**. AMD/DirectML
acceleration is **experimental and not currently available**: the shipped models
are CTranslate2-format and cannot run on DirectML; a DirectML path would require
a separate ~1 GB Whisper ONNX model, a swap to `onnxruntime-directml` (no
verified cp314 Windows wheels, and mutually exclusive with the CPU `onnxruntime`
the VAD uses), and a hand-rolled autoregressive decode loop — none of which can
be validated on the current hardware (no AMD GPU present). DirectML Whisper is
also frequently slower than ROAR's existing CPU int8 path. The backend seam
(`backends/onnx_directml_spike.py`) is in place for a future implementation;
today, selecting DirectML cleanly falls back to CPU/CUDA and reports the reason.

## CPU performance (incl. AMD Ryzen)
On machines without an NVIDIA GPU, transcription runs on the CPU (int8). ROAR
sets CTranslate2's `cpu_threads` to the **physical-core estimate** (`logical // 2`
on SMT chips like Ryzen and modern Intel, capped at 16) instead of ct2's default,
which oversubscribes SMT and is measurably slower. Measured (16-logical laptop,
small.en int8, 4.9 s clip, p50): ct2 default **2197 ms** / all-16-threads
**2561 ms** vs physical-core count **~1720–1770 ms** — **~20% faster**.

On a uniform Ryzen (e.g. 8C/16T → 8 threads, 6C/12T → 6) this maps exactly to the
physical cores, which is the sweet spot. Override via the `cpu_threads` config key
(`0` = auto; a positive value forces that thread count). The active count shows in
Diagnostics.

## Packaging
The CUDA runtime ships as pip `nvidia-*` wheels (cuBLAS + cuDNN 9) — no system
CUDA toolkit required. CPU-only installs work unchanged.
`requirements-directml.txt` is **opt-in only** and must never be added to
`requirements.txt` (it would corrupt the plain `onnxruntime` the VAD relies on).
