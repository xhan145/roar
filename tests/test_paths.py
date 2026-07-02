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
