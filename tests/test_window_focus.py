import window_focus


def test_selects_backend_windows(monkeypatch):
    monkeypatch.setattr(window_focus.platform_id, "is_linux", lambda: False)
    assert window_focus._select().__class__.__name__ == "WindowsFocus"


def test_x11_active_process_parses_comm(monkeypatch):
    import focus_x11
    monkeypatch.setattr(focus_x11.subprocess, "check_output",
                        lambda *a, **k: b"1234\n")
    monkeypatch.setattr(focus_x11.os.path, "exists", lambda p: True)
    monkeypatch.setattr(focus_x11, "_read", lambda p: "gedit\n")
    assert focus_x11.X11Focus().active_process() == "gedit"


def test_focus_guard_detects_change(monkeypatch):
    seq = iter([111, 222])
    class Fake:
        def current_id(self): return next(seq)
        def active_process(self): return ""
        def active_title(self): return ""
    monkeypatch.setattr(window_focus, "_BACKEND", Fake())
    a = window_focus.current_id(); b = window_focus.current_id()
    assert a != b
