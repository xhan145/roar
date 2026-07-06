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

    # tk.Tk() can transiently fail reading init.tcl when Tk instances are
    # created back-to-back in one process — retry before giving up.
    root = None
    for _ in range(4):
        try:
            root = tk.Tk()
            break
        except tk.TclError:
            time.sleep(0.5)
    if root is None:
        pytest.skip("Tk could not initialize (transient Tcl init race)")
    root.attributes("-topmost", True)
    entry = tk.Entry(root, width=40)
    entry.pack()
    root.update()

    # Prove we actually own keyboard focus before testing injection: type a
    # probe char and check it lands. If the user is actively using the
    # desktop, focus is contended — skip rather than fail on environment.
    focused = False
    for _ in range(3):
        entry.focus_force()
        root.update()
        time.sleep(0.5)
        keyboard.write("x", delay=0)
        deadline = time.time() + 1.5
        while time.time() < deadline and not entry.get():
            root.update()
            time.sleep(0.02)
        if entry.get() == "x":
            focused = True
            entry.delete(0, tk.END)
            root.update()
            break
        entry.delete(0, tk.END)
        root.update()
    if not focused:
        root.destroy()
        pytest.skip("desktop focus contended (user active) — injection "
                    "cannot be verified right now")
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


def _run_with_retry(text, paste_fallback, expected):
    """Two independently-probed attempts: focus can be stolen between the
    probe and the injection when the user is active. A genuine injector bug
    fails both attempts deterministically."""
    value = _run_injection(text, paste_fallback=paste_fallback)
    if value != expected:
        time.sleep(1.0)
        value = _run_injection(text, paste_fallback=paste_fallback)
    return value


def test_sendinput_types_into_focused_window():
    assert _run_with_retry("hello local", False, "hello local ") == "hello local "


def test_paste_fallback_and_clipboard_restored():
    pyperclip.copy("sentinel-before")
    assert _run_with_retry("pasted text", True, "pasted text ") == "pasted text "
    assert pyperclip.paste() == "sentinel-before"


def test_inject_empty_returns_false():
    assert injector.inject_text("", paste_fallback=False) is False


def test_paste_and_type_are_bounded():
    # backstop: never fire a runaway injection into the focused app
    huge = "x" * (injector.MAX_PASTE + 1)
    assert injector.inject_text(huge) is False
    assert injector.inject_text(huge, paste_fallback=True) is False
