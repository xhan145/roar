"""Global hotkey capture behind a platform seam. Reliability is the priority:
start/stop/restart are clean, and the Linux backend self-heals a dead listener."""
import platform_id


class HotkeyListener:
    def __init__(self, on_key_event, on_toggle, toggle_chord):
        self._backend = self._select(on_key_event, on_toggle, toggle_chord)

    def _select(self, on_key_event, on_toggle, toggle_chord):
        if platform_id.is_linux():
            from hotkeys_x11 import X11Hotkeys       # Task 9
            return X11Hotkeys(on_key_event, on_toggle, toggle_chord)
        from hotkeys_windows import WindowsHotkeys
        return WindowsHotkeys(on_key_event, on_toggle, toggle_chord)

    def start(self):   self._backend.start()
    def stop(self):    self._backend.stop()
    def restart(self):
        self._backend.stop()
        self._backend.start()
