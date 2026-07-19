"""Text injection: platform backend types into the focused app, with a
clipboard-paste fallback. Backend picked by platform_id + ROAR_INJECT_BACKEND."""
import os

import platform_id

# Backstop: never fire a runaway injection into the focused app. Real
# dictations are a few hundred chars; snippets are capped at 2000 and the
# {clipboard} variable at 10k, so anything near this is a bug upstream.
MAX_PASTE = 100_000


def prepare(text):
    """Final injectable string (trailing space added), or None when empty.
    A bare newline (spoken 'new line' alone) is injectable."""
    if not text:
        return None
    if not text.strip():
        return text if "\n" in text else None
    return text if text.endswith("\n") else text + " "


def _select_backend():
    if platform_id.is_linux():
        from inject_x11 import X11Injector          # Task 6
        return X11Injector(os.environ.get("ROAR_INJECT_BACKEND", "pynput"))
    from inject_windows import WindowsInjector
    return WindowsInjector()


_BACKEND = _select_backend()


def inject_text(text, paste_fallback=False) -> bool:
    out = prepare(text)
    if out is None:
        return False
    if len(out) > MAX_PASTE:
        print(f"ROAR: injection refused — {len(out)} chars exceeds the "
              f"{MAX_PASTE} safety bound", flush=True)
        return False
    try:
        if paste_fallback:
            _BACKEND.paste_text(out)
        else:
            _BACKEND.type_text(out)
        return True
    except Exception as e:
        print(f"ROAR: injection failed ({e})", flush=True)
        return False


def send_backspaces(n) -> None:
    try:
        _BACKEND.send_backspaces(int(n))
    except Exception as e:
        print(f"ROAR: send_backspaces failed ({e})", flush=True)
