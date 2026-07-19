# tests/test_paths_linux.py
import os
import importlib
import pytest

@pytest.fixture
def linux_paths(monkeypatch, tmp_path):
    import paths
    monkeypatch.setattr(paths.platform_id, "is_linux", lambda: True)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return paths, home

def test_config_under_xdg_config(linux_paths):
    paths, home = linux_paths
    assert paths.config_path() == str(home / ".config" / "ROAR" / "config.json")

def test_data_under_xdg_data(linux_paths):
    paths, home = linux_paths
    assert paths.history_db_path() == str(home / ".local" / "share" / "ROAR" / "history.db")
    assert paths.models_dir() == str(home / ".local" / "share" / "ROAR" / "models")

def test_license_beside_config_not_in_data(linux_paths):
    paths, home = linux_paths
    lic = paths.license_path()
    assert lic == str(home / ".config" / "ROAR" / "license.json")
    assert ".local" not in lic  # never in the data dir that clears touch

def test_xdg_env_overrides(linux_paths, monkeypatch, tmp_path):
    paths, _ = linux_paths
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dat"))
    assert paths.config_path() == str(tmp_path / "cfg" / "ROAR" / "config.json")
    assert paths.log_path() == str(tmp_path / "dat" / "ROAR" / "roar.log")
