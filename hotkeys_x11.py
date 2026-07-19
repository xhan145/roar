"""X11 global hotkeys via pynput. Reliability first: own thread, clean stop,
one self-heal restart if the listener dies. Verified on Ubuntu 24.04 / Xorg."""
import threading


class _Event:
    __slots__ = ("event_type", "name")
    def __init__(self, event_type, name):
        self.event_type = event_type
        self.name = name


def _key_name(key):
    char = getattr(key, "char", None)
    if char:
        return char.lower()
    name = getattr(key, "name", None) or str(key).replace("Key.", "")
    return name.lower()


class X11Hotkeys:
    def __init__(self, on_key_event, on_toggle, toggle_chord):
        self._on_key_event = on_key_event
        self._on_toggle = on_toggle
        self._chord = [k.strip().lower() for k in toggle_chord.split("+") if k.strip()]
        self._down = set()
        self._listener = None
        self._watchdog = None
        self._stopped = False
        self._restarted = False
        self._toggle_fired = False

    def _press(self, key):
        name = _key_name(key)
        self._down.add(name)
        self._on_key_event(_Event("down", name))
        if self._chord and not self._toggle_fired and all(
                (c in self._down) or (c == "ctrl" and "ctrl_l" in self._down)
                for c in self._chord):
            self._toggle_fired = True
            try:
                self._on_toggle()
            except Exception:
                pass

    def _release(self, key):
        name = _key_name(key)
        self._down.discard(name)
        self._on_key_event(_Event("up", name))
        if name in self._chord or (name == "ctrl_l" and "ctrl" in self._chord):
            self._toggle_fired = False

    def start(self):
        from pynput import keyboard
        self._stopped = False
        self._listener = keyboard.Listener(on_press=self._press,
                                           on_release=self._release)
        self._listener.start()
        self._watchdog = threading.Thread(target=self._watch, daemon=True)
        self._watchdog.start()

    def _maybe_restart(self, listener):
        """Decide whether to self-heal a dead listener. Returns True if a
        restart was performed. Per-instance, once-per-lifetime budget;
        stop() always wins the race."""
        alive = getattr(listener, "is_alive", lambda: True)()
        if alive or self._restarted:
            return False
        if self._stopped:      # stop() won the race — do not resurrect
            return False
        self._restarted = True
        print("ROAR: hotkey listener died — restarting once", flush=True)
        try:
            self.start()
        except Exception as e:
            print(f"ROAR: hotkey restart failed ({e})", flush=True)
        return True

    def _watch(self):
        import time
        while not self._stopped:
            time.sleep(2.0)
            lis = self._listener
            if self._stopped or lis is None:
                return
            if self._maybe_restart(lis):
                return

    def stop(self):
        self._stopped = True
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
