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


def test_gpu_plan_uninstalls_then_installs_cuda_wheel():
    cmds = prep.torch_install_commands("py.exe", gpu=True)
    assert len(cmds) == 2
    # first: force the CPU torch out so the CUDA build can take its place
    assert cmds[0][:5] == ["py.exe", "-m", "pip", "uninstall", "-y"]
    assert cmds[0][-1] == "torch"
    # second: install the pinned torch from the CUDA index
    assert prep.TORCH_PIN in cmds[1]
    assert "--index-url" in cmds[1]
    idx = cmds[1][cmds[1].index("--index-url") + 1]
    assert idx == "https://download.pytorch.org/whl/cu126"


def test_gpu_plan_honors_explicit_cuda_version():
    cmds = prep.torch_install_commands("py.exe", gpu=True, cuda="cu128")
    idx = cmds[1][cmds[1].index("--index-url") + 1]
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
