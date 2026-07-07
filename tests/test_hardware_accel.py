import json

import config as config_mod
import hardware_accel as ha

CUDA = {"cuda": True, "cuda_count": 1, "directml": False,
        "cuda_compute": {"float16", "int8_float16", "int8", "bfloat16", "float32"},
        "cpu_compute": {"int8", "int8_float32", "float32"}}
NOCUDA = {"cuda": False, "cuda_count": 0, "directml": False,
          "cuda_compute": set(), "cpu_compute": {"int8", "int8_float32", "float32"}}


# ---- detect_acceleration (mock ctranslate2; never crashes) ----
def test_detect_never_crashes_shape():
    a = ha.detect_acceleration()
    for k in ("cuda", "cuda_count", "directml", "cpu_compute", "cuda_compute"):
        assert k in a
    assert isinstance(a["cuda"], bool)


def test_detect_cuda_available(monkeypatch):
    import ctranslate2
    monkeypatch.setattr(ctranslate2, "get_cuda_device_count", lambda: 1)
    monkeypatch.setattr(ctranslate2, "get_supported_compute_types",
                        lambda d: {"float16", "int8"} if d == "cuda" else {"int8"})
    a = ha.detect_acceleration()
    assert a["cuda"] is True and a["cuda_count"] == 1
    assert "float16" in a["cuda_compute"]


def test_detect_cuda_missing(monkeypatch):
    import ctranslate2
    monkeypatch.setattr(ctranslate2, "get_cuda_device_count", lambda: 0)
    a = ha.detect_acceleration()
    assert a["cuda"] is False and a["cuda_count"] == 0


def test_detect_survives_probe_exception(monkeypatch):
    import ctranslate2
    def boom():
        raise RuntimeError("driver missing")
    monkeypatch.setattr(ctranslate2, "get_cuda_device_count", boom)
    a = ha.detect_acceleration()
    assert a["cuda"] is False  # degraded to CPU, no crash


# ---- choose_device ----
def test_choose_device_auto_prefers_cuda_when_present():
    assert ha.choose_device({"acceleration_mode": "auto"}, CUDA) == "cuda"
    assert ha.choose_device({"acceleration_mode": "auto"}, NOCUDA) == "cpu"


def test_choose_device_cpu_mode_forces_cpu_even_with_gpu():
    assert ha.choose_device({"acceleration_mode": "cpu"}, CUDA) == "cpu"


def test_choose_device_gpu_mode_falls_back_without_cuda():
    assert ha.choose_device({"acceleration_mode": "gpu"}, NOCUDA) == "cpu"
    assert ha.choose_device({"acceleration_mode": "gpu"}, CUDA) == "cuda"


# ---- choose_compute_type ----
def test_compute_balanced_cuda_is_float16():
    assert ha.choose_compute_type({"performance_preset": "balanced"}, "cuda", CUDA) == "float16"


def test_compute_fast_cuda_is_int8_float16():
    assert ha.choose_compute_type({"performance_preset": "fast"}, "cuda", CUDA) == "int8_float16"


def test_compute_max_vram_overrides_to_int8_float16():
    cfg = {"performance_preset": "accurate", "max_vram_mode": True}
    assert ha.choose_compute_type(cfg, "cuda", CUDA) == "int8_float16"


def test_compute_explicit_override_when_supported():
    assert ha.choose_compute_type({"compute_type": "bfloat16"}, "cuda", CUDA) == "bfloat16"


def test_compute_unsupported_override_falls_back():
    # user forces float16 on a card that lacks it -> ladder picks a supported one
    weak = {"cuda": True, "cuda_compute": {"int8", "float32"}, "cpu_compute": {"int8"}}
    got = ha.choose_compute_type({"compute_type": "float16"}, "cuda", weak)
    assert got in weak["cuda_compute"]


def test_compute_cpu_is_int8():
    assert ha.choose_compute_type({"performance_preset": "balanced"}, "cpu", NOCUDA) == "int8"


def test_compute_empty_support_trusts_want():
    # detection failed (empty sets) -> return the wanted type, let ct2 + the
    # transcriber's load-ladder handle any real failure
    blank = {"cuda": True, "cuda_compute": set(), "cpu_compute": set()}
    assert ha.choose_compute_type({"performance_preset": "balanced"}, "cuda", blank) == "float16"


# ---- backend + beam ----
def test_backend_defaults_to_ct2():
    assert ha.choose_best_backend({}, CUDA) == "ct2"
    assert ha.choose_best_backend({"backend": "auto"}, CUDA) == "ct2"


def test_backend_directml_only_when_present():
    assert ha.choose_best_backend({"backend": "onnx_directml"}, NOCUDA) == "ct2"  # absent -> ct2
    dml = dict(NOCUDA, directml=True)
    assert ha.choose_best_backend({"backend": "onnx_directml"}, dml) == "onnx_directml"


def test_beam_size_by_preset():
    assert ha.beam_size_for({"performance_preset": "fast"}) == 1
    assert ha.beam_size_for({"performance_preset": "balanced"}) == 1
    assert ha.beam_size_for({"performance_preset": "accurate"}) == 5
    assert ha.beam_size_for({}) == 1  # default balanced


# ---- config keys ----
def test_new_accel_config_defaults(tmp_path):
    cfg = config_mod.load(str(tmp_path / "c.json"))
    assert cfg["acceleration_mode"] == "auto"
    assert cfg["performance_preset"] == "balanced"
    assert cfg["compute_type"] == "auto"
    assert cfg["backend"] == "auto"
    assert cfg["gpu_device_index"] == 0
    assert cfg["prefer_low_latency"] is True
    assert cfg["max_vram_mode"] is False


def test_accel_config_accepts_valid(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"acceleration_mode": "cpu", "performance_preset": "fast",
                             "compute_type": "int8_float16", "gpu_device_index": 2}),
                 encoding="utf-8")
    cfg = config_mod.load(str(p))
    assert cfg["acceleration_mode"] == "cpu"
    assert cfg["performance_preset"] == "fast"
    assert cfg["compute_type"] == "int8_float16"
    assert cfg["gpu_device_index"] == 2


def test_accel_config_rejects_garbage(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"acceleration_mode": "warp", "performance_preset": "ludicrous",
                             "backend": "quantum", "compute_type": "int4",
                             "gpu_device_index": "-5"}), encoding="utf-8")
    cfg = config_mod.load(str(p))
    assert cfg["acceleration_mode"] == "auto"      # garbage -> default
    assert cfg["performance_preset"] == "balanced"
    assert cfg["backend"] == "auto"
    assert cfg["compute_type"] == "auto"
    assert cfg["gpu_device_index"] == 0            # int("-5") clamped to 0
