import pytest

import hardware_accel as ha
import transcriber
from backends import TranscriberBackend
from backends import onnx_directml_spike as dml


def test_directml_unavailable_in_this_env():
    # plain onnxruntime here -> no DmlExecutionProvider
    assert dml.directml_available() is False


def test_directml_backend_refuses_cleanly():
    b = dml.DirectMLWhisperBackend()
    assert "unavailable" in b.description().lower()
    assert b.available() is False
    with pytest.raises(RuntimeError):
        b.load()
    with pytest.raises(RuntimeError):
        b.transcribe("x")


def test_selector_falls_back_to_ct2_when_directml_absent():
    assert ha.choose_best_backend({"backend": "onnx_directml"},
                                  {"cuda": True, "directml": False}) == "ct2"
    # only honored when actually present
    assert ha.choose_best_backend({"backend": "onnx_directml"},
                                  {"cuda": False, "directml": True}) == "onnx_directml"


def test_faster_whisper_backend_alias_and_shape():
    assert transcriber.FasterWhisperBackend is transcriber.Transcriber
    t = transcriber.FasterWhisperBackend(model_name="small.en")
    for m in ("load", "transcribe", "description"):
        assert callable(getattr(t, m))
    for a in ("device", "active_model", "backend", "compute_type",
              "beam_size", "last_infer_ms"):
        assert hasattr(t, a)
    assert isinstance(t, TranscriberBackend)  # satisfies the runtime protocol
