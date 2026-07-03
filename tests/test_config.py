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


def test_corrupt_json_falls_back_to_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not valid json!!")
    cfg = config.load(str(p))
    assert cfg == config.DEFAULTS
    assert p.read_text() == "{not valid json!!"  # user's file left for fixing


def test_non_string_replacements_filtered(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"replacements": {"bad": 123, "good": "ok", 5: "x"}}))
    cfg = config.load(str(p))
    assert "bad" not in cfg["replacements"]
    assert cfg["replacements"]["good"] == "ok"
    assert cfg["replacements"]["new line"] == "\n"


def test_custom_vocabulary_sanitized_on_load(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"custom_vocabulary": "hello"}))
    assert config.load(str(p))["custom_vocabulary"] == []  # non-list ignored
    p.write_text(json.dumps({"custom_vocabulary": ["ok", 7, "  ", " kept "]}))
    assert config.load(str(p))["custom_vocabulary"] == ["ok", "kept"]


def test_language_sanitized_on_load(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"language": "klingon"}))
    assert config.load(str(p))["language"] == "en"
    p.write_text(json.dumps({"language": "auto"}))
    assert config.load(str(p))["language"] == "auto"
    p.write_text(json.dumps({"language": "es"}))
    assert config.load(str(p))["language"] == "es"
