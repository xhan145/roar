"""Local hardware acceleration detection + backend/device/compute selection.

Pure and side-effect-free to IMPORT: the heavy ML probes (ctranslate2,
onnxruntime) are lazy-imported INSIDE `detect_acceleration()`, so the settings
process can import this module and call the pure `choose_*` helpers without
dragging in the ML/CUDA stack. `detect_acceleration()` is called only from the
tray/engine process (which already loads ctranslate2).

Never crashes if CUDA, cuDNN, drivers, DirectML, or GPU libraries are missing —
every probe degrades to a safe CPU answer. Logs only hardware/backend facts,
never transcript text.
"""
import os

# Performance presets tune PRECISION + beam width only (never the model), so
# every preset stays within the models the installer already bundles offline —
# no preset ever triggers a download. Fast trades a little accuracy for lower
# latency (int8_float16 on GPU); Accurate widens the beam for quality.
PRESETS = {
    "fast":     {"gpu_compute": "int8_float16", "cpu_compute": "int8", "beam_size": 1},
    "balanced": {"gpu_compute": "float16",      "cpu_compute": "int8", "beam_size": 1},
    "accurate": {"gpu_compute": "float16",      "cpu_compute": "int8", "beam_size": 5},
}
DEFAULT_PRESET = "balanced"

_CUDA_FALLBACK = ("int8_float16", "float16", "int8", "float32")
_CPU_FALLBACK = ("int8", "int8_float32", "float32")


def detect_acceleration() -> dict:
    """Probe the machine. Returns a plain dict (JSON-safe except the two sets):
    {cuda, cuda_count, gpu_name, vram_mb, directml, cpu_compute, cuda_compute}.
    Call only from the engine process. Never raises."""
    accel = {"cuda": False, "cuda_count": 0, "gpu_name": None, "vram_mb": None,
             "directml": False, "cpu_compute": set(), "cuda_compute": set()}
    try:
        import ctranslate2
        n = int(ctranslate2.get_cuda_device_count())
        accel["cuda_count"] = n
        accel["cuda"] = n > 0
        try:
            accel["cpu_compute"] = set(ctranslate2.get_supported_compute_types("cpu"))
        except Exception:
            pass
        if n > 0:
            try:
                accel["cuda_compute"] = set(ctranslate2.get_supported_compute_types("cuda"))
            except Exception:
                pass
    except Exception:
        pass  # no ctranslate2 / no CUDA -> CPU
    try:
        import onnxruntime
        accel["directml"] = "DmlExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:
        pass
    return accel


def _preset(cfg) -> dict:
    name = str((cfg or {}).get("performance_preset", DEFAULT_PRESET)).strip().lower()
    return PRESETS.get(name, PRESETS[DEFAULT_PRESET])


def resolve_preset(cfg) -> dict:
    """Concrete knobs for the active preset (a copy)."""
    return dict(_preset(cfg))


def beam_size_for(cfg) -> int:
    return int(_preset(cfg)["beam_size"])


def choose_cpu_threads(cfg) -> int:
    """Threads for CPU transcription. An explicit `cpu_threads > 0` wins; else
    AUTO returns the physical-core estimate (logical//2 on SMT chips like Ryzen
    and modern Intel). CTranslate2's own default oversubscribes SMT and is
    measurably slower — benchmarked ~20% slower than physical-core count on an
    int8 small.en clip. Capped at 16 (a tiny dictation model doesn't scale past
    that) and floored at 1."""
    req = int((cfg or {}).get("cpu_threads", 0) or 0)
    if req > 0:
        return req
    logical = os.cpu_count() or 4
    est = logical // 2 if logical >= 8 else logical   # SMT -> physical cores
    return max(1, min(16, est))


def choose_best_backend(cfg, accel) -> str:
    """'ct2' (CTranslate2/faster-whisper) or 'onnx_directml'. DirectML is only
    honored when explicitly requested AND actually present; otherwise ct2."""
    cfg = cfg or {}
    if cfg.get("backend") == "onnx_directml" and (accel or {}).get("directml"):
        return "onnx_directml"
    return "ct2"


def choose_device(cfg, accel) -> str:
    """'cuda' or 'cpu', honoring acceleration_mode and real CUDA availability."""
    cfg = cfg or {}
    mode = str(cfg.get("acceleration_mode", "auto")).strip().lower()
    if mode == "cpu":
        return "cpu"
    # auto / gpu / cuda all prefer CUDA when it's actually available
    return "cuda" if (accel or {}).get("cuda") else "cpu"


def choose_compute_type(cfg, device, accel) -> str:
    """Pick a compute type supported by `device`. Honors an explicit override,
    then max_vram_mode, then the preset, then a safe fallback ladder."""
    cfg = cfg or {}
    accel = accel or {}
    supported = accel.get("cuda_compute") if device == "cuda" else accel.get("cpu_compute")
    supported = set(supported or ())

    override = str(cfg.get("compute_type", "auto")).strip().lower()
    if override and override != "auto":
        if not supported or override in supported:
            return override  # trust it if we can't validate; else it's valid

    if device == "cuda":
        want = "int8_float16" if cfg.get("max_vram_mode") else _preset(cfg)["gpu_compute"]
        ladder = _CUDA_FALLBACK
    else:
        want = _preset(cfg)["cpu_compute"]
        ladder = _CPU_FALLBACK

    if not supported or want in supported:
        return want
    for c in ladder:
        if c in supported:
            return c
    return "float32"  # universally supported last resort
