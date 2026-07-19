# tests/test_linux_launcher_assets.py
import pathlib

def test_launcher_runs_app_in_venv():
    sh = pathlib.Path("linux/roar").read_text()
    assert ".venv/bin/activate" in sh and "app.py" in sh

def test_desktop_entry_fields():
    d = pathlib.Path("linux/roar.desktop").read_text()
    for token in ["[Desktop Entry]", "Type=Application", "Name=ROAR", "Exec="]:
        assert token in d, token

def test_appimage_recipe_uses_pyinstaller_and_appimagetool():
    sh = pathlib.Path("linux/build_appimage.sh").read_text()
    assert "pyinstaller" in sh.lower() and "appimagetool" in sh.lower()
