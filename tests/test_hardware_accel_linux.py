import hardware_accel as hw


def test_vulkan_never_present_on_linux(monkeypatch):
    monkeypatch.setattr(hw.platform_id, "is_linux", lambda: True)
    assert hw.vulkan_runtime_present() is False


def test_best_backend_not_vulkan_on_linux(monkeypatch):
    monkeypatch.setattr(hw.platform_id, "is_linux", lambda: True)
    cfg = {"backend": "whispercpp_vulkan"}  # even if the user asked for it
    assert hw.choose_best_backend(cfg, {}) != "whispercpp_vulkan"


def test_cuda_device_preferred_when_present(monkeypatch):
    monkeypatch.setattr(hw.platform_id, "is_linux", lambda: True)
    accel = {"cuda": True, "cuda_count": 1}
    assert hw.choose_device({}, accel) == "cuda"


def test_cpu_when_no_cuda(monkeypatch):
    monkeypatch.setattr(hw.platform_id, "is_linux", lambda: True)
    assert hw.choose_device({}, {"cuda": False, "cuda_count": 0}) == "cpu"
