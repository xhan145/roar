import json

from settings_ui import SettingsAPI


def make_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    return path


def test_tts_settings_validation_and_core_availability(tmp_path, monkeypatch):
    path = make_config(tmp_path)
    api = SettingsAPI(str(path))
    monkeypatch.setattr(
        "tts.playback.list_output_devices",
        lambda: [("default", "System default"), (4, "Speakers")])
    result = api.tts_apply({
        "tts_enabled": True,
        "tts_voice": "af_heart",
        "tts_language": "en-us",
        "tts_speed": 1.25,
        "tts_volume": 0.8,
        "tts_output_device": "4",
        "tts_readback_mode": "after",
        "tts_unload_after_idle_minutes": 5,
    })
    assert result == {"ok": True}
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["tts_enabled"] is True
    assert saved["tts_readback_mode"] == "after"


def test_tts_hotkeys_reject_dictation_and_internal_collisions(tmp_path):
    api = SettingsAPI(str(make_config(tmp_path)))
    assert "conflicts" in api.tts_apply_hotkeys({
        "tts_hotkey_stop": "ctrl+windows",
    })["error"]
    assert "conflicts" in api.tts_apply_hotkeys({
        "tts_hotkey_stop": "ctrl+shift+x",
        "tts_hotkey_repeat": "shift+ctrl+x",
    })["error"]


def test_tts_settings_reject_invalid_ranges(tmp_path, monkeypatch):
    api = SettingsAPI(str(make_config(tmp_path)))
    monkeypatch.setattr(
        "tts.playback.list_output_devices",
        lambda: [("default", "System default")])
    assert "between" in api.tts_apply({"tts_speed": 3})["error"]
    assert "not supported" in api.tts_apply({"license": "pro"})["error"]
