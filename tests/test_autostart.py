import os

import autostart

NAME = f"ROARTest{os.getpid()}"


def test_round_trip_and_cleanup():
    try:
        assert autostart.get(NAME) is None
        autostart.set_enabled(NAME, '"C:\\fake\\ROAR.exe"', True)
        assert autostart.get(NAME) == '"C:\\fake\\ROAR.exe"'
        autostart.set_enabled(NAME, '"C:\\fake\\ROAR.exe"', False)
        assert autostart.get(NAME) is None
        autostart.set_enabled(NAME, "x", False)  # disabling absent key is a no-op
    finally:
        autostart.set_enabled(NAME, "x", False)


def test_default_command_points_at_app():
    cmd = autostart.default_command()
    assert "app.py" in cmd and "pythonw" in cmd.lower()
