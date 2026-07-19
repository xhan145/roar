"""Focused-window queries behind a platform seam. current_id() is an opaque,
comparable handle used for the injection focus-guard; active_process/title feed
per-app profiles (context.py)."""
import platform_id


def _select():
    if platform_id.is_linux():
        from focus_x11 import X11Focus
        return X11Focus()
    from focus_windows import WindowsFocus
    return WindowsFocus()


_BACKEND = _select()

def current_id():      return _BACKEND.current_id()
def active_process():  return _BACKEND.active_process()
def active_title():    return _BACKEND.active_title()
