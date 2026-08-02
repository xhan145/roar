"""The exe must carry a Windows version resource, and the installer must not
fail silently.

Both invariants come from a real incident (2026-08-02): the 0.34.0 -> 0.35.0
in-place upgrade did nothing three times in a row while every layer reported
success. Root causes, one test each below:
  * ROAR.exe had no version resource, so MSI kept the old unversioned file;
  * the SFX wrapper reported exit 0 even when msiexec failed, hiding it;
  * build_msi.sh purged the previous MSI, which MSI needs to remove the old
    product during a major upgrade (Error 1714 / System Error 1612).
"""
import pathlib

import pytest

from scripts import version_info as vinfo

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_version_tuple_pads_to_four_parts():
    assert vinfo.version_tuple("0.35.0") == (0, 35, 0, 0)
    assert vinfo.version_tuple("1.2.3.4") == (1, 2, 3, 4)
    assert vinfo.version_tuple("7") == (7, 0, 0, 0)


def test_version_tuple_tolerates_junk_rather_than_killing_a_release_build():
    assert vinfo.version_tuple("0.35.0rc1") == (0, 35, 0, 0)
    assert vinfo.version_tuple("") == (0, 0, 0, 0)
    assert vinfo.version_tuple("x.y") == (0, 0, 0, 0)


def test_text_carries_the_version_in_both_the_binary_and_string_fields():
    text = vinfo.version_info_text("0.35.0")
    assert "filevers=(0, 35, 0, 0)" in text
    assert "prodvers=(0, 35, 0, 0)" in text
    assert '"FileVersion", "0.35.0.0"' in text
    assert '"ProductVersion", "0.35.0"' in text
    assert '"OriginalFilename", "ROAR.exe"' in text


def test_generated_file_parses_as_a_real_pyinstaller_version_resource():
    """Eval it the way PyInstaller does — a typo here would only surface as a
    failed release build."""
    vi = pytest.importorskip("PyInstaller.utils.win32.versioninfo")
    names = ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable",
             "StringStruct", "VarFileInfo", "VarStruct")
    ns = {n: getattr(vi, n) for n in names}
    info = eval(vinfo.version_info_text("0.35.0"), ns)   # noqa: S307
    assert isinstance(info, vi.VSVersionInfo)
    rendered = str(info)          # PyInstaller renders it back out to stamp it
    assert "0.35.0.0" in rendered
    assert "ROAR.exe" in rendered


def test_write_version_file_creates_the_file(tmp_path):
    out = tmp_path / "nested" / "version_info.txt"
    path = vinfo.write_version_file("0.35.0", out)
    assert pathlib.Path(path).read_text(encoding="utf-8").startswith("#")


def test_spec_gives_the_exe_a_version_resource():
    spec = (ROOT / "roar.spec").read_text(encoding="utf-8")
    assert "write_version_file" in spec, "roar.spec must generate the resource"
    assert "version=" in spec, "EXE() must receive version=<path>"


def test_installer_logs_and_surfaces_a_failed_msiexec():
    """The 7zSD stub swallows the child's exit code, so a failed install must
    be made visible to the human running it."""
    sh = (ROOT / "scripts" / "build_setup.sh").read_text(encoding="utf-8")
    assert "/l*v" in sh, "msiexec must always write a verbose log"
    assert "failed" in sh.lower(), "a failure must print a message, not exit quietly"
    assert "%RC%" in sh, "the msiexec exit code must be captured and reported"


def test_build_msi_keeps_the_previous_msi_for_upgrades():
    """Purging the old MSI breaks the next in-place upgrade: Windows needs it
    to remove the installed product."""
    sh = (ROOT / "scripts" / "build_msi.sh").read_text(encoding="utf-8")
    assert 'find dist -maxdepth 1 \\( -name "ROAR-*.msi"' not in sh, (
        "the blanket purge of superseded MSIs is what broke the 0.34->0.35 upgrade")
    assert "head -n -2" in sh, "keep the current AND previous MSI"
