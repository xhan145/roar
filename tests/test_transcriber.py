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
