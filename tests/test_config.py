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


def test_snippets_sanitized_on_load(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(
        {"snippets": {"ok": "text", "bad": 7, "bad name": "x", "big": "y" * 3000}}))
    cfg = config.load(str(p))
    # non-strings dropped; hand-edited string entries KEPT even when invalid
    # (deleting them here would clobber the user's file on the next save)
    assert cfg["snippets"] == {"ok": "text", "bad name": "x", "big": "y" * 3000}
    assert cfg["snippet_keyword"] == "snippet"


def test_non_dict_snippets_and_replacements_ignored(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"snippets": "boom", "replacements": ["boom"]}))
    cfg = config.load(str(p))
    assert cfg["snippets"] == {}
    assert cfg["replacements"]["new line"] == "\n"  # defaults intact


def test_cleanup_defaults_present(tmp_path):
    cfg = config.load(str(tmp_path / "config.json"))
    assert cfg["cleanup_enabled"] is True
    assert cfg["remove_discourse_fillers"] is False
    assert cfg["app_profiles"] == {}


def test_cleanup_flags_coerced_to_bool(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"cleanup_enabled": 0, "remove_discourse_fillers": 1}))
    cfg = config.load(str(p))
    assert cfg["cleanup_enabled"] is False
    assert cfg["remove_discourse_fillers"] is True


def test_milestone_defaults_and_coercion(tmp_path):
    cfg = config.load(str(tmp_path / "c1.json"))
    assert cfg["milestones_enabled"] is True
    assert cfg["milestone_notifications"] is True
    p = tmp_path / "c2.json"
    p.write_text(json.dumps({"milestones_enabled": 0, "milestone_notifications": 1}))
    cfg = config.load(str(p))
    assert cfg["milestones_enabled"] is False
    assert cfg["milestone_notifications"] is True


def test_double_tap_ms_default_and_clamp(tmp_path):
    assert config.load(str(tmp_path / "d.json"))["double_tap_ms"] == 400
    p = tmp_path / "d2.json"
    p.write_text(json.dumps({"double_tap_ms": 50}))
    assert config.load(str(p))["double_tap_ms"] == 200      # clamped up
    p.write_text(json.dumps({"double_tap_ms": 9999}))
    assert config.load(str(p))["double_tap_ms"] == 1000     # clamped down
    p.write_text(json.dumps({"double_tap_ms": "x"}))
    assert config.load(str(p))["double_tap_ms"] == 400      # non-numeric -> default


def test_app_profiles_sanitized_on_load(tmp_path):
    p = tmp_path / "profiles.json"
    p.write_text(json.dumps({"app_profiles": "boom"}))
    assert config.load(str(p))["app_profiles"] == {}

    p.write_text(json.dumps({
        "app_profiles": {
            "CODE.EXE": "formal",
            " title:Gmail ": "casual",
            "bad.exe": "unknown",
            "nonstr": 7,
            "": "code",
        }
    }))
    cfg = config.load(str(p))
    assert cfg["app_profiles"] == {
        "code.exe": "formal",
        "title:gmail": "casual",
    }
