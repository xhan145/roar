# tests/test_linux_launcher_assets.py
import pathlib


def test_launcher_runs_app_in_venv():
    sh = pathlib.Path("linux/roar").read_text()
    assert ".venv/bin/activate" in sh and "app.py" in sh


def test_desktop_entry_fields():
    lines = pathlib.Path("linux/roar.desktop").read_text().splitlines()
    fields = dict(line.split("=", 1) for line in lines if "=" in line)

    assert lines[0] == "[Desktop Entry]"
    assert fields["Type"] == "Application"
    assert fields["Name"] == "ROAR"
    assert fields["Exec"] == "ROAR-linux"
    assert fields["Icon"] == "roar"
    assert fields["Terminal"] == "false"
