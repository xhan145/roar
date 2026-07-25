from pathlib import Path


def test_main_requirements_keep_kokoro_in_optional_worker():
    main = Path("requirements.txt").read_text(encoding="utf-8")
    optional = Path("requirements-tts.txt").read_text(encoding="utf-8")
    assert "\nkokoro" not in main
    assert "\ntorch" not in main
    assert "kokoro==0.9.4" in optional
    assert "torch==2.7.1" in optional


def test_pyinstaller_ships_protocol_worker_manifest_and_uia_not_model():
    spec = Path("roar.spec").read_text(encoding="utf-8")
    assert '("tts/worker.py", "tts")' in spec
    assert "kokoro-model-manifest.json" in spec
    assert "THIRD_PARTY_NOTICES.md" in spec
    assert '("licenses", "licenses")' in spec
    assert '"uiautomation"' in spec
    assert "kokoro-v1_0.pth" not in spec
    assert "af_heart.pt" not in spec


def test_no_model_or_voice_binary_is_tracked():
    roots = [Path("tts"), Path("tests"), Path("scripts")]
    binaries = [
        path for root in roots for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".pth", ".pt", ".onnx"}
    ]
    assert binaries == []


def test_optional_prepare_commands_are_never_called_by_application():
    app = Path("app.py").read_text(encoding="utf-8")
    assert "prepare_kokoro_runtime" not in app
    assert "prepare_kokoro_voice_pack" not in app
