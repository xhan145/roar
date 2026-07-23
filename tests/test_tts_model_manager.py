import hashlib
import json
import os

import pytest

import paths
from tts import model_manager as mm


def make_manifest(files):
    return {
        "engine": "kokoro",
        "model": "Kokoro-82M",
        "model_version": "1.0",
        "package_version": "test",
        "upstream": "hexgrad/Kokoro-82M",
        "revision": "abc",
        "sample_rate": 24000,
        "files": files,
    }


def make_pack(root, entries):
    files = []
    for relative, content in entries.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        files.append({
            "path": relative.replace("\\", "/"),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "license": "Apache-2.0",
            "origin": "https://huggingface.co/hexgrad/Kokoro-82M",
        })
    manifest = make_manifest(files)
    (root / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    return manifest


def test_verify_and_atomic_install(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    manifest = make_pack(source, {
        "config.json": b"{}",
        "kokoro-v1_0.pth": b"safe weights",
        "voices/af_heart.pt": b"safe voice",
    })
    monkeypatch.setattr(mm, "canonical_manifest", lambda: manifest)
    destination = tmp_path / "managed" / "kokoro"
    installed = mm.install_pack(str(source), str(destination))
    assert installed["valid"]
    assert mm.verify_pack(str(destination))["package_version"] == "test"
    assert (destination / "voices" / "af_heart.pt").read_bytes() == b"safe voice"


def test_hash_mismatch_is_a_distinct_failure(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    manifest = make_pack(source, {"config.json": b"{}"})
    monkeypatch.setattr(mm, "canonical_manifest", lambda: manifest)
    (source / "config.json").write_bytes(b"tampered")
    with pytest.raises(mm.ModelPackHashMismatch):
        mm.verify_pack(str(source))


def test_manifest_path_traversal_is_rejected(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    manifest = make_manifest([{
        "path": "../escape.pt",
        "size": 1,
        "sha256": "0" * 64,
        "license": "Apache-2.0",
        "origin": "https://example.invalid",
    }])
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(mm, "canonical_manifest", lambda: manifest)
    with pytest.raises(mm.ModelPackUnsafe):
        mm.verify_pack(str(source))


def test_remove_refuses_paths_outside_managed_root(monkeypatch, tmp_path):
    managed = tmp_path / "tts"
    managed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(paths, "tts_dir", lambda: str(managed))
    with pytest.raises(mm.ModelPackUnsafe):
        mm.remove_pack(str(outside))
