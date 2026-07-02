# FlowLocal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows tray app: hold Ctrl+Win to dictate, release to have locally-transcribed text typed into the focused window — 100% local, free, no telemetry.

**Architecture:** Threaded state machine (IDLE→RECORDING→TRANSCRIBING→IDLE): pystray tray loop on main thread, `keyboard` hook thread for hotkeys, sounddevice callback thread for capture, one worker thread owning the warm faster-whisper model.

**Tech Stack:** Python 3.14.5, faster-whisper 1.2.1 (ctranslate2 4.8.0), sounddevice, keyboard, pystray, Pillow, pyperclip, pytest.

## Global Constraints

- Project root: `C:\Users\xhan1\flowlocal` (own git repo, branch `main`).
- Shell: Git Bash (MINGW64). venv via `python -m venv venv`; invoke the venv interpreter directly as `venv/Scripts/python.exe` (no reliance on activation between shell calls).
- All deps pinned in `requirements.txt`. No cloud APIs, no API keys, no telemetry.
- Whisper models cache to project-local `models/` (`download_root="models"`), gitignored.
- Default hotkeys: push-to-talk `ctrl+windows` (hold), toggle `ctrl+windows+space`.
- Model policy `"auto"`: CUDA present → try `distil-large-v3` float16 on cuda; any failure → `small.en` int8 on cpu + tray notification. Runtime CUDA failure during inference → one CPU retry.
- Never inject when processed transcript is empty. Trailing space appended unless text ends with newline.
- Tray state colors (shape AND color differ per state): idle/loading gray `#D1D5DB`, recording red `#DC2626`, transcribing blue `#2563EB`, error amber `#D97706`.
- Startup stdout markers (exact strings, consumed by smoke test): `FlowLocal: model loaded`, `FlowLocal: hotkeys registered`, `FlowLocal: tray ready`, `FlowLocal: clean exit`.
- Commit after every task with the message given in the task.

---

### Task 1: Scaffolding, venv, pinned dependencies

**Files:**
- Create: `.gitignore`, `requirements.txt`, `requirements-gpu.txt`

**Interfaces:**
- Produces: working venv at `venv/` with all deps importable; later tasks run `venv/Scripts/python.exe -m pytest`.

- [ ] **Step 1: Write `.gitignore`**

```gitignore
venv/
models/
__pycache__/
*.pyc
.pytest_cache/
config.json
*.wav
```

- [ ] **Step 2: Write `requirements.txt`**

```text
faster-whisper==1.2.1
ctranslate2==4.8.0
sounddevice==0.5.5
keyboard==0.13.5
pystray==0.19.5
Pillow==12.3.0
pyperclip==1.11.0
numpy==2.5.0
pytest==9.1.1
```

- [ ] **Step 3: Write `requirements-gpu.txt`** (optional CUDA runtime DLLs; exact pins recorded after install in Task 9 if used) **and an empty root `conftest.py`** (makes the project root importable from `tests/` under pytest)

```text
# Optional: enables CUDA inference (cuBLAS + cuDNN DLLs). CPU works without this file.
nvidia-cublas-cu12>=12.4,<13
nvidia-cudnn-cu12>=9.1,<10
```

`conftest.py`:
```python
# Root conftest: makes pytest add the project root to sys.path so tests can
# import the app modules (commands, config, recorder, ...) directly.
```

- [ ] **Step 4: Create venv and install**

Run (from `C:\Users\xhan1\flowlocal`):
```bash
python -m venv venv
venv/Scripts/python.exe -m pip install --upgrade pip
venv/Scripts/python.exe -m pip install -r requirements.txt
```
Expected: exit 0, no ERROR lines.

- [ ] **Step 5: Verify imports**

```bash
venv/Scripts/python.exe -c "import faster_whisper, ctranslate2, sounddevice, keyboard, pystray, PIL, pyperclip, numpy; print('imports OK'); print('cuda devices:', ctranslate2.get_cuda_device_count())"
```
Expected: `imports OK` and a cuda device count line.

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt requirements-gpu.txt conftest.py
git commit -m "chore: scaffolding, pinned requirements, venv setup"
```

---

### Task 2: commands.py — text pipeline (pure)

**Files:**
- Create: `commands.py`
- Test: `tests/test_commands.py`

**Interfaces:**
- Produces: `process(text: str, replacements: dict[str, str]) -> str` — returns `""` when nothing injectable; `apply_replacements(text, replacements) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_commands.py`:
```python
import commands

REPL = {"new line": "\n", "new paragraph": "\n\n"}


def test_replacement_absorbs_surrounding_punctuation():
    out = commands.process("Hello there. New line. This is a test.", REPL)
    assert out == "Hello there.\nThis is a test."


def test_new_paragraph():
    out = commands.process("First part, new paragraph, second part.", REPL)
    assert out == "First part\n\nsecond part."


