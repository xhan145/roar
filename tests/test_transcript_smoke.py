"""The transcript window opens, renders its controls, and exits cleanly."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_transcript_smoke():
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--transcript", "--smoke"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = proc.communicate(timeout=120)
    assert "ROAR: transcript window ready" in out
    assert "ui=1" in out
    assert "ROAR: transcript closed" in out
    assert proc.returncode == 0
