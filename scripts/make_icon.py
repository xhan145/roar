"""Generate icon.ico (multi-size) from the ROAR mic glyph.

Run: venv/Scripts/python.exe scripts/make_icon.py
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BRAND = "#5E6AD2"  # ROAR blue (transcribing state color)


def draw_mic(size: int) -> Image.Image:
    """Scaled-up version of tray_icons' mic glyph on a soft dark disc."""
    s = size / 64.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([1 * s, 1 * s, 63 * s, 63 * s], fill="#0a0a0c")
    w = max(2, int(4 * s))
    d.rounded_rectangle([24 * s, 10 * s, 40 * s, 38 * s], radius=8 * s, fill=BRAND)
    d.arc([16 * s, 20 * s, 48 * s, 46 * s], start=0, end=180, fill=BRAND, width=w)
    d.line([32 * s, 46 * s, 32 * s, 52 * s], fill=BRAND, width=w)
    d.line([22 * s, 54 * s, 42 * s, 54 * s], fill=BRAND, width=w)
    return img


def main():
    base = draw_mic(256)
    out = os.path.join(ROOT, "icon.ico")
    base.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                          (128, 128), (256, 256)])
    print(f"wrote {out} ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
