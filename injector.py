"""Text injection: SendInput unicode typing (primary), clipboard paste (fallback)."""
import time

import keyboard

MAX_PASTE_CHARS = 100000


def prepare(text):
    """Final injectable string (trailing space added), or None when empty.
    A bare newline (spoken 'new line' alone) is injectable."""
    if not text:
        return None
    if not text.strip():
        return text if "\n" in text else None
    return text if text.endswith("\n") else text + " "


def inject_text(text, paste_fallback=False) -> bool:
    out = prepare(text)
    if out is None:
        return False
    if paste_fallback:
        return _paste(out)
    keyboard.write(out, delay=0)  # SendInput with KEYEVENTF_UNICODE
    return True


def _paste(out) -> bool:
    import pyperclip
    if len(out) > MAX_PASTE_CHARS:
        return False
    old = None
    copied = False
    try:
        old = pyperclip.paste()
    except Exception:
        pass
    try:
        pyperclip.copy(out)
        copied = True
        keyboard.send("ctrl+v")
        time.sleep(0.8)  # let the target app read the clipboard before restoring
    except Exception:
        return False
    finally:
        try:
            if old is not None:
                pyperclip.copy(old)
        except Exception:
            pass
    return copied
