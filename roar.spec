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
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [("settings.html", ".")]

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
