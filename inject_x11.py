"""X11 text injection. pynput Unicode typing by default; xdotool alternative;
clipboard-paste fallback. Verified on Ubuntu 24.04 / Xorg."""
import subprocess
import time


class X11Injector:
    def __init__(self, mode="pynput"):
        self.mode = "xdotool" if mode == "xdotool" else "pynput"
        self._kb = None

    def _controller(self):
        if self._kb is None:
            from pynput import keyboard
            self._kb = keyboard.Controller()
        return self._kb

    def type_text(self, text):
        if self.mode == "xdotool":
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text],
                           check=False)
            return
        self._controller().type(text)

    def paste_text(self, text):
        import pyperclip
        old = None
        try:
            old = pyperclip.paste()
        except Exception:
            pass
        pyperclip.copy(text)
        from pynput import keyboard
        kb = self._controller()
        kb.press(keyboard.Key.ctrl)
        kb.press("v"); kb.release("v")
        kb.release(keyboard.Key.ctrl)
        time.sleep(0.8)
        if old is not None:
            try:
                pyperclip.copy(old)
            except Exception:
                pass

    def send_backspaces(self, n):
        if self.mode == "xdotool":
            for _ in range(n):
                subprocess.run(["xdotool", "key", "--clearmodifiers", "BackSpace"],
                               check=False)
            return
        from pynput import keyboard
        kb = self._controller()
        for _ in range(n):
            kb.press(keyboard.Key.backspace)
            kb.release(keyboard.Key.backspace)
