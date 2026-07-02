import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_smoke_startup_and_clean_exit():
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--smoke"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        out, _ = proc.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    assert "FlowLocal: hotkeys registered" in out
    assert "FlowLocal: tray ready" in out
    assert "FlowLocal: model loaded" in out
    assert "FlowLocal: clean exit" in out
    assert proc.returncode == 0
