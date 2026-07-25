"""GPU-capable Kokoro runtime provisioning.

The isolated runtime shipped CPU-only torch, so the worker always reported
`backend=cpu` even on an NVIDIA machine. These tests pin the pure command-
planning: GPU installs the CUDA torch wheel from the pinned index (and removes
any CPU torch first, because pip treats 2.7.1+cpu as already satisfying
torch==2.7.1 and would not swap it); CPU changes nothing.
"""
import scripts.prepare_kokoro_runtime as prep


def test_cpu_plan_is_empty():
    assert prep.torch_install_commands("py.exe", gpu=False) == []


def test_gpu_plan_force_reinstalls_cuda_wheel_in_one_step():
    cmds = prep.torch_install_commands("py.exe", gpu=True)
    # A SINGLE force-reinstall — never a separate uninstall, so a failed download
    # can't leave the runtime torch-less.
    assert len(cmds) == 1
    cmd = cmds[0]
    assert "uninstall" not in cmd
    assert "--force-reinstall" in cmd
    assert "--no-deps" in cmd
    assert prep.TORCH_PIN in cmd
    assert "--index-url" in cmd
    idx = cmd[cmd.index("--index-url") + 1]
    assert idx == "https://download.pytorch.org/whl/cu126"


def test_gpu_plan_honors_explicit_cuda_version():
    cmd = prep.torch_install_commands("py.exe", gpu=True, cuda="cu128")[0]
    idx = cmd[cmd.index("--index-url") + 1]
    assert idx == "https://download.pytorch.org/whl/cu128"


def test_resolve_gpu_respects_explicit_flag_over_autodetect(monkeypatch):
    monkeypatch.setattr(prep, "gpu_available", lambda: False)
    assert prep.resolve_gpu(True) is True     # explicit --gpu wins
    assert prep.resolve_gpu(False) is False   # explicit --cpu wins


def test_resolve_gpu_auto_uses_nvidia_detection(monkeypatch):
    monkeypatch.setattr(prep, "gpu_available", lambda: True)
    assert prep.resolve_gpu(None) is True
    monkeypatch.setattr(prep, "gpu_available", lambda: False)
    assert prep.resolve_gpu(None) is False
