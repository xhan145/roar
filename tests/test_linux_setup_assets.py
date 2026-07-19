# tests/test_linux_setup_assets.py
import pathlib

def test_requirements_linux_has_core_deps():
    txt = pathlib.Path("requirements-linux.txt").read_text()
    for dep in ["faster-whisper", "sounddevice", "pynput", "pyperclip",
                "pywebview", "pystray", "pillow", "numpy",
                "nvidia-cublas-cu12", "nvidia-cudnn-cu12"]:
        assert dep in txt, dep

def test_setup_sh_installs_system_and_python_deps():
    sh = pathlib.Path("linux/setup.sh").read_text()
    for token in ["apt", "python3-gi", "gir1.2-webkit2-4.1",
                  "gir1.2-appindicator3", "libportaudio2", "xclip", "xdotool",
                  "python3-tk", "--system-site-packages", "nvidia-smi"]:
        assert token in sh, token
