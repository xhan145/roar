"""The Settings window runs as a separate, lightweight process. It must NEVER
import the ML/CUDA stack at module load — acceleration facts come from config +
status.json (written by the tray), read-only."""
import ast
import pathlib

BANNED = {"transcriber", "faster_whisper", "ctranslate2", "hardware_accel",
          "torch", "onnxruntime", "numpy", "kokoro", "misaki", "transformers"}


def _top_level_imports(py):
    tree = ast.parse(pathlib.Path(py).read_text(encoding="utf-8"))
    mods = set()
    for node in tree.body:  # MODULE level only — lazy imports in functions are fine
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def test_settings_ui_has_no_top_level_ml_import():
    assert not (_top_level_imports("settings_ui.py") & BANNED)
