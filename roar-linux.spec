# PyInstaller spec for the Linux AppImage build.
# Build through linux/build_appimage.sh so output paths and verification remain
# isolated from the Windows roar.spec build.
from PyInstaller.utils.hooks import collect_all


datas, binaries, hiddenimports = [], [], []
for pkg in (
    "faster_whisper",
    "ctranslate2",
    "av",
    "onnxruntime",
    "webview",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(pkg)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

hiddenimports += [
    "webview.platforms.gtk",
    "gi",
    "pynput.keyboard._xorg",
]

datas += [
    ("settings.html", "."),
    ("transcript.html", "."),
    ("fob.png", "."),
    ("assets", "assets"),
    ("licenses", "licenses"),
    ("THIRD_PARTY_NOTICES.md", "."),
    ("tts/worker.py", "tts"),
    ("tts/assets/kokoro-model-manifest.json", "tts/assets"),
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "pytest",
        "uiautomation",
        "comtypes",
        "PyAudioWPatch",
        "backends.onnx_directml_spike",
        "whispercpp_assets",
        "backends.whispercpp_vulkan",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ROAR-linux",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ROAR-linux",
)
