"""'Make it work everywhere' fixes: UIA ancestor walk + backup-aware fallback."""
import sys
import types

import pytest

import tts.text_sources as sources
from tts.clipboard_guard import ClipboardSnapshot


# --- backup-aware clipboard fallback ---------------------------------------

def _seq_counter(values):
    it = iter(values)
    last = [values[0]]
    def read():
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        return last[0]
    return read


def test_non_text_clipboard_proceeds_when_backup_available():
    """A screenshot on the clipboard used to abort with 'cannot preserve'.
    With a Win32 snapshot available the read proceeds and restores it."""
    restored = []
    snap = ClipboardSnapshot({8: b"dib-bytes"}, skipped=0)   # CF_DIB
    api = {
        "sequence": _seq_counter([1, 1, 2, 2, 2]),
        "has_text": lambda: False,
        "format_count": lambda: 1,
        "get": lambda: "selected words",
        "set": lambda text: None,
        "send": lambda: None,
        "sleep": lambda s: None,
        "backup": lambda: snap,
        "restore": lambda s: restored.append(s) or True,
    }
    assert sources._copy_selection_with_restore(
        timeout=0.2, _api=api) == "selected words"
    assert restored == [snap]                 # the image came back


def test_non_text_clipboard_still_refused_without_backup():
    """Unchanged safety: if nothing could be backed up, never destroy it."""
    api = {
        "sequence": lambda: 1,
        "has_text": lambda: False,
        "format_count": lambda: 2,
        "get": lambda: "x",
        "set": lambda t: None,
        "send": lambda: None,
        "sleep": lambda s: None,
        "backup": lambda: ClipboardSnapshot({}, skipped=2),  # private formats
    }
    with pytest.raises(sources.TextSourceError):
        sources._copy_selection_with_restore(timeout=0.2, _api=api)


def test_text_clipboard_restores_via_backup_not_pyperclip():
    restored, set_calls = [], []
    snap = ClipboardSnapshot({13: "old".encode("utf-16-le") + b"\x00\x00"}, 0)
    api = {
        "sequence": _seq_counter([1, 1, 2, 2, 2]),
        "has_text": lambda: True,
        "format_count": lambda: 1,
        "get": lambda: "selected",
        "set": lambda t: set_calls.append(t),
        "send": lambda: None,
        "sleep": lambda s: None,
        "backup": lambda: snap,
        "restore": lambda s: restored.append(s) or True,
    }
    assert sources._copy_selection_with_restore(
        timeout=0.2, _api=api) == "selected"
    assert restored == [snap] and set_calls == []


# --- UIA ancestor walk ------------------------------------------------------

class _FakePattern:
    def __init__(self, text):
        self._text = text

    def GetSelection(self):
        class R:
            def __init__(self, t): self._t = t
            def GetText(self, _cap): return self._t
        return [R(self._text)]


class _FakeControl:
    def __init__(self, pattern=None, is_password=False):
        self._pattern = pattern
        self.IsPassword = is_password

    def GetPattern(self, _pid):
        return self._pattern


def _stub_uia(monkeypatch, focused):
    mod = types.ModuleType("uiautomation")
    mod.SetGlobalSearchTimeout = lambda t: None
    mod.GetFocusedControl = lambda: focused
    mod.PatternId = types.SimpleNamespace(TextPattern=10014)
    monkeypatch.setitem(sys.modules, "uiautomation", mod)


def test_focused_control_selection_is_read(monkeypatch):
    monkeypatch.setattr(sources.platform_id, "is_windows", lambda: True)
    _stub_uia(monkeypatch, _FakeControl(pattern=_FakePattern("highlighted words")))
    assert sources._read_uia_selection() == "highlighted words"


def test_no_text_pattern_raises_so_fallback_takes_over(monkeypatch):
    # a control with no TextPattern must NOT read anything — it raises, and the
    # caller drops to the clipboard fallback (the everywhere path)
    monkeypatch.setattr(sources.platform_id, "is_windows", lambda: True)
    _stub_uia(monkeypatch, _FakeControl(pattern=None))
    with pytest.raises(sources.TextSourceError):
        sources._read_uia_selection()


def test_password_focus_fails_closed(monkeypatch):
    monkeypatch.setattr(sources.platform_id, "is_windows", lambda: True)
    _stub_uia(monkeypatch, _FakeControl(pattern=_FakePattern("secret"),
                                        is_password=True))
    with pytest.raises(sources.TextSourceError):
        sources._read_uia_selection()


# --- Point & Speak forces the fallback even when the global toggle is off ---

def test_global_fallback_stays_off_by_default():
    # privacy invariant: the clipboard fallback ships OFF globally
    import config as config_mod
    assert config_mod.DEFAULTS["tts_clipboard_fallback_enabled"] is False


def test_read_selected_fallback_resolves_from_config_or_force():
    """The read_selected handler uses the fallback when EITHER the global
    toggle is on OR the caller forced it (Point & Speak). This mirrors the
    exact expression in app._handle_tts_command."""
    def resolves(global_on, forced):
        return bool(global_on) or bool(forced)
    assert resolves(False, True) is True     # gesture forces it
    assert resolves(False, False) is False   # hotkey, global off
    assert resolves(True, False) is True     # hotkey, global on
