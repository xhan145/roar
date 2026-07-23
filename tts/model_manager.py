"""Trusted local Kokoro voice-pack verification and atomic installation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from typing import Callable

import paths

MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_PACK_FILES = 32
_REPARSE_POINT = 0x400


class ModelPackError(RuntimeError):
    category = "invalid_pack"


class ModelPackMissing(ModelPackError):
    category = "missing_pack"


class ModelPackHashMismatch(ModelPackError):
    category = "hash_mismatch"


class ModelPackUnsafe(ModelPackError):
    category = "unsafe_path"


def bundled_manifest_path() -> str:
    return paths.resource_path(os.path.join(
        "tts", "assets", "kokoro-model-manifest.json"))


def canonical_manifest() -> dict:
    return _read_json(bundled_manifest_path())


def default_pack_dir() -> str:
    return paths.tts_model_dir()


def configured_pack_dir(config: dict | None = None) -> str:
    value = (config or {}).get("tts_model_path")
    if isinstance(value, str) and value.strip():
        return os.path.abspath(value)
    return default_pack_dir()


def inspect_pack(pack_dir: str | None = None, *, verify_hashes=True) -> dict:
    pack_dir = os.path.abspath(pack_dir or default_pack_dir())
    result = {
        "installed": False,
        "valid": False,
        "status": "not_installed",
        "error_category": "",
        "model": "Kokoro-82M",
        "model_version": "1.0",
        "package_version": "1.0-roar.1",
        "sample_rate": 24_000,
        "disk_bytes": 0,
        "path": pack_dir,
    }
    try:
        manifest = verify_pack(pack_dir, verify_hashes=verify_hashes)
        result.update(
            installed=True,
            valid=True,
            status="ready",
            model=manifest["model"],
            model_version=manifest["model_version"],
            package_version=manifest["package_version"],
            sample_rate=manifest["sample_rate"],
            disk_bytes=sum(int(f["size"]) for f in manifest["files"]),
        )
    except ModelPackMissing as exc:
        result.update(status="not_installed", error_category=exc.category)
    except ModelPackError as exc:
        result.update(installed=os.path.isdir(pack_dir), status="invalid",
                      error_category=exc.category)
    return result


def verify_pack(pack_dir: str, *, verify_hashes=True) -> dict:
    root = os.path.abspath(pack_dir)
    if not os.path.isdir(root):
        raise ModelPackMissing("local voice pack is not installed")
    if _is_reparse(root):
        raise ModelPackUnsafe("voice-pack root cannot be a reparse point")
    manifest_path = os.path.join(root, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        raise ModelPackMissing("manifest.json is missing")
    if _is_reparse(manifest_path):
        raise ModelPackUnsafe("manifest cannot be a link")
    actual = _read_json(manifest_path)
    expected = canonical_manifest()
    _validate_manifest_shape(actual)
    if _manifest_identity(actual) != _manifest_identity(expected):
        raise ModelPackError("manifest provenance is not supported")

    expected_files = {entry["path"]: entry for entry in expected["files"]}
    actual_files = {entry["path"]: entry for entry in actual["files"]}
    if actual_files != expected_files:
        raise ModelPackError("manifest file inventory does not match ROAR's pin")

    for relative, entry in expected_files.items():
        full = _safe_child(root, relative)
        if not os.path.isfile(full):
            raise ModelPackMissing(f"required file is missing: {relative}")
        if _is_reparse(full):
            raise ModelPackUnsafe(f"linked model file rejected: {relative}")
        if os.path.getsize(full) != int(entry["size"]):
            raise ModelPackHashMismatch(f"size mismatch: {relative}")
        if verify_hashes and _sha256(full) != entry["sha256"]:
            raise ModelPackHashMismatch(f"hash mismatch: {relative}")
    return actual


def install_pack(
    source_dir: str,
    destination: str | None = None,
    *,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Verify, copy only pinned files, verify again, then atomically activate."""
    source = os.path.abspath(source_dir)
    destination = os.path.abspath(destination or default_pack_dir())
    manifest = verify_pack(source, verify_hashes=True)
    parent = os.path.dirname(destination)
    os.makedirs(parent, exist_ok=True)
    if _is_reparse(parent):
        raise ModelPackUnsafe("destination parent cannot be a reparse point")
    stage = tempfile.mkdtemp(prefix=".kokoro-stage-", dir=parent)
    backup = destination + ".previous"
    activated = False
    try:
        files = manifest["files"]
        for index, entry in enumerate(files, 1):
            relative = entry["path"]
            src = _safe_child(source, relative)
            dst = _safe_child(stage, relative)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            _copy_regular_file(src, dst)
            if progress:
                progress(relative, index, len(files))
        shutil.copyfile(os.path.join(source, MANIFEST_NAME),
                        os.path.join(stage, MANIFEST_NAME))
        verify_pack(stage, verify_hashes=True)

        if os.path.lexists(backup):
            _safe_remove_tree(backup, parent)
        if os.path.lexists(destination):
            if _is_reparse(destination):
                raise ModelPackUnsafe("installed destination is a reparse point")
            os.replace(destination, backup)
        os.replace(stage, destination)
        activated = True
        if os.path.isdir(backup):
            _safe_remove_tree(backup, parent)
        return inspect_pack(destination, verify_hashes=False)
    except Exception:
        if not activated and os.path.isdir(backup) and not os.path.exists(destination):
            os.replace(backup, destination)
        raise
    finally:
        if os.path.isdir(stage):
            _safe_remove_tree(stage, parent)


