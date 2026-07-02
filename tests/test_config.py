import json

import config


def test_first_run_creates_file_with_defaults(tmp_path):
    p = tmp_path / "config.json"
    cfg = config.load(str(p))
    assert p.exists()
    assert cfg == config.DEFAULTS
    assert cfg is not config.DEFAULTS  # must be a copy


def test_user_overrides_merge(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"model": "tiny.en", "replacements": {"smiley": ":)"}}))
    cfg = config.load(str(p))
    assert cfg["model"] == "tiny.en"
    assert cfg["replacements"]["smiley"] == ":)"
    assert cfg["replacements"]["new line"] == "\n"  # defaults preserved
    assert cfg["hotkey_ptt"] == "ctrl+windows"


def test_save_round_trip(tmp_path):
    p = tmp_path / "config.json"
    cfg = config.load(str(p))
    cfg["paste_fallback"] = True
    config.save(cfg, str(p))
    assert config.load(str(p))["paste_fallback"] is True