def test_capitalizes_first_letter():
    assert commands.process("hello world.", REPL) == "Hello world."


def test_strips_whitespace():
    assert commands.process("  hello  ", REPL) == "Hello"


def test_empty_returns_empty():
    assert commands.process("", REPL) == ""
    assert commands.process("   ", REPL) == ""


def test_solo_new_line_survives():
    assert commands.process("new line", REPL) == "\n"


def test_no_replacements_dict():
    assert commands.process("plain text", {}) == "Plain text"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_commands.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'commands'`.

- [ ] **Step 3: Write `commands.py`**

```python
"""Spoken-command replacement and text normalization. Pure functions."""
import re


def apply_replacements(text: str, replacements: dict) -> str:
    """Replace spoken phrases (case-insensitive, word-bounded), absorbing
    surrounding punctuation and spaces so 'foo. New line. bar' -> 'foo.\nbar'."""
    for phrase in sorted(replacements, key=len, reverse=True):
        repl = replacements[phrase]
        # Leading side absorbs only whitespace + an optional comma (a sentence-
        # ending period before the command must survive: "there. New line" ->
        # "there.\n"). Trailing side absorbs the command's own punctuation.
        pattern = re.compile(
            r"[ \t]*,?[ \t]*\b" + re.escape(phrase) + r"\b[ \t]*[,.!?;:]?[ \t]*",
            re.IGNORECASE,
        )
        text = pattern.sub(lambda m, r=repl: r, text)
    return text


def process(text: str, replacements: dict) -> str:
    """Full pipeline: strip -> replacements -> capitalize first letter.
    Returns '' when there is nothing worth injecting."""
    text = text.strip()
    if not text:
        return ""
    text = apply_replacements(text, replacements)
    for i, ch in enumerate(text):
        if ch.isalpha():
            if ch.islower():
                text = text[:i] + ch.upper() + text[i + 1:]
            break
    if not text.strip():
        # whitespace-only result: keep it only if it came from an explicit
        # newline command (e.g. user said just "new line")
        return text if "\n" in text else ""
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_commands.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add commands.py tests/test_commands.py
git commit -m "feat: spoken-command replacement + text normalization"
```

---

### Task 3: config.py — defaults, load/save

**Files:**
- Create: `config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `DEFAULTS: dict`, `load(path=None) -> dict`, `save(cfg, path=None)`, `PATH` (default config.json path next to the module). `load()` creates the file with defaults on first run; user keys override defaults; user `replacements` merge into (not replace) default replacements.

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
import json
import config


def test_first_run_creates_file_with_defaults(tmp_path):
    p = tmp_path / "config.json"
    cfg = config.load(str(p))
    assert p.exists()
    assert cfg == config.DEFAULTS
    assert cfg is not config.DEFAULTS  # must be a copy


def test_user_overrides_merge(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"model": "tiny.en", "replacements": {"smiley": ":)"}}))
    cfg = config.load(str(p))
    assert cfg["model"] == "tiny.en"
    assert cfg["replacements"]["smiley"] == ":)"
    assert cfg["replacements"]["new line"] == "\n"  # defaults preserved
    assert cfg["hotkey_ptt"] == "ctrl+windows"


