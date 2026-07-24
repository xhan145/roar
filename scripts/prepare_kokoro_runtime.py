"""Explicitly create the optional isolated Python 3.12 Read Aloud runtime.

This command may access PyPI (and, for GPU, the PyTorch CUDA index). ROAR itself
never invokes it automatically.

By default it auto-detects an NVIDIA GPU (via `nvidia-smi`) and installs the CUDA
build of torch so Kokoro runs on the GPU; otherwise it installs the CPU build.
Force either with --gpu / --cpu.

    py -3.12 scripts/prepare_kokoro_runtime.py --yes           # auto-detect
    py -3.12 scripts/prepare_kokoro_runtime.py --yes --gpu     # force CUDA
    py -3.12 scripts/prepare_kokoro_runtime.py --yes --cpu     # force CPU
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paths

# torch 2.7.1 is pinned in requirements-tts.txt. Its CUDA wheels live on the
# PyTorch index; cu126 (CUDA 12.6) covers Ada GPUs like the RTX 4060 and only
# needs a reasonably recent NVIDIA display driver (the wheel bundles its own
# CUDA runtime). Override with --cuda-version if a different toolchain is wanted.
TORCH_PIN = "torch==2.7.1"
DEFAULT_CUDA = "cu126"
CUDA_INDEX = "https://download.pytorch.org/whl/{cuda}"


def gpu_available() -> bool:
    """True if an NVIDIA GPU is visible (nvidia-smi on PATH)."""
    return shutil.which("nvidia-smi") is not None


def resolve_gpu(flag):
    """flag is True (--gpu), False (--cpu), or None (auto-detect)."""
    if flag is None:
        return gpu_available()
    return bool(flag)


def torch_install_commands(python, gpu, cuda=DEFAULT_CUDA):
    """pip argv lists to get the right torch build into the runtime.

    GPU: uninstall any existing torch first (pip treats 2.7.1+cpu as satisfying
    torch==2.7.1 and would NOT swap it for the CUDA build), then install the
    pinned torch from the CUDA index. CPU: nothing — requirements-tts.txt pulls
    the CPU wheel from PyPI as before.
    """
    if not gpu:
        return []
    index = CUDA_INDEX.format(cuda=cuda)
    return [
        [python, "-m", "pip", "uninstall", "-y", "torch"],
        [python, "-m", "pip", "install", "--disable-pip-version-check",
         TORCH_PIN, "--index-url", index],
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", default=os.path.dirname(
        os.path.dirname(paths.tts_runtime_python())))
    parser.add_argument("--yes", action="store_true",
                        help="confirm the explicit dependency download")
    accel = parser.add_mutually_exclusive_group()
    accel.add_argument("--gpu", dest="gpu", action="store_true", default=None,
                       help="install CUDA torch (default: auto-detect NVIDIA)")
    accel.add_argument("--cpu", dest="gpu", action="store_false",
                       help="install CPU torch even if an NVIDIA GPU is present")
    parser.add_argument("--cuda-version", default=DEFAULT_CUDA,
                        help=f"PyTorch CUDA channel (default: {DEFAULT_CUDA})")
    args = parser.parse_args()
    if not args.yes:
        parser.error(
            "This explicit setup downloads pinned Python packages. Re-run with --yes.")

    gpu = resolve_gpu(args.gpu)
    print(f"Read Aloud runtime: {'GPU (CUDA ' + args.cuda_version + ')' if gpu else 'CPU'}")

    destination = os.path.abspath(args.destination)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    subprocess.run(["py", "-3.12", "-m", "venv", destination], check=True)
    python = os.path.join(
        destination, "Scripts" if os.name == "nt" else "bin",
        "python.exe" if os.name == "nt" else "python")

    # Install the CUDA torch build BEFORE the rest, so requirements-tts.txt sees
    # torch==2.7.1 already satisfied and leaves the CUDA wheel in place.
    for command in torch_install_commands(python, gpu, args.cuda_version):
        subprocess.run(command, check=True)

    subprocess.run([
        python, "-m", "pip", "install", "--disable-pip-version-check",
        "-r", os.path.join(ROOT, "requirements-tts.txt"),
    ], check=True)

    subprocess.run([
        python, "-c",
        "import kokoro, misaki, torch;"
        "print('Kokoro runtime ready:', "
        "getattr(kokoro, '__version__', '0.9.4'), torch.__version__,"
        "'cuda' if torch.cuda.is_available() else 'cpu')",
    ], check=True)
    print(f"Installed isolated Read Aloud runtime at {destination}")


if __name__ == "__main__":
    main()
