import time
import tkinter as tk

import pyperclip

import injector


def test_prepare_appends_trailing_space():
    assert injector.prepare("hello") == "hello "


def test_prepare_keeps_trailing_newline():
    assert injector.prepare("hello\n") == "hello\n"


def test_prepare_rejects_empty():
    assert injector.prepare("") is None
    assert injector.prepare("   ") is None


def test_prepare_allows_bare_newline():
    assert injector.prepare("\n") == "\n"


def _run_injection(text, paste_fallback):
    import threading

    import keyboard
    keyboard.key_to_scan_codes("a")  # pre-warm the lib's key table (~4s cold)

    root = tk.Tk()
    root.attributes("-topmost", True)
    entry = tk.Entry(root, width=40)
    entry.pack()
    root.update()
    entry.focus_force()
    root.update()
    time.sleep(0.5)
    # inject on a thread so the Tk event loop can pump WHILE injection runs —
    # the paste fallback restores the clipboard 300ms after Ctrl+V, and the
    # target must process the paste before that restore happens.
    result = {}
    th = threading.Thread(
        target=lambda: result.update(ok=injector.inject_text(text, paste_fallback=paste_fallback)))
    th.start()
    deadline = time.time() + 20
    while time.time() < deadline and (th.is_alive() or not entry.get()):
        root.update()
        time.sleep(0.02)
    th.join(timeout=2)
    root.update()
    value = entry.get()
    root.destroy()
    assert result.get("ok") is True
    return value


def test_sendinput_types_into_focused_window():
    assert _run_injection("hello local", paste_fallback=False) == "hello local "


def test_paste_fallback_and_clipboard_restored():
    pyperclip.copy("sentinel-before")
    assert _run_injection("pasted text", paste_fallback=True) == "pasted text "
    assert pyperclip.paste() == "sentinel-before"


def test_inject_empty_returns_false():
    assert injector.inject_text("", paste_fallback=False) is False
