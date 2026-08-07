# tests/test_paths_linux.py
import os
import importlib
import sys
import pytest

@pytest.fixture
def linux_paths(monkeypatch, tmp_path):
    import paths
    monkeypatch.setattr(paths.platform_id, "is_linux", lambda: True)
    monkeypatch.setattr(paths.platform_id, "is_windows", lambda: False)
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


def test_frozen_linux_uses_xdg_user_paths_without_windows_environment(
    linux_paths, monkeypatch, tmp_path
):
    """A PyInstaller Linux build must not require Windows environment variables."""
    paths, _ = linux_paths
    config_root = tmp_path / "xdg-config"
    data_root = tmp_path / "xdg-data"
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_root))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert paths.config_path() == str(config_root / "ROAR" / "config.json")
    assert paths.license_path() == str(config_root / "ROAR" / "license.json")
    assert paths.legacy_grant_path() == str(config_root / "ROAR" / "legacy_grant.json")
    assert paths.trial_state_path() == str(config_root / "ROAR" / "trial.json")

    assert paths.models_dir() == str(data_root / "ROAR" / "models")
    assert paths.tts_dir() == str(data_root / "ROAR" / "tts")
    assert paths.tts_model_dir() == str(data_root / "ROAR" / "tts" / "kokoro")
    assert paths.tts_runtime_python() == str(
        data_root / "ROAR" / "tts" / "runtime" / "bin" / "python"
    )
    assert paths._data_dir() == str(data_root / "ROAR")
    assert paths.vulkan_dir() == str(data_root / "ROAR" / "vulkan")
    assert paths.history_db_path() == str(data_root / "ROAR" / "history.db")
    assert paths.status_path() == str(data_root / "ROAR" / "status.json")
    assert paths.command_path() == str(data_root / "ROAR" / "command.json")
    assert paths.log_path() == str(data_root / "ROAR" / "roar.log")

    assert paths.resource_path("settings.html") == os.path.join(
        os.path.dirname(sys.executable), "_internal", "settings.html"
    )
