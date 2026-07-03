"""faster-whisper wrapper: device autodetect, model management, CPU fallback."""
import importlib.util
import os
import pathlib
import sys

from faster_whisper import WhisperModel

GPU_MODEL = "distil-large-v3"
CPU_MODEL = "small.en"


def detect_device() -> str:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def resolve_model(name: str, device: str) -> str:
    if name != "auto":
        return name
    return GPU_MODEL if device == "cuda" else CPU_MODEL


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
            attempts.append((resolve_model(name, "cuda"), "cuda", "float16"))
        attempts.append((resolve_model(name, "cpu"), "cpu", "int8"))
        last_err = None
        for model, dev, compute in attempts:
            try:
                if dev == "cuda":
                    _add_nvidia_dll_dirs()
                self.log(f"loading {model} on {dev} ({compute})...")
                self._model = WhisperModel(model, device=dev, compute_type=compute,
                                           download_root=self.models_dir)
                self.active_model, self.device = model, dev
                return
            except Exception as e:  # missing cuDNN, OOM, bad model name on gpu...
                last_err = e
                self.log(f"load failed for {model} on {dev}: {e}")
        raise RuntimeError(f"could not load any model: {last_err}")

    def _run(self, audio) -> str:
        # beam_size=1 + no VAD: measured 1.66s vs 3.7-4.4s for a ~4s clip on CPU
        # small.en with identical output. The app's RMS gate already rejects
        # silence, which is what vad_filter would protect against.
        segments, _info = self._model.transcribe(
            audio, language=self.language, beam_size=1, vad_filter=False,
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
