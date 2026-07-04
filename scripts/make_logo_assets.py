"""Copy the lavender ROAR logo into assets/ and derive tight square sizes.
Run once: venv/Scripts/python.exe scripts/make_logo_assets.py"""
import os
import shutil

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"C:/Users/xhan1/OneDrive/Pictures/ROAR LOGO FINAL 2 LAV.png"
ASSETS = os.path.join(ROOT, "assets")


def main():
    os.makedirs(ASSETS, exist_ok=True)
    full = os.path.join(ASSETS, "roar-logo-purple.png")
    shutil.copyfile(SRC, full)
    im = Image.open(SRC).convert("RGBA")
    # Threshold the alpha before measuring: faint anti-alias pixels near the
    # canvas edges otherwise inflate the bbox to nearly the full sheet, leaving
    # the mark tiny and off-centre in the square.
    solid = im.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    bbox = solid.getbbox()
    mark = im.crop(bbox)
    side = max(mark.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    for px in (256, 64, 32):
        square.resize((px, px), Image.LANCZOS).save(
            os.path.join(ASSETS, f"roar-logo-purple-{px}.png"))
    print("logo assets written to", ASSETS)


if __name__ == "__main__":
    main()
