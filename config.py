"""config.json load/save with sane defaults."""
import copy
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS = {
    "hotkey_ptt": "ctrl+windows",
    "hotkey_toggle": "ctrl+windows+space",
    "model": "auto",
    "input_device": None,
    "paste_fallback": False,
    "silence_rms_threshold": 0.005,
    "min_duration_s": 0.3,
    "tones_enabled": True,
    "language": "en",
    "replacements": {"new line": "\n", "new paragraph": "\n\n"},
}


def load(path=None):
    path = path or PATH
    cfg = copy.deepcopy(DEFAULTS)
    if not os.path.exists(path):
        save(cfg, path)
        return cfg
    with open(path, encoding="utf-8") as f:
        user = json.load(f)
    for key, value in user.items():
        if key == "replacements" and isinstance(value, dict):
            cfg["replacements"].update(value)
        else:
            cfg[key] = value
    return cfg


def save(cfg, path=None):
    path = path or PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
