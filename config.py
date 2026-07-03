"""config.json load/save with sane defaults."""
import copy
import json
import os

import paths

PATH = paths.config_path()

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
    "history_enabled": True,
    "audio_retention_days": 0,
    "custom_vocabulary": [],
    "auto_vocabulary": True,
}


def load(path=None):
    path = path or PATH
    cfg = copy.deepcopy(DEFAULTS)
    if not os.path.exists(path):
        save(cfg, path)
        return cfg
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        # Broken hand-edited config must not brick the app. Keep the user's
        # file untouched so they can fix it; run on defaults meanwhile.
        print(f"FlowLocal: config.json is invalid ({e}) — using defaults. "
              f"Fix or delete {path} to silence this.", flush=True)
        return cfg
    for key, value in user.items():
        if key == "replacements" and isinstance(value, dict):
            cfg["replacements"].update(
                {k: v for k, v in value.items()
                 if isinstance(k, str) and isinstance(v, str)})
        elif key == "custom_vocabulary":
            # hand-edited configs: only a list of non-empty strings survives
            # (a plain string would otherwise be iterated char-by-char)
            if isinstance(value, list):
                cfg[key] = [str(w).strip() for w in value
                            if isinstance(w, str) and w.strip()]
        else:
            cfg[key] = value
    return cfg


def save(cfg, path=None):
    path = path or PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
