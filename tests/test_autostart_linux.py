import os, pytest

@pytest.fixture
def linux_autostart(monkeypatch, tmp_path):
    import autostart
    monkeypatch.setattr(autostart.platform_id, "is_linux", lambda: True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return autostart, tmp_path

def test_enable_writes_desktop_file(linux_autostart):
    autostart, home = linux_autostart
    autostart.set_enabled("ROAR", "/opt/roar/roar", True)
    p = home / ".config" / "autostart" / "ROAR.desktop"
    assert p.exists()
    body = p.read_text()
    assert "Type=Application" in body
    assert "Exec=/opt/roar/roar" in body
    assert "Name=ROAR" in body
    assert "X-GNOME-Autostart-enabled=true" in body

def test_get_returns_exec_then_none_after_disable(linux_autostart):
    autostart, _ = linux_autostart
    assert autostart.get("ROAR") is None
    autostart.set_enabled("ROAR", "/opt/roar/roar", True)
    assert autostart.get("ROAR") == "/opt/roar/roar"
    autostart.set_enabled("ROAR", "", False)
    assert autostart.get("ROAR") is None
