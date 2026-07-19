"""Single source of truth for the running OS. Import this instead of testing
sys.platform ad hoc, so backend selection is consistent and mockable."""
import sys

def is_windows() -> bool:
    return sys.platform.startswith("win")

def is_linux() -> bool:
    return sys.platform.startswith("linux")

def name() -> str:
    if is_windows():
        return "windows"
    if is_linux():
        return "linux"
    return "other"
