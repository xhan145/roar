# ROAR Desktop — whisper.cpp Vulkan GPU Backend

**Date:** 2026-07-10
**Release target:** v0.21.0
**Status:** Approved; core approach validated by a live spike

## Goal

Give AMD (and Intel) GPU users real transcription acceleration. Today ROAR's
only GPU fast path is NVIDIA CUDA (via CTranslate2); on AMD it falls back to CPU
(~2–3 s per utterance) and the "AMD acceleration" setting is an honest but dead
DirectML scaffold. This adds a **whisper.cpp + Vulkan** backend — Vulkan is
vendor-agnostic (any Vulkan-1.3 GPU: AMD/Intel/NVIDIA) — that runs the model on
the GPU, fully offline.

## Spike evidence (validated on this RTX 4060 via Vulkan)

Downloaded the prebuilt Vulkan build and a GGML model and ran them here:

- `ggml_vulkan: using Vulkan0 backend` — runs on the GPU.
- Correct transcript of `jfk.wav` (11 s clip): "And so my fellow Americans…".
- **337 ms total** (encode 45 ms) — RTF ~0.03.
- `whisper-server.exe` warm-model HTTP round-trip works: `POST /inference`
  (multipart wav) → `{"text":"…"}` over `127.0.0.1` loopback.

So the design below is proven end-to-end, not hypothetical.

## Non-goals / constraints

- No cloud, no telemetry, no account. The Vulkan server binds **loopback only**;
  no audio leaves the machine.
- **CPU/CUDA paths unchanged.** The Vulkan backend is additive and **opt-in**;
  the CTranslate2 CPU int8 fallback always remains.
- **Opt-in download.** Auto-downloading ~150–500 MB silently is user-hostile, so
  the Vulkan backend activates only when the user enables it in Settings; the
  first activation downloads the binary + model (checksum-verified) with the
  existing model-download UX. CPU still works fully offline from install.
- No installer bundling of the binary/model (download-on-first-use).

## Architecture

Slots into the existing backend seam (`backends.TranscriberBackend` Protocol:
`device / active_model / backend / compute_type` + `load()/transcribe()/
description()`), selected by `hardware_accel.choose_best_backend`.

### 1. `whispercpp_assets.py` — download + verify (new)

An asset manifest + a small download/verify/extract helper.

```python
BIN = {
    "url": "https://github.com/jerryshell/whisper.cpp-windows-vulkan-bin/releases/download/v1.0.0/whisper.cpp-windows-vulkan.zip",
    "sha256": "a5d408c72e460433b39875f74a0b6e27e60a3724301d478fe9873db7ff4098e0",
    "size": 18340920,
}
MODELS = {                       # GGML .bin from ggerganov/whisper.cpp on HF
    "base.en":  {"url": ".../ggml-base.en.bin",  "sha256": "<pinned>"},
    "small.en": {"url": ".../ggml-small.en.bin", "sha256": "<pinned>"},
    "base":     {"url": ".../ggml-base.bin",     "sha256": "<pinned>"},
    "small":    {"url": ".../ggml-small.bin",    "sha256": "<pinned>"},
}
```

- Assets live under `%LOCALAPPDATA%\ROAR\vulkan\` (binary, unzipped) and the
  existing models dir (GGML `.bin`).
- Pure, testable helpers: `sha256_of(path)`, `verify(path, expected)`,
  `bin_present(dir)`, `model_present(models_dir, name)`. Network functions
  (`ensure_binary`, `ensure_model`) download to a temp file, verify the sha256,
  then atomically move into place — a failed/partial download never yields a
  "present" asset.
- Default English model for the Vulkan path: **`small.en`** (quality parity with
  the CPU English model, but GPU-accelerated); multilingual → `small`.

### 2. `backends/whispercpp_vulkan.py` — the backend (new)

```python
class WhisperCppVulkanBackend:          # satisfies backends.TranscriberBackend
    backend = "whispercpp_vulkan"
    def load(self): ...
    def transcribe(self, audio) -> str: ...
    def description(self) -> str: ...
    def close(self): ...