def test_save_round_trip(tmp_path):
    p = tmp_path / "config.json"
    cfg = config.load(str(p))
    cfg["paste_fallback"] = True
    config.save(cfg, str(p))
    assert config.load(str(p))["paste_fallback"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`.

- [ ] **Step 3: Write `config.py`**

```python
"""config.json load/save with sane defaults."""
import copy
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS = {
    "hotkey_ptt": "ctrl+windows",
    "hotkey_toggle": "ctrl+windows+space",
    "model": "auto",
    "input_device": None,
    "paste_fallback": False,
    "silence_rms_threshold": 0.005,
    "min_duration_s": 0.3,
    "tones_enabled": True,
    "language": "en",
    "replacements": {"new line": "\n", "new paragraph": "\n\n"},
}


def load(path=None):
    path = path or PATH
    cfg = copy.deepcopy(DEFAULTS)
    if not os.path.exists(path):
        save(cfg, path)
        return cfg
    with open(path, encoding="utf-8") as f:
        user = json.load(f)
    for key, value in user.items():
        if key == "replacements" and isinstance(value, dict):
            cfg["replacements"].update(value)
        else:
            cfg[key] = value
    return cfg


def save(cfg, path=None):
    path = path or PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config load/save with defaults and merge"
```

---

### Task 4: recorder.py — capture, energy gate, tones

**Files:**
- Create: `recorder.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Produces: `SAMPLE_RATE = 16000`; `rms(audio) -> float`; `passes_gate(audio, threshold, min_duration_s) -> bool`; `make_tone(freq_hz, ms) -> np.ndarray`; `play_tone(kind, enabled=True)` for kind in `{"start","stop","error"}`; `class Recorder(device=None)` with `.start()`, `.stop() -> np.ndarray` (float32 mono 16 kHz), `.device` attribute (None = system default).
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Write the failing tests**

`tests/test_gate.py`:
```python
import numpy as np
import recorder


def test_zeros_buffer_rejected():
    audio = np.zeros(recorder.SAMPLE_RATE, dtype=np.float32)  # 1s of silence
    assert recorder.passes_gate(audio, threshold=0.005, min_duration_s=0.3) is False


def test_too_short_rejected():
    audio = 0.5 * np.ones(int(0.1 * recorder.SAMPLE_RATE), dtype=np.float32)
    assert recorder.passes_gate(audio, threshold=0.005, min_duration_s=0.3) is False


def test_loud_long_signal_passes():
    t = np.linspace(0, 1, recorder.SAMPLE_RATE, endpoint=False)
    audio = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    assert recorder.passes_gate(audio, threshold=0.005, min_duration_s=0.3) is True


def test_empty_buffer_rejected():
    assert recorder.passes_gate(np.zeros(0, dtype=np.float32), 0.005, 0.3) is False


def test_make_tone_shape_and_range():
    tone = recorder.make_tone(880, 80)
    assert tone.dtype == np.float32
    assert len(tone) == int(recorder.SAMPLE_RATE * 0.08)
    assert np.max(np.abs(tone)) <= 0.11
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recorder'`.

- [ ] **Step 3: Write `recorder.py`**

```python
"""Microphone capture (16 kHz mono float32), RMS energy gate, feedback tones."""
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


def passes_gate(audio: np.ndarray, threshold: float, min_duration_s: float) -> bool:
    """True when the clip is long enough and loud enough to be worth transcribing."""
    if audio.size < int(min_duration_s * SAMPLE_RATE):
        return False
    return rms(audio) >= threshold


def make_tone(freq_hz: float, ms: int, amplitude: float = 0.1) -> np.ndarray:
    n = int(SAMPLE_RATE * ms / 1000)
    t = np.linspace(0, ms / 1000, n, endpoint=False)
    tone = (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)
    fade = max(1, int(SAMPLE_RATE * 0.005))  # 5 ms fade to avoid clicks
    env = np.ones(n, dtype=np.float32)
    env[:fade] = np.linspace(0.0, 1.0, fade)
    env[-fade:] = np.linspace(1.0, 0.0, fade)
    return tone * env


def _build_tones():
    gap = np.zeros(int(SAMPLE_RATE * 0.04), dtype=np.float32)
    blip = make_tone(220, 70)
    return {
        "start": make_tone(880, 80),
        "stop": make_tone(440, 80),
        "error": np.concatenate([blip, gap, blip]),
    }


TONES = _build_tones()


def play_tone(kind: str, enabled: bool = True):
    if not enabled:
        return
    try:
        sd.play(TONES[kind], SAMPLE_RATE)  # non-blocking, default output device
    except Exception:
        pass  # audio feedback is never worth crashing over


class Recorder:
    """Buffers microphone audio between start() and stop()."""

    def __init__(self, device=None):
        self.device = device  # None = system default input
        self._stream = None
        self._chunks = []
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        self._chunks.append(indata[:, 0].copy())

    def stop(self) -> np.ndarray:
        with self._lock:
            if self._stream is None:
                return np.zeros(0, dtype=np.float32)
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._chunks)


def list_input_devices():
    """[(index, name)] for input-capable devices on the default host API,
    prefixed with (None, 'System default')."""
    devices = [(None, "System default")]
    try:
        hostapi_index = sd.default.hostapi
        if hostapi_index < 0:
            hostapi_index = 0
        hostapi = sd.query_hostapis(hostapi_index)
        for idx in hostapi["devices"]:
            info = sd.query_devices(idx)
            if info["max_input_channels"] > 0:
                devices.append((idx, info["name"]))
    except Exception:
        pass
    return devices
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_gate.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add recorder.py tests/test_gate.py
git commit -m "feat: mic capture, RMS silence gate, feedback tones"
```

---

### Task 5: tray_icons.py — state icons

**Files:**
- Create: `tray_icons.py`
- Test: `tests/test_icons.py`

**Interfaces:**
- Produces: `make_icon(state: str, size: int = 64) -> PIL.Image.Image` for state in `{"idle","loading","recording","transcribing","error"}`; `COLORS: dict`.

- [ ] **Step 1: Write the failing tests**

`tests/test_icons.py`:
```python
import tray_icons

STATES = ["idle", "loading", "recording", "transcribing", "error"]


def test_all_states_render_64px_rgba():
    for state in STATES:
        img = tray_icons.make_icon(state)
        assert img.size == (64, 64)
        assert img.mode == "RGBA"


def test_states_visually_distinct():
    rendered = {s: tray_icons.make_icon(s).tobytes() for s in STATES}
    assert rendered["idle"] != rendered["recording"]
    assert rendered["recording"] != rendered["transcribing"]
    assert rendered["transcribing"] != rendered["error"]
    # shape decoration differs even between same-color states
    assert rendered["idle"] != rendered["loading"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_icons.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tray_icons'`.

- [ ] **Step 3: Write `tray_icons.py`**

```python
"""Pillow-drawn tray icons. State is encoded in shape AND color (a11y)."""
from PIL import Image, ImageDraw

COLORS = {
    "idle": "#D1D5DB",
    "loading": "#D1D5DB",
    "recording": "#DC2626",
    "transcribing": "#2563EB",
    "error": "#D97706",
}


def make_icon(state: str, size: int = 64) -> Image.Image:
    color = COLORS[state]
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # microphone: capsule + cradle arc + stem + base
    d.rounded_rectangle([24, 8, 40, 36], radius=8, fill=color)
    d.arc([16, 18, 48, 44], start=0, end=180, fill=color, width=4)
    d.line([32, 44, 32, 52], fill=color, width=4)
    d.line([22, 54, 42, 54], fill=color, width=4)
    # state decoration, bottom-right corner
    if state == "recording":
        d.ellipse([46, 44, 60, 58], fill=color)
    elif state in ("transcribing", "loading"):
        d.arc([44, 42, 60, 58], start=300, end=210, fill=color, width=4)
    elif state == "error":
        d.line([53, 40, 53, 50], fill=color, width=4)
        d.ellipse([50, 53, 56, 59], fill=color)
    return img
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_icons.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tray_icons.py tests/test_icons.py
git commit -m "feat: Pillow-drawn tray state icons"
```

---

### Task 6: transcriber.py — faster-whisper wrapper + headless speech test

**Files:**
- Create: `transcriber.py`
- Test: `tests/test_transcriber.py`

**Interfaces:**
- Produces: `detect_device() -> "cuda"|"cpu"`; `resolve_model(name, device) -> str`; `class Transcriber(model_name="auto", models_dir="models", language="en", log=print, force_device=None)` with `.load(model_name=None)`, `.transcribe(audio: np.ndarray | str) -> str`, `.description() -> str` (e.g. `small.en (cpu)`), `.active_model`, `.device`.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Write the failing test** (generates real speech via Windows SAPI TTS — no new deps; first run downloads small.en ~460 MB to `models/`)

`tests/test_transcriber.py`:
```python
import os
import subprocess

import pytest

from transcriber import Transcriber, detect_device, resolve_model

SPOKEN = "Hello world. This is a local dictation test."
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_resolve_model_auto():
    assert resolve_model("auto", "cuda") == "distil-large-v3"
    assert resolve_model("auto", "cpu") == "small.en"
    assert resolve_model("tiny.en", "cuda") == "tiny.en"


def test_detect_device_returns_valid():
    assert detect_device() in ("cuda", "cpu")


@pytest.fixture(scope="module")
def speech_wav(tmp_path_factory):
    path = tmp_path_factory.mktemp("audio") / "speech.wav"
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{path}'); "
        f"$s.Speak('{SPOKEN}'); "
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=120)
    assert path.exists() and path.stat().st_size > 10000
    return str(path)


def test_transcribes_real_speech(speech_wav):
    t = Transcriber(model_name="small.en", models_dir=os.path.join(ROOT, "models"),
                    force_device="cpu")
    t.load()
    text = t.transcribe(speech_wav).lower()
    assert "hello" in text
    assert "test" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_transcriber.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'transcriber'`.

- [ ] **Step 3: Write `transcriber.py`**

```python
"""faster-whisper wrapper: device autodetect, model management, CPU fallback."""
import importlib.util
import os
import pathlib

from faster_whisper import WhisperModel

GPU_MODEL = "distil-large-v3"
CPU_MODEL = "small.en"


def detect_device() -> str:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def resolve_model(name: str, device: str) -> str:
    if name != "auto":
        return name
    return GPU_MODEL if device == "cuda" else CPU_MODEL


def _add_nvidia_dll_dirs():
    """Make pip-installed cuBLAS/cuDNN DLLs (requirements-gpu.txt) loadable."""
    for pkg in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(pkg)
        except (ImportError, ModuleNotFoundError):
            continue
        if spec and spec.submodule_search_locations:
            bin_dir = pathlib.Path(list(spec.submodule_search_locations)[0]) / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))


class Transcriber:
    def __init__(self, model_name="auto", models_dir="models", language="en",
                 log=print, force_device=None):
        self.requested = model_name
        self.models_dir = models_dir
        self.language = language
        self.log = log
        self.force_device = force_device
        self._model = None
        self.active_model = None
        self.device = None

    def description(self) -> str:
        if self._model is None:
            return "no model"
        return f"{self.active_model} ({self.device})"

    def load(self, model_name=None):
        """Load the model, trying CUDA first (when present), falling back to CPU."""
        name = model_name or self.requested
        device = self.force_device or detect_device()
        attempts = []
        if device == "cuda":
            attempts.append((resolve_model(name, "cuda"), "cuda", "float16"))
        attempts.append((resolve_model(name, "cpu"), "cpu", "int8"))
        last_err = None
        for model, dev, compute in attempts:
            try:
                if dev == "cuda":
                    _add_nvidia_dll_dirs()
                self.log(f"loading {model} on {dev} ({compute})...")
                self._model = WhisperModel(model, device=dev, compute_type=compute,
                                           download_root=self.models_dir)
                self.active_model, self.device = model, dev
                return
            except Exception as e:  # missing cuDNN, OOM, bad model name on gpu...
                last_err = e
                self.log(f"load failed for {model} on {dev}: {e}")
        raise RuntimeError(f"could not load any model: {last_err}")

    def _run(self, audio) -> str:
        # beam_size=1 + no VAD: measured 1.66s vs 3.7-4.4s for a ~4s clip on CPU
        # small.en with identical output. The app's RMS gate already rejects
        # silence, which is what vad_filter would protect against.
        segments, _info = self._model.transcribe(
            audio, language=self.language, beam_size=1, vad_filter=False)
        return " ".join(seg.text.strip() for seg in segments).strip()

    def transcribe(self, audio) -> str:
        """audio: float32 mono 16 kHz ndarray, or a path to an audio file."""
        if self._model is None:
            raise RuntimeError("model not loaded")
        try:
            return self._run(audio)
        except Exception as e:
            if self.device == "cuda":
                # CUDA can fail only at inference time (e.g. missing cudnn ops).
                self.log(f"cuda inference failed ({e}); retrying on cpu")
                self.force_device = "cpu"
                self.load()
                return self._run(audio)
            raise
```

- [ ] **Step 4: Run tests to verify they pass** (first run downloads small.en)

Run: `venv/Scripts/python.exe -m pytest tests/test_transcriber.py -v`
Expected: 3 passed. Note transcription wall time for the README latency claim.

- [ ] **Step 5: Commit**

```bash
git add transcriber.py tests/test_transcriber.py
git commit -m "feat: faster-whisper transcriber with CUDA autodetect + CPU fallback"
```

---

### Task 7: injector.py — SendInput injection + clipboard fallback

**Files:**
- Create: `injector.py`
- Test: `tests/test_injector.py`

**Interfaces:**
- Produces: `prepare(text) -> str | None` (pure: returns final string with trailing space, or None if nothing to inject); `inject_text(text, paste_fallback=False) -> bool`.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Write the failing tests** (integration tests use a real focused tkinter Entry — requires an interactive desktop, which this machine has)

`tests/test_injector.py`:
```python
import time
import tkinter as tk

import pyperclip
import pytest

import injector


def test_prepare_appends_trailing_space():
    assert injector.prepare("hello") == "hello "


def test_prepare_keeps_trailing_newline():
    assert injector.prepare("hello\n") == "hello\n"


def test_prepare_rejects_empty():
    assert injector.prepare("") is None
    assert injector.prepare("   ") is None


def test_prepare_allows_bare_newline():
    assert injector.prepare("\n") == "\n"


def _run_injection(text, paste_fallback):
    import threading

    root = tk.Tk()
    root.attributes("-topmost", True)
    entry = tk.Entry(root, width=40)
    entry.pack()
    root.update()
    entry.focus_force()
    root.update()
    time.sleep(0.5)
    # inject on a thread so the Tk event loop can pump WHILE injection runs —
    # the paste fallback restores the clipboard 300ms after Ctrl+V, and the
    # target must process the paste before that restore happens.
    result = {}
    th = threading.Thread(
        target=lambda: result.update(ok=injector.inject_text(text, paste_fallback=paste_fallback)))
    th.start()
    deadline = time.time() + 8
    while time.time() < deadline and (th.is_alive() or not entry.get()):
        root.update()
        time.sleep(0.02)
    th.join(timeout=1)
    root.update()
    value = entry.get()
    root.destroy()
    assert result.get("ok") is True
    return value


def test_sendinput_types_into_focused_window():
    assert _run_injection("hello local", paste_fallback=False) == "hello local "


def test_paste_fallback_and_clipboard_restored():
    pyperclip.copy("sentinel-before")
    assert _run_injection("pasted text", paste_fallback=True) == "pasted text "
    assert pyperclip.paste() == "sentinel-before"


def test_inject_empty_returns_false():
    assert injector.inject_text("", paste_fallback=False) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_injector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'injector'`.

- [ ] **Step 3: Write `injector.py`**

```python
"""Text injection: SendInput unicode typing (primary), clipboard paste (fallback)."""
import time

import keyboard


def prepare(text):
    """Final injectable string (trailing space added), or None when empty.
    A bare newline (spoken 'new line' alone) is injectable."""
    if not text:
        return None
    if not text.strip():
        return text if "\n" in text else None
    return text if text.endswith("\n") else text + " "


def inject_text(text, paste_fallback=False) -> bool:
    out = prepare(text)
    if out is None:
        return False
    if paste_fallback:
        return _paste(out)
    keyboard.write(out, delay=0)  # SendInput with KEYEVENTF_UNICODE
    return True


def _paste(out) -> bool:
    import pyperclip
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(out)
    keyboard.send("ctrl+v")
    time.sleep(0.3)  # let the target app read the clipboard before restoring
    try:
        if old is not None:
            pyperclip.copy(old)
    except Exception:
        pass
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_injector.py -v`
Expected: 7 passed (two of them briefly flash a small topmost window).

- [ ] **Step 5: Commit**

```bash
git add injector.py tests/test_injector.py
git commit -m "feat: SendInput unicode injection + clipboard-paste fallback"
```

---

### Task 8: app.py — tray, hotkeys, state machine, single instance

**Files:**
- Create: `app.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: `config.load/save`, `commands.process`, `injector.inject_text`, `recorder.Recorder/passes_gate/play_tone/list_input_devices`, `transcriber.Transcriber`, `tray_icons.make_icon`.
- Produces: `python app.py` (normal run), `python app.py --smoke` (starts, waits for model load, quits by itself, exits 0). Stdout markers exactly: `FlowLocal: model loaded`, `FlowLocal: hotkeys registered`, `FlowLocal: tray ready`, `FlowLocal: clean exit`.

- [ ] **Step 1: Write the failing smoke test**

`tests/test_smoke.py`:
```python
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_smoke_startup_and_clean_exit():
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--smoke"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        out, _ = proc.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    assert "FlowLocal: hotkeys registered" in out
    assert "FlowLocal: tray ready" in out
    assert "FlowLocal: model loaded" in out
    assert "FlowLocal: clean exit" in out
    assert proc.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_smoke.py -v`
Expected: FAIL — app.py does not exist (`No such file or directory` from the subprocess, non-zero returncode).

- [ ] **Step 3: Write `app.py`**

```python
"""FlowLocal — local voice-to-text tray app. Entry point."""
import argparse
import ctypes
import os
import queue
import subprocess
import sys
import threading

import keyboard
import pystray
from pystray import Menu, MenuItem as Item

import commands
import config as config_mod
import injector
import recorder as recorder_mod
import tray_icons
from transcriber import Transcriber

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Global\\FlowLocalSingleton"

MODIFIER_ALIASES = {
    "ctrl": {"ctrl", "left ctrl", "right ctrl"},
    "windows": {"windows", "left windows", "right windows"},
    "alt": {"alt", "left alt", "right alt", "alt gr"},
    "shift": {"shift", "left shift", "right shift"},
}

MODEL_CHOICES = ["auto", "tiny.en", "base.en", "small.en", "medium.en", "distil-large-v3"]


def acquire_single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def parse_chord(hotkey: str):
    return [k.strip().lower() for k in hotkey.split("+") if k.strip()]


class FlowLocalApp:
    IDLE, LOADING, RECORDING, TRANSCRIBING = "idle", "loading", "recording", "transcribing"

    def __init__(self, cfg, smoke=False):
        self.cfg = cfg
        self.smoke = smoke
        self.state = self.LOADING
        self.session_mode = None  # "ptt" | "toggle"
        self.pressed = set()
        self.state_lock = threading.Lock()
        self.jobs = queue.Queue()
        self.last_transcript = ""
        self.ptt_chord = parse_chord(cfg["hotkey_ptt"])
        self.recorder = recorder_mod.Recorder(device=cfg["input_device"])
        self.transcriber = Transcriber(model_name=cfg["model"], language=cfg["language"],
                                       log=self.log)
        self.model_ready = threading.Event()
        self.icon = pystray.Icon("FlowLocal", tray_icons.make_icon(self.LOADING),
                                 "FlowLocal", menu=self._build_menu())
        self.worker = threading.Thread(target=self._worker, daemon=True)

    # -- logging / notifications ------------------------------------------
    def log(self, msg):
        print(f"FlowLocal: {msg}", flush=True)

    def notify(self, msg):
        self.log(msg)
        try:
            self.icon.notify(msg, "FlowLocal")
        except Exception:
            pass

    # -- state ------------------------------------------------------------
    def _set_state(self, state):
        self.state = state
        try:
            self.icon.icon = tray_icons.make_icon(state)
            self.icon.update_menu()
        except Exception:
            pass

    # -- hotkeys ----------------------------------------------------------
    def _matches(self, key_name, chord_key):
        return key_name in MODIFIER_ALIASES.get(chord_key, {chord_key})

    def _chord_down(self):
        return all(any(self._matches(p, ck) for p in self.pressed) for ck in self.ptt_chord)

    def _on_key_event(self, event):
        name = (event.name or "").lower()
        if event.event_type == "down":
            self.pressed.add(name)
            if self._chord_down():
                self._start_recording("ptt")
        else:
            self.pressed.discard(name)
            if (self.state == self.RECORDING and self.session_mode == "ptt"
                    and any(self._matches(name, ck) for ck in self.ptt_chord)):
                self._finish_recording()

    def _on_toggle(self):
        if self.state == self.RECORDING:
            if self.session_mode == "ptt":
                self.session_mode = "toggle"  # upgrade held PTT into a toggle session
                self.notify("Toggle dictation on — press the toggle hotkey to stop")
            else:
                self._finish_recording()
        else:
            self._start_recording("toggle")

    def _register_hotkeys(self):
        keyboard.hook(self._on_key_event)
        toggle = self.cfg["hotkey_toggle"]
        try:
            keyboard.add_hotkey(toggle, self._on_toggle)
        except ValueError:
            keyboard.add_hotkey(toggle.replace("windows", "left windows"), self._on_toggle)
        self.log("hotkeys registered")

    # -- record / transcribe flow ------------------------------------------
    def _start_recording(self, mode):
        with self.state_lock:
            if self.state != self.IDLE:
                return
            self.session_mode = mode
            recorder_mod.play_tone("start", self.cfg["tones_enabled"])
            try:
                self.recorder.start()
            except Exception as e:
                recorder_mod.play_tone("error", self.cfg["tones_enabled"])
                self.notify("No microphone found — plug one in or pick a device "
                            f"in the tray menu ({e})")
                self.session_mode = None
                return
            self._set_state(self.RECORDING)

    def _finish_recording(self):
        with self.state_lock:
            if self.state != self.RECORDING:
                return
            recorder_mod.play_tone("stop", self.cfg["tones_enabled"])
            audio = self.recorder.stop()
            self.session_mode = None
            self._set_state(self.TRANSCRIBING)
            self.jobs.put(("transcribe", audio))

    # -- worker thread ------------------------------------------------------
    def _worker(self):
        try:
            self.transcriber.load()
            self.log(f"model loaded: {self.transcriber.description()}")
        except Exception as e:
            self.notify(f"Model load failed: {e}. Check your internet connection "
                        "for the first-run download, then restart FlowLocal.")
        self.model_ready.set()
        self._set_state(self.IDLE)
        while True:
            job = self.jobs.get()
            if job is None:
                break
            kind, payload = job
            try:
                if kind == "reload":
                    self._set_state(self.LOADING)
                    self.transcriber.requested = payload  # "auto" re-runs the policy
                    self.transcriber.load()
                    self.notify(f"Model ready: {self.transcriber.description()}")
                elif kind == "transcribe":
                    self._handle_transcription(payload)
            except Exception as e:
                recorder_mod.play_tone("error", self.cfg["tones_enabled"])
                self.notify(f"Transcription failed: {e}")
            self._set_state(self.IDLE)

    def _handle_transcription(self, audio):
        if not recorder_mod.passes_gate(audio, self.cfg["silence_rms_threshold"],
                                        self.cfg["min_duration_s"]):
            self.log("recording gated (silence/too short) — nothing injected")
            return
        raw = self.transcriber.transcribe(audio)
        text = commands.process(raw, self.cfg["replacements"])
        if not text:
            self.log("empty transcript — nothing injected")
            return
        self.last_transcript = text
        injector.inject_text(text, paste_fallback=self.cfg["paste_fallback"])
        self.log(f"injected {len(text)} chars")

    # -- tray menu -----------------------------------------------------------
    def _status_text(self):
        return f"{self.state.capitalize()} — {self.transcriber.description()}"

    def _build_menu(self):
        def model_item(name):
            return Item(name, lambda: self._set_model(name),
                        checked=lambda item, n=name: self.cfg["model"] == n, radio=True)

        def device_items():
            for idx, dev_name in recorder_mod.list_input_devices():
                yield Item(dev_name, lambda _icon, _item, i=idx: self._set_device(i),
                           checked=lambda item, i=idx: self.cfg["input_device"] == i,
                           radio=True)

        return Menu(
            Item(lambda item: self._status_text(), None, enabled=False),
            Item("Copy last transcript", self._copy_last),
            Item("Model", Menu(*[model_item(m) for m in MODEL_CHOICES])),
            Item("Input device", Menu(device_items)),
            Item("Fallback paste mode", self._toggle_paste,
                 checked=lambda item: self.cfg["paste_fallback"]),
            Item("Open config", self._open_config),
            Menu.SEPARATOR,
            Item("Quit", self._quit),
        )

    def _copy_last(self):
        import pyperclip
        if self.last_transcript:
            pyperclip.copy(self.last_transcript)
            self.notify("Last transcript copied to clipboard")
        else:
            self.notify("No transcript yet — hold the hotkey and speak first")

    def _set_model(self, name):
        self.cfg["model"] = name
        config_mod.save(self.cfg)
        self.jobs.put(("reload", name))

    def _set_device(self, idx):
        self.cfg["input_device"] = idx
        self.recorder.device = idx
        config_mod.save(self.cfg)

    def _toggle_paste(self):
        self.cfg["paste_fallback"] = not self.cfg["paste_fallback"]
        config_mod.save(self.cfg)

    def _open_config(self):
        subprocess.Popen(["notepad.exe", config_mod.PATH])

    # -- lifecycle -------------------------------------------------------------
    def _quit(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.jobs.put(None)
        self.worker.join(timeout=5)
        self.icon.stop()

    def _on_tray_ready(self, icon):
        icon.visible = True
        self.log("tray ready")
        if self.smoke:
            def stop_after_load():
                self.model_ready.wait(timeout=240)
                self._quit()
            threading.Thread(target=stop_after_load, daemon=True).start()

    def run(self):
        self.worker.start()
        self._register_hotkeys()
        self.icon.run(setup=self._on_tray_ready)
        self.log("clean exit")


def main():
    parser = argparse.ArgumentParser(description="FlowLocal — local voice-to-text")
    parser.add_argument("--smoke", action="store_true",
                        help="start, load model, then exit (self-test)")
    args = parser.parse_args()

    mutex = acquire_single_instance()
    if mutex is None:
        print("FlowLocal: already running — exiting", flush=True)
        sys.exit(1)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    cfg = config_mod.load()
    if args.smoke:  # deterministic, small, CPU-only for the self-test
        cfg["model"] = "small.en"
    app = FlowLocalApp(cfg, smoke=args.smoke)
    if args.smoke:
        app.transcriber.force_device = "cpu"
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run smoke test to verify it passes**

Run: `venv/Scripts/python.exe -m pytest tests/test_smoke.py -v`
Expected: 1 passed (tray icon appears briefly, app exits on its own).

- [ ] **Step 5: Run full test suite**

Run: `venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_smoke.py
git commit -m "feat: tray app, hotkey state machine, single-instance lock"
```

---

### Task 9: README + live verification

**Files:**
- Create: `README.md`
- Modify: `requirements-gpu.txt` (pin exact versions if GPU deps were installed)

**Interfaces:**
- Consumes: everything; this task verifies the Definition of Done end-to-end.

- [ ] **Step 1: Live verification — normal (non-smoke) run**

Run `venv/Scripts/python.exe app.py` in the background. Verify from its stdout: hotkeys registered, tray ready, model loaded (note whether cuda or cpu fallback was used). If CUDA load failed for missing DLLs, run `venv/Scripts/python.exe -m pip install -r requirements-gpu.txt`, re-run, confirm cuda works or document CPU fallback behavior; pin exact versions in requirements-gpu.txt via `pip freeze | grep nvidia`.

- [ ] **Step 2: Live verification — single instance**

While the app is running, run `venv/Scripts/python.exe app.py` again. Expected: prints `FlowLocal: already running — exiting`, exit code 1. Then quit the first instance (or terminate it) and confirm clean exit.

- [ ] **Step 3: Write `README.md`** — sections: What it is (1 paragraph, privacy statement), Install (≤10 numbered steps: clone → venv → pip install → optional GPU extras → run), Hotkeys table (PTT hold Ctrl+Win; toggle Ctrl+Win+Space; note the Win+Ctrl+Space input-method conflict for multi-language users), Tray menu tour, Models table (tiny.en→distil-large-v3 with size/speed guidance, measured latency from Task 6), Spoken commands + how to edit `replacements` in config.json, config.json reference (every key from `config.DEFAULTS` with one-line description), Troubleshooting (no mic found; app blocks synthetic keys → enable Fallback paste mode; CUDA fallback message; hotkey conflicts; "already running"). State plainly: everything runs locally, nothing leaves the machine.

- [ ] **Step 4: Commit**

```bash
git add README.md requirements-gpu.txt
git commit -m "docs: README — install, hotkeys, models, troubleshooting"
```

---

### Task 10: GitHub repo + push + release commit

**Files:** none (git operations only)

- [ ] **Step 1: Full green suite one last time**

Run: `venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all pass. Fix anything red before proceeding (per verification-before-completion skill).

- [ ] **Step 2: Final release commit**

```bash
git add -A
git commit --allow-empty -m "flowlocal v0.1.0 — local voice-to-text, verified"
```
(`--allow-empty` in case Task 9 left nothing unstaged; the release marker commit is mandatory.)

- [ ] **Step 3: Create private GitHub repo and push**

```bash
gh repo create flowlocal --private --source=. --push
```
Expected: repo created under `xhan145/flowlocal`, `main` pushed. Verify with `git remote -v && git log --oneline -3`.

- [ ] **Step 4: Confirm Definition of Done** — app launches, records via hotkey, transcribes locally, injects into a focused window (test evidence from Task 7 integration test + Task 9 live run), all tests green, README ≤10 install steps, pushed to GitHub.
