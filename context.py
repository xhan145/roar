"""Per-app formatting profiles: the focused app decides how dictation is
formatted. Pure — app.py supplies the detected foreground exe basename."""

# profile name -> overrides for commands.process (only listed keys override the
# user's own settings)
_PROFILES = {
    "code": {"capitalize": False, "cleanup": False},   # exact words, no auto-cap
    "chat": {"discourse_fillers": True},               # terser messages
}

# lowercased exe basename -> profile name
_APP_MAP = {
    "code.exe": "code", "code - insiders.exe": "code", "devenv.exe": "code",
    "pycharm64.exe": "code", "idea64.exe": "code", "sublime_text.exe": "code",
    "windowsterminal.exe": "code", "cmd.exe": "code", "powershell.exe": "code",
    "pwsh.exe": "code", "conhost.exe": "code", "wezterm-gui.exe": "code",
    "slack.exe": "chat", "discord.exe": "chat", "teams.exe": "chat",
    "ms-teams.exe": "chat", "telegram.exe": "chat", "whatsapp.exe": "chat",
}


def profile_for(exe_name):
    """Override dict for a foreground exe basename ({} = use user settings)."""
    if not exe_name:
        return {}
    prof = _PROFILES.get(_APP_MAP.get(str(exe_name).lower()))
    return dict(prof) if prof else {}
