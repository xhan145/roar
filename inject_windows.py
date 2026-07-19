"""Windows text injection: keyboard.write (SendInput unicode), clipboard paste."""
import time


class WindowsInjector:
    def type_text(self, text):
        import keyboard
        keyboard.write(text, delay=0)

    def paste_text(self, text):
        import keyboard, pyperclip
        old = None
        try:
            old = pyperclip.paste()
        except Exception:
            pass
        pyperclip.copy(text)
        keyboard.send("ctrl+v")
        time.sleep(0.8)
        if old is not None:
            try:
                pyperclip.copy(old)
            except Exception:
                pass

    def send_backspaces(self, n):
        import keyboard
        for _ in range(n):
            keyboard.send("backspace")
