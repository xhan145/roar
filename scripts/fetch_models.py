"""Download the multilingual models into models-seed/ for installer bundling.

Run: venv/Scripts/python.exe scripts/fetch_models.py
The seed ships inside the exe/MSI so language switching works offline.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SEED_MODELS = ["large-v3-turbo", "small"]


def main():
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from faster_whisper import download_model
    seed_root = os.path.join(ROOT, "models-seed")
    for name in SEED_MODELS:
        out = os.path.join(seed_root, name)
        marker = os.path.join(out, "model.bin")
        if os.path.exists(marker):
            print(f"{name}: already seeded")
            continue
        print(f"{name}: downloading to {out} ...")
        download_model(name, output_dir=out)
        print(f"{name}: done")
    print("seed complete")


if __name__ == "__main__":
    main()
