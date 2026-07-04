import os
import subprocess

import pytest

from transcriber import Transcriber, detect_device, resolve_model

SPOKEN = "Hello world. This is a local dictation test."
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_resolve_model_auto():
    assert resolve_model("auto", "cuda") == "distil-large-v3"
    assert resolve_model("auto", "cpu") == "small.en"
    assert resolve_model("tiny.en", "cuda") == "tiny.en"


def test_detect_device_returns_valid():
    assert detect_device() in ("cuda", "cpu")


@pytest.fixture(scope="module")
def speech_wav(tmp_path_factory):
    path = tmp_path_factory.mktemp("audio") / "speech.wav"
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{path}'); "
        f"$s.Speak('{SPOKEN}'); "
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=120)
    assert path.exists() and path.stat().st_size > 10000
    return str(path)


def test_transcribes_real_speech(speech_wav):
    t = Transcriber(model_name="small.en", models_dir=os.path.join(ROOT, "models"),
                    force_device="cpu")
    t.load()
    text = t.transcribe(speech_wav).lower()
    assert "hello" in text
    assert "test" in text


def test_hotwords_reach_model_transcribe():
    t = Transcriber(model_name="small.en", force_device="cpu")

    class StubModel:
        def __init__(self):
            self.kwargs = None

        def transcribe(self, audio, **kwargs):
            self.kwargs = kwargs
            return iter(()), None

    t._model = StubModel()
    t.active_model, t.device = "stub", "cpu"
    t.transcribe("ignored.wav")
    assert t._model.kwargs["hotwords"] is None  # default
    t.hotwords = "ScratchEdge ROAR"
    t.transcribe("ignored.wav")
    assert t._model.kwargs["hotwords"] == "ScratchEdge ROAR"


def test_resolve_model_language_fork():
    assert resolve_model("auto", "cuda", "en") == "distil-large-v3"
    assert resolve_model("auto", "cpu", "en") == "small.en"
    assert resolve_model("auto", "cuda", "es") == "large-v3-turbo"
    assert resolve_model("auto", "cuda", "auto") == "large-v3-turbo"
    assert resolve_model("auto", "cpu", "auto") == "small"
    assert resolve_model("tiny.en", "cuda", "es") == "tiny.en"  # explicit wins


def test_auto_language_reaches_transcribe_as_none():
    t = Transcriber(model_name="small.en", force_device="cpu", language="auto")

    class StubModel:
        def transcribe(self, audio, **kwargs):
            self.kwargs = kwargs
            return iter(()), None

    t._model = StubModel()
    t.active_model, t.device = "stub", "cpu"
    t.transcribe("x.wav")
    assert t._model.kwargs["language"] is None
    t.language = "es"
    t.transcribe("x.wav")
    assert t._model.kwargs["language"] == "es"


def test_seed_dir_resolution(tmp_path, monkeypatch):
    import paths
    from transcriber import seed_dir
    monkeypatch.setattr(paths, "resource_path",
                        lambda name: str(tmp_path / name))
    assert seed_dir("small") is None
    (tmp_path / "models-seed" / "small").mkdir(parents=True)
    assert seed_dir("small").endswith("small")


def test_load_source_order_uses_seed(monkeypatch, tmp_path):
    import paths
    import transcriber as tr
    (tmp_path / "models-seed" / "small").mkdir(parents=True)
    monkeypatch.setattr(paths, "resource_path",
                        lambda name: str(tmp_path / name))
    calls = []

    class StubWM:
        def __init__(self, src, **kw):
            calls.append((src, kw.get("local_files_only")))
            if kw.get("local_files_only"):
                raise RuntimeError("not in cache")

    monkeypatch.setattr(tr, "WhisperModel", StubWM)
    t = tr.Transcriber(model_name="small", force_device="cpu")
    t.load()
    assert calls[0][1] is True                       # cache first
    assert calls[1][0].endswith("small")             # then bundled seed
    assert t.active_model == "small"
