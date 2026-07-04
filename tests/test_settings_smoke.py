import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_settings_smoke():
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--settings", "--smoke"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = proc.communicate(timeout=120)
    assert "ROAR: settings window ready" in out
    assert "navs=9" in out and "priv=1" in out and "privnav=1" in out
    assert "insnav=1" in out
    assert "vocab=1" in out
    assert "ovl=1" in out
    assert "lang=1" in out
    assert "snip=1" in out and "snipnav=1" in out
    assert "cleanup=1" in out and "discourse=1" in out
    assert "updates=1" in out and "credits=1" in out
    assert "ROAR: settings closed" in out
    assert proc.returncode == 0
