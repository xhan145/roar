import os

import paths


def test_not_frozen_under_pytest():
    assert paths.is_frozen() is False


def test_source_paths_are_project_local():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert paths.config_path() == os.path.join(root, "config.json")
    assert paths.models_dir() == os.path.join(root, "models")


def test_redirect_is_noop_when_not_frozen(capsys):
    paths.redirect_output_when_frozen()
    print("still visible")
    assert "still visible" in capsys.readouterr().out


def test_app_name_is_roar():
    assert paths.APP_NAME == "ROAR"
    assert paths.APP_VERSION == "0.6.0"


def test_migrate_legacy_data_renames_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    la, ra = tmp_path / "Local", tmp_path / "Roaming"
    (la / "FlowLocal").mkdir(parents=True)
    (la / "FlowLocal" / "history.db").write_text("data")
    (ra / "FlowLocal").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(la))
    monkeypatch.setenv("APPDATA", str(ra))
    moved = paths.migrate_legacy_data()
    assert (la / "ROAR" / "history.db").read_text() == "data"
    assert not (la / "FlowLocal").exists()
    assert (ra / "ROAR").exists() and not (ra / "FlowLocal").exists()
    assert len(moved) >= 2


def test_migrate_no_clobber_when_both_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    la = tmp_path / "Local"
    (la / "FlowLocal").mkdir(parents=True)
    (la / "FlowLocal" / "old.txt").write_text("old")
    (la / "ROAR").mkdir(parents=True)
    (la / "ROAR" / "new.txt").write_text("new")
    monkeypatch.setenv("LOCALAPPDATA", str(la))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    paths.migrate_legacy_data()
    assert (la / "FlowLocal" / "old.txt").exists()   # untouched
    assert (la / "ROAR" / "new.txt").exists()


def test_migrate_noop_when_not_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    assert paths.migrate_legacy_data() == []
