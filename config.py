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
    "overlay_enabled": True,
    "streaming_preview": True,
    "snippets": {},
    "snippet_keyword": "snippet",
    "cleanup_enabled": True,
    "remove_discourse_fillers": False,
    "milestones_enabled": True,
    "milestone_notifications": True,
}


_COMMON_LANGS = {"en", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "uk",
                 "zh", "ja", "ko", "ar", "hi", "tr"}


def valid_language(v) -> bool:
    if v == "auto":
        return True
    if not isinstance(v, str):
        return False
    from languages import CODES  # static — never imports faster_whisper
    return v in CODES


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
        print(f"ROAR: config.json is invalid ({e}) — using defaults. "
              f"Fix or delete {path} to silence this.", flush=True)
        return cfg
    for key, value in user.items():
        if key == "replacements":
            if isinstance(value, dict):
                cfg["replacements"].update(
                    {k: v for k, v in value.items()
                     if isinstance(k, str) and isinstance(v, str)})
        elif key == "language":
            if valid_language(value):
                cfg[key] = value
            else:
                print(f"ROAR: unknown language {value!r} in config — using en",
                      flush=True)
        elif key == "snippets":
            # type safety only — name/length rules are enforced where entries
            # are CREATED (bridge save/import). Dropping hand-edited entries
            # here would silently delete them on the next settings write, and
            # an invalid name is inert anyway: the expansion regex can only
            # capture [A-Za-z0-9-]{1,30}.
            if isinstance(value, dict):
                cfg["snippets"] = {k: v for k, v in value.items()
                                   if isinstance(k, str) and isinstance(v, str)}
        elif key == "snippet_keyword":
            if isinstance(value, str) and value.strip():
                cfg[key] = value.strip()
        elif key in ("cleanup_enabled", "remove_discourse_fillers",
                     "milestones_enabled", "milestone_notifications"):
            cfg[key] = bool(value)
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
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)  # getters are pure; writers create
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
