import config
from settings_ui import SettingsAPI, normalize_combo


def test_normalize_combo_orders_and_merges_sides():
    assert normalize_combo({"left ctrl", "left windows"}) == "ctrl+windows"
    assert normalize_combo({"right shift", "z", "left alt"}) == "alt+shift+z"
    assert normalize_combo(set()) == ""


def test_set_value_whitelist(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("tones_enabled", False)["ok"] is True
    assert config.load(p)["tones_enabled"] is False
    assert "error" in api.set_value("model", "tiny.en")  # model is Apply-only


def test_sensitivity_clamped(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("silence_rms_threshold", 999)["ok"] is True
    assert config.load(p)["silence_rms_threshold"] == 0.02
    assert "error" in api.set_value("silence_rms_threshold", "abc")


def test_apply_hotkeys_validates(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.apply_hotkeys("ctrl+alt", "ctrl+alt+space")["ok"] is True
    assert config.load(p)["hotkey_ptt"] == "ctrl+alt"
    assert "error" in api.apply_hotkeys("", "ctrl+space")
    assert "error" in api.apply_hotkeys("ctrl+x", "ctrl+x")


def test_apply_model(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.apply_model("small.en")["ok"] is True
    assert config.load(p)["model"] == "small.en"
    assert "error" in api.apply_model("bogus-model")


def test_get_state_shape(tmp_path):
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    s = api.get_state()
    assert s["config"]["hotkey_ptt"] == "ctrl+windows"
    assert isinstance(s["devices"], list) and isinstance(s["autostart"], bool)
    assert s["version"] == "0.2.0"
