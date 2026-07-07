from types import SimpleNamespace

from app import ROARApp


def _reason(device=None, cuda_detected=False, backend=None, cfg=None):
    fake = SimpleNamespace(
        transcriber=SimpleNamespace(device=device, cuda_detected=cuda_detected,
                                    backend=backend),
        cfg=cfg or {})
    return ROARApp._accel_fallback_reason(fake)


def test_no_reason_when_running_on_gpu():
    assert _reason("cuda", True, "ct2", {"acceleration_mode": "auto"}) == ""


def test_reason_when_gpu_present_but_running_on_cpu():
    assert "CPU" in _reason("cpu", True, "ct2", {"acceleration_mode": "auto"})


def test_no_reason_when_user_chose_cpu():
    assert _reason("cpu", True, "ct2", {"acceleration_mode": "cpu"}) == ""


def test_reason_when_directml_requested_but_unavailable():
    r = _reason("cuda", True, "ct2",
                {"acceleration_mode": "auto", "backend": "onnx_directml"})
    assert "DirectML" in r


def test_defensive_with_missing_transcriber_attrs():
    # a stub transcriber missing every accel attr must not crash -> empty reason
    fake = SimpleNamespace(transcriber=SimpleNamespace(), cfg={})
    assert ROARApp._accel_fallback_reason(fake) == ""
