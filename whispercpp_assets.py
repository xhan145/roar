"""Download + verify the whisper.cpp Vulkan binary and GGML models on first GPU
use. Everything is checksum-pinned (verified by a live spike on 2026-07-10); a
failed or partial download never leaves a "present" asset behind. After the
one-time fetch, transcription is 100% offline. Pure helpers here are unit-tested;
the network functions are exercised by the live proxy test.
"""
import hashlib
import os
import tempfile
import urllib.request
import zipfile

_HF = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

# Prebuilt Vulkan whisper.cpp for Windows (MIT). Ships whisper-server.exe +
# ggml-vulkan.dll; relies on the system Vulkan loader (vulkan-1.dll, installed
# with GPU drivers). Verified: loads on GPU, correct transcript, ~337ms/11s clip.
BIN = {
    "url": "https://github.com/jerryshell/whisper.cpp-windows-vulkan-bin/"
           "releases/download/v1.0.0/whisper.cpp-windows-vulkan.zip",
    "sha256": "a5d408c72e460433b39875f74a0b6e27e60a3724301d478fe9873db7ff4098e0",
    "size": 18340920,
}

# GGML models (HF ggerganov/whisper.cpp). sha256 == HF LFS oid.
MODELS = {
    "base.en":  {"url": f"{_HF}/ggml-base.en.bin",
                 "sha256": "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"},
    "small.en": {"url": f"{_HF}/ggml-small.en.bin",
                 "sha256": "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"},
    "base":     {"url": f"{_HF}/ggml-base.bin",
                 "sha256": "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"},
    "small":    {"url": f"{_HF}/ggml-small.bin",
                 "sha256": "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"},
    "tiny.en":  {"url": f"{_HF}/ggml-tiny.en.bin",
                 "sha256": "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"},
}

SERVER_EXE = "whisper-server.exe"


def model_for(language: str) -> str:
    """Default GGML model for the Vulkan path — English-optimized when English,
    else multilingual small (parity with the CPU model choice)."""
    return "small.en" if (language or "en") == "en" else "small"


def sha256_of(path, _bufsize: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path, expected_sha: str) -> bool:
    """True iff the file exists and its content sha256 matches."""
    try:
        return os.path.isfile(path) and sha256_of(path) == expected_sha
    except OSError:
        return False


def server_path(bin_dir) -> str:
    return os.path.join(bin_dir, SERVER_EXE)


def bin_present(bin_dir) -> bool:
    return os.path.isfile(server_path(bin_dir))


def model_path(models_dir, name) -> str:
    return os.path.join(models_dir, f"ggml-{name}.bin")


def model_present(models_dir, name) -> bool:
    spec = MODELS.get(name)
    return bool(spec) and verify(model_path(models_dir, name), spec["sha256"])


def _download(url, dest, expected_sha=None, progress=None):
    """Download to a temp file next to dest, verify sha256, then atomically
    rename into place — dest never exists in a partial/corrupt state."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), suffix=".part")
    os.close(fd)
    try:
        with urllib.request.urlopen(url) as r, open(tmp, "wb") as out:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done, total)
        if expected_sha and sha256_of(tmp) != expected_sha:
            raise RuntimeError(f"checksum mismatch downloading {url}")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def ensure_model(models_dir, name, log=print, progress=None) -> str:
    """Return the GGML model path, downloading + verifying it if absent."""
    spec = MODELS[name]
    dest = model_path(models_dir, name)
    if verify(dest, spec["sha256"]):
        return dest
    log(f"downloading GGML model {name} (~{round(_size_hint(name))} MB)...")
    _download(spec["url"], dest, spec["sha256"], progress)
    return dest


def ensure_binary(bin_dir, log=print, progress=None) -> str:
    """Ensure the Vulkan whisper-server binary is unpacked in bin_dir; return the
    server exe path. Downloads + checksum-verifies the zip, then extracts."""
    if bin_present(bin_dir):
        return server_path(bin_dir)
    os.makedirs(bin_dir, exist_ok=True)
    fd, tmp_zip = tempfile.mkstemp(dir=bin_dir, suffix=".zip")
    os.close(fd)
    try:
        log("downloading Vulkan whisper.cpp binary (~18 MB)...")
        _download(BIN["url"], tmp_zip, BIN["sha256"], progress)
        with zipfile.ZipFile(tmp_zip) as z:
            z.extractall(bin_dir)   # files sit at the archive root
    finally:
        if os.path.exists(tmp_zip):
            try:
                os.remove(tmp_zip)
            except OSError:
                pass
    if not bin_present(bin_dir):
        raise RuntimeError("whisper-server.exe missing after extracting the Vulkan build")
    return server_path(bin_dir)


def _size_hint(name) -> float:
    return {"tiny.en": 78, "base.en": 148, "base": 148,
            "small.en": 488, "small": 488}.get(name, 200)
