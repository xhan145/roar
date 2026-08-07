import subprocess
import sys
import textwrap


IMPORT_STUBS = r'''
import sys
import types

pystray = types.ModuleType("pystray")
pystray.Icon = type("Icon", (), {})
pystray.Menu = type("Menu", (), {})
pystray.MenuItem = type("MenuItem", (), {})
sys.modules["pystray"] = pystray
sys.modules["sounddevice"] = types.ModuleType("sounddevice")
faster_whisper = types.ModuleType("faster_whisper")
faster_whisper.WhisperModel = object
sys.modules["faster_whisper"] = faster_whisper

import app

class BrokenIcon:
    def run(self, setup):
        raise RuntimeError("notification cleanup failed")
'''


def _run_case(case):
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(IMPORT_STUBS + case)],
        text=True,
        capture_output=True,
    )


def test_tray_cleanup_error_is_nonfatal_after_shutdown_starts():
    result = _run_case(r'''
app_instance = app.ROARApp.__new__(app.ROARApp)
app_instance.icon = BrokenIcon()
app_instance._on_tray_ready = lambda icon: None
app_instance._shutting_down = True
messages = []
app_instance.log = messages.append
app_instance._run_tray()
assert messages[-1] == "clean exit"
assert "notification cleanup failed" in messages[-2]
''')

    assert result.returncode == 0, result.stdout + result.stderr


def test_tray_runtime_error_still_propagates_before_shutdown():
    result = _run_case(r'''
app_instance = app.ROARApp.__new__(app.ROARApp)
app_instance.icon = BrokenIcon()
app_instance._on_tray_ready = lambda icon: None
app_instance._shutting_down = False
app_instance.log = lambda message: None
try:
    app_instance._run_tray()
except RuntimeError as exc:
    assert str(exc) == "notification cleanup failed"
else:
    raise AssertionError("tray runtime error was swallowed")
''')

    assert result.returncode == 0, result.stdout + result.stderr
