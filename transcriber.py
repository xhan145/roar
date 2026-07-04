"""faster-whisper wrapper: device autodetect, model management, CPU fallback."""
import importlib.util
import os
import pathlib
import sys

from faster_whisper import WhisperModel

import paths

GPU_MODEL_EN = "distil-large-v3"     # English-only distillation
GPU_MODEL_MULTI = "large-v3-turbo"   # multilingual, fast
CPU_MODEL_EN = "small.en"
CPU_MODEL_MULTI = "small"


def detect_device() -> str:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def resolve_model(name: str, device: str, language: str = "en") -> str:
    if name != "auto":
        return name
    english = language == "en"
    if device == "cuda":
        return GPU_MODEL_EN if english else GPU_MODEL_MULTI
    return CPU_MODEL_EN if english else CPU_MODEL_MULTI


def seed_dir(model_name):
    """Bundled offline copy of a model, when the installer shipped one."""
    p = paths.resource_path(os.path.join("models-seed", model_name))
    return p if os.path.isdir(p) else None


def _add_nvidia_dll_dirs():
    """Make pip-installed cuBLAS/cuDNN DLLs (requirements-gpu.txt) loadable.

    ctranslate2 loads these via a plain LoadLibrary, which searches PATH but
    NOT os.add_dll_directory() entries — so prepend to PATH as well.
    """
    bin_dirs = []
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        try:
            spec = importlib.util.find_spec(pkg)
        except (ImportError, ModuleNotFoundError):
            continue
        if spec and spec.submodule_search_locations:
            bin_dirs.append(pathlib.Path(list(spec.submodule_search_locations)[0]) / "bin")
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: collected nvidia packages live under _internal/
        bundle = pathlib.Path(sys.executable).parent / "_internal" / "nvidia"
        bin_dirs.extend(bundle.glob("*/bin"))
    for bin_dir in bin_dirs:
        if bin_dir.is_dir():
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


class Transcriber:
    def __init__(self, model_name="auto", models_dir="models", language="en",
                 log=print, force_device=None):
        self.requested = model_name
        self.models_dir = models_dir
        self.language = language
        self.log = log
        self.force_device = force_device
        self._model = None
        self.active_model = None
        self.device = None
        self.hotwords = None  # merged vocabulary string; set by the app

    def description(self) -> str:
        if self._model is None:
            return "no model"
        return f"{self.active_model} ({self.device})"

    def load(self, model_name=None):
        """Load the model, trying CUDA first (when present), falling back to CPU."""
        name = model_name or self.requested
        device = self.force_device or detect_device()
        attempts = []
        if device == "cuda":
            attempts.append((resolve_model(name, "cuda", self.language),
                             "cuda", "float16"))
        attempts.append((resolve_model(name, "cpu", self.language),
                         "cpu", "int8"))
        last_err = None
        for model, dev, compute in attempts:
            # source order: local cache -> installer-bundled seed -> download
            sources = [(model, {"download_root": self.models_dir,
                                "local_files_only": True})]
            seed = seed_dir(model)
            if seed:
                sources.append((seed, {}))
            sources.append((model, {"download_root": self.models_dir}))
            for src, extra in sources:
                try:
                    if dev == "cuda":
                        _add_nvidia_dll_dirs()
                    self.log(f"loading {model} on {dev} ({compute})...")
                    self._model = WhisperModel(src, device=dev,
                                               compute_type=compute, **extra)
                    self.active_model, self.device = model, dev
                    return
                except Exception as e:  # not cached, missing cuDNN, OOM...
                    last_err = e
            self.log(f"load failed for {model} on {dev}: {last_err}")
        raise RuntimeError(f"could not load any model: {last_err}")

    def _run(self, audio) -> str:
        # beam_size=1 + no VAD: measured 1.66s vs 3.7-4.4s for a ~4s clip on CPU
        # small.en with identical output. The app's RMS gate already rejects
        # silence, which is what vad_filter would protect against.
        segments, _info = self._model.transcribe(
            audio,
            language=None if self.language == "auto" else self.language,
            beam_size=1, vad_filter=False,
            hotwords=self.hotwords)
        return " ".join(seg.text.strip() for seg in segments).strip()

    def transcribe(self, audio) -> str:
        """audio: float32 mono 16 kHz ndarray, or a path to an audio file."""
        if self._model is None:
            raise RuntimeError("model not loaded")
        try:
            return self._run(audio)
        except Exception as e:
            if self.device == "cuda":
                # CUDA can fail only at inference time (e.g. missing cudnn ops).
                self.log(f"cuda inference failed ({e}); retrying on cpu")
                self.force_device = "cpu"
                self.load()
                return self._run(audio)
            raise
