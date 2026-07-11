import hashlib
import os
import wave

import numpy as np
import pytest

import hardware_accel as ha
import whispercpp_assets as assets
from backends import TranscriberBackend
from backends import whispercpp_vulkan as wv


# -- asset helpers (pure) --------------------------------------------------

def test_model_for_language():
    assert assets.model_for("en") == "small.en"     # English -> English-only model
    assert assets.model_for("auto") == "small"      # auto -> multilingual (ROAR policy)
    assert assets.model_for("fr") == "small"


def test_sha256_and_verify_roundtrip(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"roar" * 1000)
    digest = hashlib.sha256(b"roar" * 1000).hexdigest()
    assert assets.sha256_of(str(p)) == digest
    assert assets.verify(str(p), digest) is True
    assert assets.verify(str(p), "0" * 64) is False
    assert assets.verify(str(tmp_path / "missing.bin"), digest) is False


def test_bin_and_model_presence(tmp_path):
    assert assets.bin_present(str(tmp_path)) is False
    (tmp_path / assets.SERVER_EXE).write_bytes(b"x")
    assert assets.bin_present(str(tmp_path)) is True
    # model_present requires a matching checksum, not just existence
    mp = assets.model_path(str(tmp_path), "tiny.en")
    with open(mp, "wb") as f:
        f.write(b"not the real model")
    assert assets.model_present(str(tmp_path), "tiny.en") is False


def test_manifest_wellformed():
    assert assets.BIN["url"].startswith("https://") and len(assets.BIN["sha256"]) == 64
    for name, spec in assets.MODELS.items():
        assert spec["url"].startswith("https://")
        assert len(spec["sha256"]) == 64


# -- backend helpers (pure) ------------------------------------------------

def test_write_wav_16k_roundtrip(tmp_path):
    p = str(tmp_path / "a.wav")
    samples = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    wv.write_wav_16k(samples, p)
    with wave.open(p, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 16000
        assert w.getnframes() == 5


def test_parse_response():
    assert wv.parse_response({"text": "  hello world  "}) == "hello world"
    assert wv.parse_response({}) == ""


def test_lang_flag():
    assert wv._lang_flag("small.en", "auto") == "en"     # .en model forces en
    assert wv._lang_flag("small", "auto") == "auto"
    assert wv._lang_flag("small", "fr") == "fr"


# -- selection -------------------------------------------------------------

def test_selector_picks_vulkan_only_on_explicit_optin(monkeypatch):
    monkeypatch.setattr(ha, "vulkan_runtime_present", lambda: True)
    assert ha.choose_best_backend({"backend": "whispercpp_vulkan"}, {}) == "whispercpp_vulkan"
    # not opted in -> stays ct2 even if vulkan is present
    assert ha.choose_best_backend({}, {}) == "ct2"
    assert ha.choose_best_backend({"backend": "ct2"}, {}) == "ct2"


def test_selector_falls_back_when_vulkan_absent(monkeypatch):
    monkeypatch.setattr(ha, "vulkan_runtime_present", lambda: False)
    assert ha.choose_best_backend({"backend": "whispercpp_vulkan"}, {}) == "ct2"


def test_backend_satisfies_protocol():
    b = wv.WhisperCppVulkanBackend(models_dir="models", language="en")
    assert isinstance(b, TranscriberBackend)
    assert b.backend == "whispercpp_vulkan"
    assert b.description() == "no model"


# -- live proxy (opt-in): real server round-trip on this machine's GPU -----

@pytest.mark.skipif(not os.environ.get("ROAR_VULKAN_LIVE"),
                    reason="set ROAR_VULKAN_LIVE=<dir with binary+model+jfk.wav> to run")
def test_live_vulkan_roundtrip():
    """Exercises the real whisper-server round-trip against a pre-downloaded
    binary/model (the same path the spike proved). ROAR_VULKAN_LIVE points at a
    dir containing the unzipped binary, ggml-tiny.en.bin, and jfk.wav."""
    live = os.environ["ROAR_VULKAN_LIVE"]
    import paths
    monkey_dir = live
    b = wv.WhisperCppVulkanBackend(model_name="tiny.en",
                                   models_dir=live, language="en")
    # point vulkan_dir at the live binary dir
    orig = paths.vulkan_dir
    paths.vulkan_dir = lambda: monkey_dir
    try:
        b.load()
        text = b.transcribe(os.path.join(live, "jfk.wav"))
        assert "country" in text.lower()
    finally:
        b.close()
        paths.vulkan_dir = orig
