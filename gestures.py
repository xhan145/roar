"""Pure hotkey-gesture recognition for hands-free dictation. No I/O — app.py
feeds timed chord transitions and acts on the returned intent."""

START = "START"
FINISH = "FINISH"
DEFER = "DEFER"
HANDSFREE = "HANDSFREE"
STOP = "STOP"
NONE = "NONE"


class TapToggleDetector:
    def __init__(self, double_tap_s=0.4, tap_max_s=0.35):
        self.double_tap_s = double_tap_s
        self.tap_max_s = tap_max_s
        self._handsfree = False
        self._press_start = None
        self._last_tap_up = None

    def feed(self, kind, now):
        if kind == "down":
            if self._handsfree:
                self._reset()
                return STOP
            if (self._last_tap_up is not None
                    and now - self._last_tap_up <= self.double_tap_s):
                self._handsfree = True
                self._last_tap_up = None
                self._press_start = None
                return HANDSFREE
            self._press_start = now
            return START
        # kind == "up"
        if self._handsfree:
            return NONE
        if self._press_start is not None:
            dur = now - self._press_start
            self._press_start = None
            if dur <= self.tap_max_s:
                self._last_tap_up = now
                return DEFER
            self._last_tap_up = None
            return FINISH
        return NONE

    def on_defer_timeout(self, now):
        if self._last_tap_up is not None and not self._handsfree:
            self._last_tap_up = None
            return FINISH
        return NONE

    def _reset(self):
        self._handsfree = False
        self._press_start = None
        self._last_tap_up = None
