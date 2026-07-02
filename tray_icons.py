"""Pillow-drawn tray icons. State is encoded in shape AND color (a11y)."""
from PIL import Image, ImageDraw

COLORS = {
    "idle": "#D1D5DB",
    "loading": "#D1D5DB",
    "recording": "#DC2626",
    "transcribing": "#2563EB",
    "error": "#D97706",
}


def make_icon(state: str, size: int = 64) -> Image.Image:
    color = COLORS[state]
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # microphone: capsule + cradle arc + stem + base
    d.rounded_rectangle([24, 8, 40, 36], radius=8, fill=color)
    d.arc([16, 18, 48, 44], start=0, end=180, fill=color, width=4)
    d.line([32, 44, 32, 52], fill=color, width=4)
    d.line([22, 54, 42, 54], fill=color, width=4)
    # state decoration, bottom-right corner
    if state == "recording":
        d.ellipse([46, 44, 60, 58], fill=color)
    elif state in ("transcribing", "loading"):
        d.arc([44, 42, 60, 58], start=300, end=210, fill=color, width=4)
    elif state == "error":
        d.line([53, 40, 53, 50], fill=color, width=4)
        d.ellipse([50, 53, 56, 59], fill=color)
    return img
