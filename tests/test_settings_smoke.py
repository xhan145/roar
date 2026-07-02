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
    assert "FlowLocal: settings probe navs=7 version=0.2.0" in out
    assert "FlowLocal: settings closed" in out
    assert proc.returncode == 0
