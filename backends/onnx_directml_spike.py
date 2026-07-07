"""EXPERIMENTAL DirectML (AMD / Intel / NVIDIA Windows GPU) Whisper backend — SPIKE.

STATUS: unavailable. This is a documented placeholder, NOT a working backend.
Selecting `backend="onnx_directml"` cleanly falls back to CTranslate2/CPU, and
the diagnostics report "AMD/DirectML acceleration unavailable (experimental)".
No false claim of AMD support is ever made.

Why it is a spike and not an implementation (verified on this repo/machine):
  * CTranslate2 (faster-whisper's engine) has NO DirectML/ROCm path, so the
    models ROAR already bundles (CTranslate2 format) cannot run on DirectML.
  * A DirectML path needs `onnxruntime-directml` — this venv ships plain
    `onnxruntime` (providers: CPU/Azure only, no `DmlExecutionProvider`) — PLUS a
    separate Whisper ONNX encoder + decoder-with-past (~1 GB), a hand-rolled
    autoregressive KV-cache decode + beam search, tokenizer, language/timestamp
    handling, warm-up, and CPU-fallback parity.
  * Python here is cp314; `onnxruntime-directml` / `optimum` / `torch` cp314
    Windows wheels are unverified/likely missing.
  * There is no AMD GPU on the dev machine, so no DirectML result could be
    validated or benchmarked — and DirectML Whisper is frequently SLOWER than
    ROAR's existing CPU int8 path.

To implement later: add `onnxruntime-directml` (see requirements-directml.txt),
obtain/convert a Whisper ONNX model, implement the decode loop (or via Optimum),
make this class satisfy `backends.TranscriberBackend`, and register it in
`hardware_accel.choose_best_backend`.
"""

UNAVAILABLE = "AMD/DirectML acceleration unavailable (experimental)"


def directml_available() -> bool:
    """True only if onnxruntime actually exposes the DirectML provider here.
    Never raises."""
    try:
        import onnxruntime
        return "DmlExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:
        return False


class DirectMLWhisperBackend:
    """Placeholder backend. `load()`/`transcribe()` refuse; the selector falls
    back to CTranslate2/CPU. Kept API-shaped so a real implementation can slot
    in without touching callers."""
    backend = "onnx_directml"

    def __init__(self, *args, **kwargs):
        self.device = None
        self.active_model = None
        self.compute_type = None

    def available(self) -> bool:
        return directml_available()

    def load(self) -> None:
        raise RuntimeError(UNAVAILABLE)

    def transcribe(self, audio) -> str:
        raise RuntimeError(UNAVAILABLE)

    def description(self) -> str:
        return UNAVAILABLE
