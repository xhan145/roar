import platform_id

def test_windows(monkeypatch):
    monkeypatch.setattr(platform_id.sys, "platform", "win32")
    assert platform_id.is_windows() and not platform_id.is_linux()
    assert platform_id.name() == "windows"

def test_linux(monkeypatch):
    monkeypatch.setattr(platform_id.sys, "platform", "linux")
    assert platform_id.is_linux() and not platform_id.is_windows()
    assert platform_id.name() == "linux"

def test_other(monkeypatch):
    monkeypatch.setattr(platform_id.sys, "platform", "darwin")
    assert platform_id.name() == "other"
