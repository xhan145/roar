import importlib, sys
import pytest

MODULES = ["paths", "autostart", "injector", "window_focus",
           "hotkey_listener", "single_instance", "hardware_accel"]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports_with_linux_selection(mod, monkeypatch):
    import platform_id
    monkeypatch.setattr(platform_id, "is_linux", lambda: True)
    monkeypatch.setattr(platform_id, "is_windows", lambda: False)
    sys.modules.pop(mod, None)
    importlib.import_module(mod)   # must not raise (no eager winreg/win32/ctypes.windll)
