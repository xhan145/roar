"""Hotkey chord parsing shared by the tray app and the settings process.

Lives in its own module so the settings UI can import it without pulling
the ML stack (app.py imports transcriber -> ctranslate2 -> CUDA DLLs).
"""

MODIFIER_ALIASES = {
    "ctrl": {"ctrl", "left ctrl", "right ctrl"},
    "windows": {"windows", "left windows", "right windows"},
    "alt": {"alt", "left alt", "right alt", "alt gr"},
    "shift": {"shift", "left shift", "right shift"},
}


def parse_chord(hotkey: str):
    return [k.strip().lower() for k in hotkey.split("+") if k.strip()]
