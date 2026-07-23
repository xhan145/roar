"""Explicitly create the optional isolated Python 3.12 Read Aloud runtime.

This command may access PyPI. ROAR itself never invokes it automatically.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", default=os.path.dirname(
        os.path.dirname(paths.tts_runtime_python())))
    parser.add_argument("--yes", action="store_true",
                        help="confirm the explicit dependency download")
    args = parser.parse_args()
    if not args.yes:
        parser.error(
            "This explicit setup downloads pinned Python packages. Re-run with --yes.")
    destination = os.path.abspath(args.destination)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    subprocess.run(
        ["py", "-3.12", "-m", "venv", destination],
        check=True,
    )
    python = os.path.join(
        destination, "Scripts" if os.name == "nt" else "bin",
        "python.exe" if os.name == "nt" else "python")
    subprocess.run([
        python, "-m", "pip", "install", "--disable-pip-version-check",
        "-r", os.path.join(ROOT, "requirements-tts.txt"),
    ], check=True)
    subprocess.run([
        python, "-c",
        "import kokoro, misaki, torch; "
        "print('Kokoro runtime ready:', kokoro.__version__ if "
        "hasattr(kokoro, '__version__') else '0.9.4', torch.__version__)",
    ], check=True)
    print(f"Installed isolated Read Aloud runtime at {destination}")


if __name__ == "__main__":
    main()
