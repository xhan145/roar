import json

import config
from tts.types import TTSConfig


def test_tts_defaults_are_private_and_core_safe(tmp_path):
    cfg = config.load(path=str(tmp_path / "missing.json"))
    assert cfg["tts_enabled"] is False
    assert cfg["tts_readback_mode"] == "off"
    assert cfg["tts_spoken_status_enabled"] is False
    assert cfg["tts_clipboard_fallback_enabled"] is False
    assert cfg["tts_persistent_cache_enabled"] is False
    assert cfg["tts_speed"] == 1.0
    assert all(not cfg[key] for key in cfg if key.startswith("tts_hotkey_"))


def test_tts_config_values_are_clamped_and_malformed_values_degrade(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "tts_enabled": 1,
        "tts_speed": 99,
        "tts_volume": -5,
        "tts_language": "unsupported",
        "tts_readback_mode": "surprise",
        "tts_unload_after_idle_minutes": "99999",
        "unknown_future_field": {"preserved": True},
    }), encoding="utf-8")
    cfg = config.load(str(path))
    assert cfg["tts_enabled"] is True
    assert cfg["tts_speed"] == 1.6
    assert cfg["tts_volume"] == 0.0
    assert cfg["tts_language"] == "en-us"
    assert cfg["tts_readback_mode"] == "off"
    assert cfg["tts_unload_after_idle_minutes"] == 1440
    assert cfg["unknown_future_field"] == {"preserved": True}


def test_backend_tts_config_is_defensive():
    cfg = TTSConfig.from_mapping({
        "tts_enabled": True,
        "tts_speed": float("nan"),
        "tts_volume": "bad",
        "tts_output_device": "4",
        "tts_model_path": " ",
    })
    assert cfg.enabled
    assert cfg.speed == 1.0
    assert cfg.volume == 1.0
    assert cfg.output_device == 4
    assert cfg.model_path is None


def test_voice_catalog_does_not_infer_demographics_from_ids():
    from tts.voices import VOICES

    assert all(voice.gender is None for voice in VOICES)
