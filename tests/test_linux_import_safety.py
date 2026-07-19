import importlib, sys
import pytest

MODULES = ["paths", "autostart", "injector", "window_focus",
           "hotkey_listener", "single_instance", "hardware_accel"]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports_with_linux_selection(mod, monkeypatch):
    import platform_id
    monkeypatch.setattr(platform_id, "is_linux", lambda: True)
    monkeypatch.setattr(platform_id, "is_windows", lambda: False)
    saved = sys.modules.get(mod)
    sys.modules.pop(mod, None)
    try:
        importlib.import_module(mod)   # must not raise (no eager winreg/win32/ctypes.windll)
    finally:
        # restore the ORIGINAL module object so we don't poison later tests
        # that monkeypatch this module (a fresh reimport would be a different
        # object than the one already-imported code holds a reference to).
        if saved is not None:
            sys.modules[mod] = saved
        else:
            sys.modules.pop(mod, None)