def remove_pack(destination: str | None = None) -> bool:
    destination = os.path.abspath(destination or default_pack_dir())
    parent = os.path.abspath(paths.tts_dir())
    if os.path.commonpath([destination, parent]) != parent:
        raise ModelPackUnsafe("only ROAR's managed voice pack can be removed")
    if not os.path.lexists(destination):
        return False
    if _is_reparse(destination):
        raise ModelPackUnsafe("refusing to follow a reparse point")
    _safe_remove_tree(destination, parent)
    return True


def resolve_model_files(pack_dir: str) -> dict:
    verify_pack(pack_dir, verify_hashes=True)
    return {
        "config": _safe_child(pack_dir, "config.json"),
        "model": _safe_child(pack_dir, "kokoro-v1_0.pth"),
        "voices": _safe_child(pack_dir, "voices"),
    }


def _manifest_identity(manifest):
    return tuple(manifest.get(key) for key in (
        "engine", "model", "model_version", "package_version", "upstream",
        "revision", "sample_rate"))


def _validate_manifest_shape(manifest):
    if not isinstance(manifest, dict):
        raise ModelPackError("manifest must be an object")
    files = manifest.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_PACK_FILES:
        raise ModelPackError("manifest file list is invalid")
    seen = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ModelPackError("manifest file entry is invalid")
        required = ("path", "size", "sha256", "license", "origin")
        if any(key not in entry for key in required):
            raise ModelPackError("manifest file entry is incomplete")
        relative = entry["path"]
        if relative in seen:
            raise ModelPackError("manifest contains duplicate paths")
        seen.add(relative)
        _validate_relative(relative)
        if not isinstance(entry["size"], int) or entry["size"] <= 0:
            raise ModelPackError("manifest size is invalid")
        digest = entry["sha256"]
        if (not isinstance(digest, str) or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)):
            raise ModelPackError("manifest hash is invalid")


def _read_json(path):
    try:
        if os.path.getsize(path) > MAX_MANIFEST_BYTES:
            raise ModelPackError("manifest is too large")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except ModelPackError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelPackError("manifest is unreadable") from exc


def _validate_relative(relative):
    if not isinstance(relative, str) or not relative:
        raise ModelPackUnsafe("empty model path")
    normalized = relative.replace("\\", "/")
    if (normalized.startswith("/") or ":" in normalized
            or any(part in ("", ".", "..") for part in normalized.split("/"))):
        raise ModelPackUnsafe("unsafe model path")
    return normalized


def _safe_child(root, relative):
    normalized = _validate_relative(relative)
    root = os.path.abspath(root)
    full = os.path.abspath(os.path.join(root, *normalized.split("/")))
    if os.path.commonpath([root, full]) != root:
        raise ModelPackUnsafe("model path escapes the pack")
    return full


def _copy_regular_file(source, destination):
    st = os.lstat(source)
    if not stat.S_ISREG(st.st_mode) or _is_reparse(source):
        raise ModelPackUnsafe("only regular model files are accepted")
    with open(source, "rb") as src, open(destination, "xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_reparse(path):
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
        return bool(attrs & _REPARSE_POINT)
    except OSError:
        return False


def _safe_remove_tree(path, allowed_parent):
    full = os.path.abspath(path)
    parent = os.path.abspath(allowed_parent)
    if os.path.commonpath([full, parent]) != parent or full == parent:
        raise ModelPackUnsafe("unsafe removal target")
    if _is_reparse(full):
        raise ModelPackUnsafe("refusing to remove through a reparse point")
    shutil.rmtree(full)
