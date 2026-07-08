import copy

from app import diff_config
from config import DEFAULTS


def _pair(**changes):
    old = copy.deepcopy(DEFAULTS)
    new = copy.deepcopy(DEFAULTS)
    new.update(changes)
    return old, new


def test_no_change_no_actions():
    assert diff_config(*_pair()) == []


def test_hotkey_change_rehooks_once():
    old, new = _pair(hotkey_ptt="ctrl+alt", hotkey_toggle="ctrl+alt+space")
    assert diff_config(old, new) == [("rehook", None)]


def test_model_and_device():
    old, new = _pair(model="tiny.en", input_device=3)
    assert ("reload_model", "tiny.en") in diff_config(old, new)
    assert ("set_device", 3) in diff_config(old, new)


def test_instant_keys_produce_no_actions():
    old, new = _pair(tones_enabled=False, paste_fallback=True,
                     silence_rms_threshold=0.01)
    assert diff_config(old, new) == []


def test_vocabulary_changes_rebuild_hotwords_once():
    old, new = _pair(custom_vocabulary=["ScratchEdge"], auto_vocabulary=False)
    assert diff_config(old, new) == [("rebuild_hotwords", None)]


def test_defaults_have_vocabulary_keys():
    from config import DEFAULTS
    assert DEFAULTS["custom_vocabulary"] == []
    assert DEFAULTS["auto_vocabulary"] is True


def test_language_change_reloads_model_once():
    old, new = _pair(language="es", model="auto")
    assert diff_config(old, new) == [("reload_model", "auto")]


def test_language_and_model_change_single_reload():
    old, new = _pair(language="auto", model="small")
    assert diff_config(old, new).count(("reload_model", "small")) == 1


def test_acceleration_changes_reload_model():
    for change in ({"acceleration_mode": "cpu"}, {"compute_type": "int8_float16"},
                   {"performance_preset": "fast"}, {"gpu_device_index": 1},
                   {"max_vram_mode": True}, {"backend": "onnx_directml"},
                   {"cpu_threads": 6}):
        old, new = _pair(**change)
        assert ("reload_model", "auto") in diff_config(old, new), change


def test_acceleration_and_model_change_single_reload():
    old, new = _pair(model="small", performance_preset="accurate")
    assert diff_config(old, new).count(("reload_model", "small")) == 1


def test_defaults_have_acceleration_keys():
    for k in ("acceleration_mode", "performance_preset", "compute_type",
              "backend", "gpu_device_index", "prefer_low_latency", "max_vram_mode"):
        assert k in DEFAULTS
