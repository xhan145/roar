# PyInstaller spec for ROAR.
# Build: venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm
#
# One-dir (NOT one-file): the bundled CUDA DLLs are >1 GB; one-file would
# re-extract them on every launch. Windowed: logs go to
# %LOCALAPPDATA%/ROAR/roar.log (see paths.py).
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in (
    "faster_whisper",   # bundles the silero VAD assets
    "ctranslate2",      # native inference DLLs
    "av",               # audio decoding used by faster-whisper
    "onnxruntime",      # imported by faster_whisper.vad
    "nvidia.cublas",    # CUDA runtime DLLs (GPU inference)
    "nvidia.cudnn",
    "nvidia.cuda_nvrtc",
    "webview",          # pywebview (settings window)
    "uiautomation",     # safe selected-text UI Automation + native helper DLL
    "comtypes",         # uiautomation COM bridge
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# The Vulkan GPU backend is imported lazily (only when the user opts in), which
# PyInstaller's static analysis can miss — pin it so the frozen build always has
# it available for the opt-in path.
hiddenimports += ["whispercpp_assets", "backends", "backends.whispercpp_vulkan"]
hiddenimports += ["uiautomation", "comtypes"]

datas += [("settings.html", ".")]
datas += [("tts/worker.py", "tts"),
          ("tts/assets/kokoro-model-manifest.json", "tts/assets"),
          ("licenses", "licenses"),
          ("THIRD_PARTY_NOTICES.md", ".")]

import os as _os2
if _os2.path.isdir("assets"):
    datas += [("assets", "assets")]  # roar-logo-purple* brand images

# Multilingual model seed (scripts/fetch_models.py) — ships offline languages.
#
# It is 2.0 GB of the ~3.5 GB bundle, which pushed the installer to 2.65 GB —
# OVER GitHub's 2 GiB release-asset cap, i.e. undistributable, and a brutal
# download for a first-time user. Build with ROAR_SLIM=1 to omit it: the app
# already falls back local cache -> bundled seed -> download (transcriber.load),
# so a slim build simply fetches the model on first run. The trade is that a
# slim install needs the network ONCE; everything after is offline as always.
import os as _os
_SLIM = _os.environ.get("ROAR_SLIM", "").strip() not in ("", "0", "false")
if _SLIM:
    print("ROAR_SLIM=1 - omitting models-seed (~2 GB); the model downloads on "
          "first run", flush=True)
elif _os.path.isdir("models-seed"):
    datas += [("models-seed", "models-seed")]
else:
    # gitignored, so fresh clones won't have it — warn instead of silently
    # shipping a build whose language switching needs a download
    print("WARNING: models-seed/ missing — run scripts/fetch_models.py first "
          "to bundle the multilingual models", flush=True)

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest"],  # tkinter required by overlay.py since v0.7.0
    noarchive=False,
)

# Prune ~780 MB of cuDNN kernels Whisper never uses. Verified empirically:
# real-speech CUDA inference works without them (runtime-compiled engines
# fall back to the bundled NVRTC).
_PRUNE = ("cudnn_adv64_9", "cudnn_engines_precompiled64_9")
a.binaries = [b for b in a.binaries if not any(p in b[0] for p in _PRUNE)]
a.datas = [d for d in a.datas if not any(p in d[0] for p in _PRUNE)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ROAR",
    icon="icon.ico",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ROAR",
)
