"""Pure per-app formatting profiles.

app.py supplies the detected foreground exe basename and, for browsers, the
window title. This module must stay lightweight: no Windows APIs, no ML imports.
"""

# profile name -> overrides for commands.process (only listed keys override the
# user's own settings)
_CASUAL = {"capitalize": False, "cleanup": True, "discourse_fillers": False}
_PROFILES = {
    "code": {"capitalize": False, "cleanup": False, "format_mode": "code"},
    "casual": _CASUAL,
    "formal": {"capitalize": True, "cleanup": True, "discourse_fillers": True},
    "chat": _CASUAL,  # legacy alias for existing config/tests
}
PROFILE_NAMES = tuple(_PROFILES)

# lowercased exe basename -> profile name
_APP_MAP = {
    # Code editors and terminals: verbatim.
    "code.exe": "code",
    "code - insiders.exe": "code",
    "devenv.exe": "code",
    "pycharm64.exe": "code",
    "idea64.exe": "code",
    "rider64.exe": "code",
    "webstorm64.exe": "code",
    "clion64.exe": "code",
    "goland64.exe": "code",
    "rustrover64.exe": "code",
    "phpstorm64.exe": "code",
    "datagrip64.exe": "code",
    "studio64.exe": "code",
    "notepad++.exe": "code",
    "sublime_text.exe": "code",
    "zed.exe": "code",
    "cursor.exe": "code",
    "windowsterminal.exe": "code",
    "wt.exe": "code",
    "cmd.exe": "code",
    "powershell.exe": "code",
    "pwsh.exe": "code",
    "conhost.exe": "code",
    "wezterm-gui.exe": "code",
    "alacritty.exe": "code",
    "hyper.exe": "code",

    # Casual/chat/social/music apps: keep texting style.
    "whatsapp.exe": "casual",
    "discord.exe": "casual",
    "telegram.exe": "casual",
    "signal.exe": "casual",
    "instagram.exe": "casual",
    "messenger.exe": "casual",
    "slack.exe": "casual",
    "teams.exe": "casual",
    "ms-teams.exe": "casual",
    "ableton live 11 suite.exe": "casual",
    "ableton live 12 suite.exe": "casual",
    "ableton live 11 lite.exe": "casual",
    "ableton.exe": "casual",
    "spotify.exe": "casual",

    # Email and document tools: polished prose.
    "outlook.exe": "formal",
    "winword.exe": "formal",
    "thunderbird.exe": "formal",
    "acrobat.exe": "formal",
    "wps.exe": "formal",
}

_APP_PREFIX = {
    "ableton": "casual",
}

_BROWSERS = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "arc.exe",
}

# Ordered: first keyword hit wins.
_TITLE_MAP = (
    ("whatsapp", "casual"),
    ("messenger", "casual"),
    ("facebook", "casual"),
    ("instagram", "casual"),
    ("discord", "casual"),
    ("gmail", "formal"),
    ("outlook", "formal"),
    ("google docs", "formal"),
    ("- word", "formal"),
    ("github", "code"),
    ("stack overflow", "code"),
    ("localhost", "code"),
    ("codepen", "code"),
)


def _profile(name):
    prof = _PROFILES.get(name)
    return dict(prof) if prof else None


def _clean_user_map(user_map):
    if not isinstance(user_map, dict):
        return {}
    clean = {}
    for key, value in user_map.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        key = key.strip().lower()
        value = value.strip().lower()
        if key and value in _PROFILES:
            clean[key] = value
    return clean


def _resolve_exe(exe_name, user_map):
    if not exe_name:
        return None
    if exe_name in user_map:
        return user_map[exe_name]
    prof = _APP_MAP.get(exe_name)
    if prof:
        return prof
    for prefix, prefix_prof in _APP_PREFIX.items():
        if exe_name.startswith(prefix):
            return prefix_prof
    return None


def _resolve_title(title, user_map):
    if not title:
        return None
    for key, prof in user_map.items():
        if key.startswith("title:") and key[6:] and key[6:] in title:
            return prof
    for keyword, prof in _TITLE_MAP:
        if keyword in title:
            return prof
    return None


def profile_for(exe_name, title=None, user_map=None):
    """Override dict for foreground app/title ({} = use user settings)."""
    exe = str(exe_name).strip().lower() if exe_name else ""
    title_l = str(title).strip().lower() if title else ""
    overrides = _clean_user_map(user_map)

    prof = _resolve_exe(exe, overrides)
    if prof:
        return _profile(prof)

    if exe in _BROWSERS:
        prof = _resolve_title(title_l, overrides)
        if prof:
            return _profile(prof)

    return {}