```

- `load()`: ensure the binary + model are present (download on first use via
  `whispercpp_assets`); pick a free loopback port; spawn `whisper-server.exe -m
  <model> --host 127.0.0.1 --port <p>` as a subprocess with `CREATE_NO_WINDOW`;
  poll its stdout/health until "listening" (timeout → raise, caller falls back).
  Sets `device="Vulkan (GPU)"`, `active_model`, `compute_type="ggml"`,
  `backend="whispercpp_vulkan"`. The server keeps the model warm (constructed
  once) — matching ROAR's warm-model principle.
- `transcribe(audio)`: `audio` is a float32 mono-16k ndarray (or a path). Write
  it to a temp 16 kHz mono 16-bit WAV, `POST /inference` (multipart, `temperature=0`),
  parse `{"text": …}`, strip, return. Record `last_infer_ms`. Delete the temp WAV.
- `close()`/`__del__`: terminate the server subprocess.
- Never raises to the caller on a transient inference error without first letting
  `app.py` fall back — but a hard `load()` failure raises so selection degrades
  to CTranslate2.

### 3. `hardware_accel.py` — detection + selection (modify)

- `vulkan_runtime_present()`: `ctypes.WinDLL("vulkan-1")` loads (the Vulkan
  loader ships with GPU drivers). Never raises → False.
- `choose_best_backend(cfg, accel)`: return `"whispercpp_vulkan"` **only when the
  user explicitly set `backend="whispercpp_vulkan"` AND `vulkan_runtime_present()`**
  (mirrors the existing explicit-opt-in rule for `onnx_directml`). Auto stays
  CUDA/CPU. This guarantees the big download is user-initiated.

### 4. `app.py` — construct the selected backend (modify)

Where it already special-cases `onnx_directml`, add a `whispercpp_vulkan` branch:
build `WhisperCppVulkanBackend` when selected; on any `load()` failure, log and
fall back to the CTranslate2 `Transcriber` (CPU int8). The reload path
(`diff_config` on `backend` change) already exists.

### 5. `config.py` / settings / diagnostics (modify)

- `backend` accepts `whispercpp_vulkan` (validation).
- Settings: an Acceleration option "GPU — AMD/Intel (Vulkan, experimental)" that
  sets `backend=whispercpp_vulkan`; selecting it triggers the first-use download
  with progress, then a reload. The dead DirectML option is replaced.
- Diagnostics: report backend + device (already surfaces `backend`/`device` from
  the transcriber); add the Vulkan asset presence/version.

## Testing

- **Pure/unit (no GPU):** `sha256_of`/`verify` round-trips; `bin_present`/
  `model_present` logic; manifest URL/sha wellformedness; `choose_best_backend`
  returns `whispercpp_vulkan` only on explicit opt-in + vulkan present, else ct2;
  WAV-writing produces 16 kHz mono 16-bit; `/inference` JSON parsing (feed a
  sample `{"text":…}`). Subprocess + HTTP are mocked.
- **Live (this machine, NVIDIA-Vulkan proxy):** actually spawn `whisper-server`
  against a small model and POST a wav, asserting a non-empty transcript — the
  same round-trip the spike proved. Guard so it skips when the binary isn't
  present (CI/other machines).
- **User (AMD):** confirm real acceleration on the target AMD GPU.

## Rollout

- v0.21.0 ships the code; download-on-first-use means **no installer bloat**.
  The next installer build carries the feature; users opt in and download once.
- Honest labeling: "experimental" until validated on real AMD hardware.

## Constraints (verbatim)

- 100% local; loopback-only server; no telemetry/accounts.
- CPU/CUDA unchanged; Vulkan is additive + opt-in; CTranslate2 CPU fallback
  always present.
- No private keys/secrets; MIT-licensed binary (whisper.cpp).
- Never claim AMD acceleration works until the user confirms on AMD silicon.
