import ast
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import textwrap
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get("ROAR_TEST_BASH", "bash")


class _BuildNode:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.__dict__.update(kwargs)


class _Analysis(_BuildNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pure = []
        self.scripts = ["app.py"]
        self.binaries = list(kwargs["binaries"])
        self.datas = list(kwargs["datas"])


def _execute_linux_spec(monkeypatch):
    collected = []

    def collect_all(package):
        collected.append(package)
        return ([(f"{package}/data", package)],
                [(f"{package}/binary", package)],
                [f"{package}.auto_hidden"])

    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.collect_all = collect_all
    utils = types.ModuleType("PyInstaller.utils")
    pyinstaller = types.ModuleType("PyInstaller")
    monkeypatch.setitem(sys.modules, "PyInstaller", pyinstaller)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils", utils)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)
    namespace = runpy.run_path(
        str(ROOT / "roar-linux.spec"),
        init_globals={
            "SPECPATH": str(ROOT),
            "Analysis": _Analysis,
            "PYZ": _BuildNode,
            "EXE": _BuildNode,
            "COLLECT": _BuildNode,
        },
    )
    return namespace, collected


def test_linux_spec_executes_with_linux_only_collection(monkeypatch):
    namespace, collected = _execute_linux_spec(monkeypatch)

    assert collected == [
        "faster_whisper", "ctranslate2", "av", "onnxruntime", "webview"
    ]
    analysis = namespace["a"]
    assert analysis.args[0] == ["app.py"]
    assert {"webview.platforms.gtk", "gi"} <= set(analysis.hiddenimports)
    assert namespace["exe"].name == "ROAR-linux"
    assert namespace["coll"].name == "ROAR-linux"
    assert not hasattr(namespace["exe"], "icon")
    assert not hasattr(namespace["exe"], "version")

    excluded = {name.casefold() for name in analysis.excludes}
    assert {
        "uiautomation",
        "comtypes",
        "pyaudiowpatch",
        "backends.onnx_directml_spike",
        "whispercpp_assets",
        "backends.whispercpp_vulkan",
    } <= excluded


def test_linux_spec_packages_required_runtime_data(monkeypatch):
    namespace, _ = _execute_linux_spec(monkeypatch)
    datas = set(namespace["a"].datas)

    assert {
        ("settings.html", "."),
        ("transcript.html", "."),
        ("fob.png", "."),
        ("assets", "assets"),
        ("licenses", "licenses"),
        ("THIRD_PARTY_NOTICES.md", "."),
        ("tts/worker.py", "tts"),
        ("tts/assets/kokoro-model-manifest.json", "tts/assets"),
    } <= datas


def test_linux_spec_does_not_import_windows_version_writer():
    tree = ast.parse((ROOT / "roar-linux.spec").read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "scripts.version_info" not in imported


def test_linux_build_requirements_are_pinned_and_nothing_else():
    lines = (ROOT / "requirements-linux-build.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    requirements = [
        line.strip() for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert requirements == ["pyinstaller==6.21.0"]


def _write_executable(path, body):
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8", newline="\n")
    path.chmod(0o755)


@pytest.fixture
def packaging_fixture(tmp_path):
    for relative in (
        "linux/build_appimage.sh",
        "linux/verify_appimage.sh",
        "linux/roar.desktop",
        "assets/roar-logo-purple.png",
        "paths.py",
        "roar-linux.spec",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    log = tmp_path / "tool.log"

    _write_executable(fake_bin / "uname", r'''
        #!/usr/bin/env bash
        if [[ "$1" == "-s" ]]; then printf '%s\n' "${FAKE_UNAME_S:-Linux}"; exit; fi
        if [[ "$1" == "-m" ]]; then printf '%s\n' "${FAKE_UNAME_M:-x86_64}"; exit; fi
        exit 2
    ''')
    _write_executable(fake_bin / "python shim", r'''
        #!/usr/bin/env bash
        printf 'python:%s\n' "$*" >> "$FAKE_LOG"
        if [[ "$1" == "-c" && "$2" == "from paths import APP_VERSION; print(APP_VERSION)" ]]; then
          printf '0.35.2\n'
          exit 0
        fi
        if [[ "$1" == "-c" && "$2" == "import PyInstaller; print(PyInstaller.__version__)" ]]; then
          printf '%s\n' "${FAKE_PYINSTALLER_VERSION:-6.21.0}"
          exit 0
        fi
        if [[ "$*" == "-m PyInstaller --noconfirm --clean --workpath build/linux/pyinstaller --distpath build/linux/frozen roar-linux.spec" ]]; then
          mkdir -p build/linux/frozen/ROAR-linux
          cat > build/linux/frozen/ROAR-linux/ROAR-linux <<'EOF'
        #!/usr/bin/env bash
        [[ "$1" == "--smoke" ]] || exit 89
        printf 'ROAR: hotkeys registered\n'
        printf 'ROAR: clean exit\n'
        EOF
          chmod +x build/linux/frozen/ROAR-linux/ROAR-linux
          exit 0
        fi
        printf 'unexpected python invocation\n' >&2
        exit 91
    ''')
    _write_executable(fake_bin / "appimagetool shim", r'''
        #!/usr/bin/env bash
        printf 'appimagetool:ARCH=%s:%s\n' "${ARCH-}" "$*" >> "$FAKE_LOG"
        [[ "${ARCH-}" == "x86_64" && "$#" == 2 ]] || exit 92
        cat > "$2" <<'EOF'
        #!/usr/bin/env bash
        [[ "$1" == "--smoke" ]] || exit 90
        printf 'appimage-env:APPIMAGE_EXTRACT_AND_RUN=%s\n' \
          "${APPIMAGE_EXTRACT_AND_RUN-}" >> "$FAKE_LOG"
        [[ "${APPIMAGE_EXTRACT_AND_RUN-}" == "1" ]] || exit 88
        printf 'ROAR: hotkeys registered\n'
        printf 'ROAR: clean exit\n'
        exit "${FAKE_SMOKE_EXIT:-0}"
        EOF
        chmod +x "$2"
    ''')
    _write_executable(fake_bin / "sha256sum", r'''
        #!/usr/bin/env bash
        printf 'sha256sum:%s\n' "$*" >> "$FAKE_LOG"
        if [[ "$1" == "--check" ]]; then
          if [[ "${FAKE_CHECKSUM_FAIL:-0}" == "1" ]]; then
            printf 'forced checksum mismatch\n' >&2
            exit 99
          fi
          read -r digest filename < "$2"
          [[ "$digest" == aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa ]] || exit 93
          [[ -f "$filename" ]] || exit 94
          printf '%s: OK\n' "$filename"
          exit 0
        fi
        [[ "$#" == 1 && -f "$1" ]] || exit 95
        printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  %s\n' "$(basename -- "$1")"
    ''')
    _write_executable(fake_bin / "xvfb-run", r'''
        #!/usr/bin/env bash
        printf 'xvfb:XDG_CONFIG_HOME=%s:XDG_DATA_HOME=%s:XDG_RUNTIME_DIR=%s:%s\n' \
          "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_RUNTIME_DIR" "$*" >> "$FAKE_LOG"
        printf '%s\n%s\n%s\n' "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_RUNTIME_DIR" >> "$FAKE_XDG_LOG"
        [[ -d "$XDG_CONFIG_HOME" && -d "$XDG_DATA_HOME" && -d "$XDG_RUNTIME_DIR" ]] || exit 96
        [[ "$1" == "-a" ]] || exit 97
        shift
        exec "$@"
    ''')
    for command in ("pip", "pyinstaller", "curl", "wget"):
        _write_executable(fake_bin / command, rf'''
            #!/usr/bin/env bash
            printf '{command}:%s\n' "$*" >> "$FAKE_LOG"
            exit 98
        ''')

    subprocess.run(
        [BASH, "-c", "chmod +x fake-bin/* linux/*.sh"],
        cwd=tmp_path,
        check=True,
    )
    env = os.environ.copy()
    env.update({
        "FAKE_LOG": str(log),
        "FAKE_XDG_LOG": str(tmp_path / "xdg.log"),
    })
    return tmp_path, env


def _run_bash(root, env, command):
    return subprocess.run(
        [
            BASH,
            "-c",
            (
                'export PATH="$PWD/fake-bin:$PATH"; '
                'export FAKE_LOG="$PWD/tool.log"; '
                'export FAKE_XDG_LOG="$PWD/xdg.log"; '
                f"{command}"
            ),
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )


def test_build_recipe_produces_verified_canonical_artifacts(packaging_fixture):
    root, env = packaging_fixture

    (root / "build/linux/stale").mkdir(parents=True)
    (root / "dist/ROAR").mkdir(parents=True)
    (root / "dist/ROAR/windows.txt").write_text("keep", encoding="utf-8")
    preserved = [
        root / "dist/ROAR-Setup-0.35.1.exe",
        root / "dist/ROAR-0.35.1.msi",
        root / "dist/ROAR-0.35.1.cab",
    ]
    for path in preserved:
        path.write_text("keep", encoding="utf-8")
    stale_linux = root / "dist/ROAR-Linux-0.35.1-x86_64.AppImage"
    stale_linux.write_text("old", encoding="utf-8")

    result = _run_bash(
        root,
        env,
        'ROAR_LINUX_PYTHON="$PWD/fake-bin/python shim" '
        'APPIMAGETOOL="$PWD/fake-bin/appimagetool shim" '
        "bash linux/build_appimage.sh",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    artifact = root / "dist/ROAR-Linux-0.35.2-x86_64.AppImage"
    sidecar = root / f"dist/{artifact.name}.sha256"
    assert artifact.is_file()
    assert sidecar.read_text(encoding="utf-8") == (
        "a" * 64 + f"  {artifact.name}\n"
    )
    assert not (root / f"dist/{artifact.name}.building").exists()
    assert not stale_linux.exists()
    assert not (root / "build/linux/stale").exists()
    assert (root / "dist/ROAR/windows.txt").read_text(encoding="utf-8") == "keep"
    assert all(path.read_text(encoding="utf-8") == "keep" for path in preserved)

    appdir = root / "build/linux/ROAR.AppDir"
    assert (appdir / "usr/bin/ROAR/ROAR-linux").is_file()
    assert (appdir / "ROAR.desktop").read_bytes() == (root / "linux/roar.desktop").read_bytes()
    logo = (root / "assets/roar-logo-purple.png").read_bytes()
    assert (appdir / "roar.png").read_bytes() == logo
    assert (appdir / ".DirIcon").read_bytes() == logo
    assert (appdir / "AppRun").read_text(encoding="utf-8") == textwrap.dedent("""\
        #!/bin/sh
        HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
        export ROAR_APPIMAGE=1
        exec "$HERE/usr/bin/ROAR/ROAR-linux" "$@"
        """)

    invocations = (root / "tool.log").read_text(encoding="utf-8")
    assert "python:-c from paths import APP_VERSION; print(APP_VERSION)" in invocations
    assert "python:-c import PyInstaller; print(PyInstaller.__version__)" in invocations
    assert (
        "python:-m PyInstaller --noconfirm --clean --workpath "
        "build/linux/pyinstaller --distpath build/linux/frozen roar-linux.spec"
    ) in invocations
    assert "appimagetool:ARCH=x86_64:" in invocations
    assert f"ROAR.AppDir dist/{artifact.name}.building" in invocations
    assert "pip:" not in invocations
    assert "pyinstaller:" not in invocations
    assert "curl:" not in invocations
    assert "wget:" not in invocations
    assert invocations.count("xvfb:") == 2
    assert invocations.count("--smoke") == 2
    assert invocations.count("sha256sum:--check") == 1
    assert "appimage-env:APPIMAGE_EXTRACT_AND_RUN=1" in invocations

    xdg_paths = (root / "xdg.log").read_text(encoding="utf-8").splitlines()
    assert len(xdg_paths) == 6
    assert all(not Path(path).exists() for path in xdg_paths)


@pytest.mark.parametrize(
    ("host_env", "expected"),
    [
        ({"FAKE_UNAME_S": "Darwin"}, "Linux"),
        ({"FAKE_UNAME_M": "aarch64"}, "x86_64"),
    ],
)
def test_build_recipe_rejects_unsupported_hosts(packaging_fixture, host_env, expected):
    root, env = packaging_fixture
    host_assignment = " ".join(f"{key}={value}" for key, value in host_env.items())
    result = _run_bash(
        root,
        env,
        f"{host_assignment} "
        'ROAR_LINUX_PYTHON="$PWD/fake-bin/python shim" '
        'APPIMAGETOOL="$PWD/fake-bin/appimagetool shim" '
        "bash linux/build_appimage.sh",
    )

    assert result.returncode != 0
    assert expected in result.stderr


def test_build_recipe_requires_supplied_appimagetool(packaging_fixture):
    root, env = packaging_fixture
    env.pop("APPIMAGETOOL", None)

    result = _run_bash(
        root,
        env,
        'unset APPIMAGETOOL; ROAR_LINUX_PYTHON="$PWD/fake-bin/python shim" '
        "bash linux/build_appimage.sh",
    )

    assert result.returncode != 0
    assert "APPIMAGETOOL" in result.stderr
    log = (root / "tool.log").read_text(encoding="utf-8") if (root / "tool.log").exists() else ""
    assert "curl:" not in log
    assert "wget:" not in log


def test_build_recipe_rejects_mismatched_pyinstaller_before_cleanup(packaging_fixture):
    root, env = packaging_fixture
    stale_build = root / "build/linux/stale.txt"
    stale_build.parent.mkdir(parents=True)
    stale_build.write_text("keep", encoding="utf-8")
    stale_artifact = root / "dist/ROAR-Linux-0.35.1-x86_64.AppImage"
    stale_artifact.parent.mkdir()
    stale_artifact.write_text("keep", encoding="utf-8")

    result = _run_bash(
        root,
        env,
        'FAKE_PYINSTALLER_VERSION=6.20.0 '
        'ROAR_LINUX_PYTHON="$PWD/fake-bin/python shim" '
        'APPIMAGETOOL="$PWD/fake-bin/appimagetool shim" '
        "bash linux/build_appimage.sh",
    )

    assert result.returncode != 0
    assert "PyInstaller 6.21.0" in result.stderr
    assert "6.20.0" in result.stderr
    assert stale_build.read_text(encoding="utf-8") == "keep"
    assert stale_artifact.read_text(encoding="utf-8") == "keep"


def test_verifier_rejects_checksum_failure_before_smoke(packaging_fixture):
    root, env = packaging_fixture
    artifact = root / "dist/ROAR-Linux-0.35.2-x86_64.AppImage"
    artifact.parent.mkdir()
    _write_executable(
        artifact,
        "#!/usr/bin/env bash\nprintf 'ROAR: hotkeys registered\\n'\n",
    )
    artifact.with_name(artifact.name + ".sha256").write_text(
        "a" * 64 + f"  {artifact.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    subprocess.run(
        [BASH, "-c", f'chmod +x "{artifact.name}"'],
        cwd=artifact.parent,
        check=True,
    )

    result = _run_bash(
        root,
        env,
        f'FAKE_CHECKSUM_FAIL=1 bash linux/verify_appimage.sh "dist/{artifact.name}"',
    )

    assert result.returncode == 99, result.stdout + result.stderr
    assert "forced checksum mismatch" in result.stderr
    invocations = (root / "tool.log").read_text(encoding="utf-8")
    assert "sha256sum:--check" in invocations
    assert "xvfb:" not in invocations


def test_build_recipe_rejects_nonzero_packaged_smoke(packaging_fixture):
    root, env = packaging_fixture

    result = _run_bash(
        root,
        env,
        'FAKE_SMOKE_EXIT=23 '
        'ROAR_LINUX_PYTHON="$PWD/fake-bin/python shim" '
        'APPIMAGETOOL="$PWD/fake-bin/appimagetool shim" '
        "bash linux/build_appimage.sh",
    )

    assert result.returncode == 23
    assert "status 23" in result.stderr
    assert not (root / "dist/ROAR-Linux-0.35.2-x86_64.AppImage").exists()
    assert not (root / "dist/ROAR-Linux-0.35.2-x86_64.AppImage.sha256").exists()


@pytest.mark.parametrize(
    "output",
    [
        "ROAR: already running — exiting\nROAR: hotkeys registered\n",
        "ROAR: tray ready\n",
        "ROAR: hotkeys registered\n",
    ],
)
def test_verifier_rejects_invalid_smoke_output(packaging_fixture, output):
    root, env = packaging_fixture
    artifact = root / "dist/ROAR-Linux-0.35.2-x86_64.AppImage"
    artifact.parent.mkdir()
    _write_executable(
        artifact,
        "#!/usr/bin/env bash\ncat <<'EOF'\n" + output + "EOF\n",
    )
    sidecar = artifact.with_name(artifact.name + ".sha256")
    sidecar.write_text(
        "a" * 64 + f"  {artifact.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    subprocess.run([BASH, "-c", f'chmod +x "{artifact.name}"'], cwd=artifact.parent, check=True)

    result = _run_bash(
        root,
        env,
        f'bash linux/verify_appimage.sh "dist/{artifact.name}"',
    )

    assert result.returncode != 0
