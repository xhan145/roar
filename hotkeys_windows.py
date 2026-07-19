"""Windows global hotkeys via the `keyboard` lib (extracted from app.py).
`keyboard` is imported lazily inside methods, never at module top — importing
it eagerly on Linux raises "must be root" at import time."""


class WindowsHotkeys:
    def __init__(self, on_key_event, on_toggle, toggle_chord):
        self._on_key_event = on_key_event
        self._on_toggle = on_toggle
        self._toggle = toggle_chord

    def start(self):
        import keyboard
        keyboard.hook(self._on_key_event)
        try:
            keyboard.add_hotkey(self._toggle, self._on_toggle)
        except ValueError:
            keyboard.add_hotkey(self._toggle.replace("windows", "left windows"),
                                self._on_toggle)

    def stop(self):
        import keyboard
        keyboard.unhook_all()
