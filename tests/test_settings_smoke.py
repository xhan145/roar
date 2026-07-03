import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_settings_smoke():
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--settings", "--smoke"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = proc.communicate(timeout=120)
    assert "FlowLocal: settings window ready" in out
    assert "navs=8" in out and "priv=1" in out and "privnav=1" in out
    assert "insnav=1" in out
    assert "vocab=1" in out
    assert "FlowLocal: settings closed" in out
    assert proc.returncode == 0
