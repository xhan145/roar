import json
from pathlib import Path

import copy

import pytest

from scripts.generate_site_release_manifest import (
    ManifestError,
    build_manifest,
    validate_manifest,
)


FIXTURES = Path(__file__).parent / "fixtures" / "releases"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_channels_are_selected_independently():
    """Fails if stable Windows and preview Linux selection become coupled."""
    manifest = build_manifest(
        load_fixture("windows-and-linux.json"),
        "xhan145/roar",
        "2026-08-06T12:00:00Z",
    )

    assert manifest["platforms"]["windows"]["channel"] == "stable"
    assert manifest["platforms"]["windows"]["version"] == "0.35.2"
    assert manifest["platforms"]["linux"]["channel"] == "preview"
    assert manifest["platforms"]["linux"]["package_type"] == "AppImage"


def test_missing_linux_release_fails_closed():
    """Fails if a missing Linux package is represented as an available download."""
    linux = build_manifest(
        load_fixture("current.json"), "xhan145/roar", "2026-08-06T12:00:00Z"
    )["platforms"]["linux"]

    assert linux == {"available": False, "channel": "preview"}


def test_invalid_release_list_root_is_rejected():
    """Fails if an API error object is treated as an empty release list."""
    with pytest.raises(ManifestError, match="release list"):
        build_manifest(load_fixture("invalid.json"), "xhan145/roar", "2026-08-06T12:00:00Z")


def test_draft_release_is_ignored_even_when_newer():
    """Fails if an unpublished draft can replace the stable Windows download."""
    windows = build_manifest(
        load_fixture("windows-and-linux.json"),
        "xhan145/roar",
        "2026-08-06T12:00:00Z",
    )["platforms"]["windows"]

    assert windows["version"] == "0.35.2"
    assert windows["asset_name"] == "ROAR-Setup-0.35.2.exe"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/xhan145/roar/releases/download/v0.35.2/ROAR-Setup-0.35.2.exe",
        "https://example.test/xhan145/roar/releases/download/v0.35.2/ROAR-Setup-0.35.2.exe",
    ],
)
def test_untrusted_asset_url_is_rejected(url):
    """Fails if an asset outside GitHub HTTPS can enter release metadata."""
    releases = load_fixture("current.json")
    releases[0]["assets"][0]["browser_download_url"] = url

    with pytest.raises(ManifestError, match="browser_download_url"):
        build_manifest(releases, "xhan145/roar", "2026-08-06T12:00:00Z")


@pytest.mark.parametrize(
    "field,value",
    [
        ("size", 0),
        ("digest", None),
        ("digest", "sha256:ABCDEF"),
    ],
)
def test_invalid_release_asset_metadata_is_rejected(field, value):
    """Fails if incomplete or malformed GitHub asset metadata becomes downloadable."""
    releases = load_fixture("current.json")
    releases[0]["assets"][0][field] = value

    with pytest.raises(ManifestError):
        build_manifest(releases, "xhan145/roar", "2026-08-06T12:00:00Z")


def test_asset_version_must_match_release_tag():
    """Fails if a mismatched filename version is attributed to the release tag."""
    releases = load_fixture("current.json")
    releases[0]["assets"][0]["name"] = "ROAR-Setup-0.35.1.exe"

    with pytest.raises(ManifestError, match="does not match release tag"):
        build_manifest(releases, "xhan145/roar", "2026-08-06T12:00:00Z")


def test_ambiguous_matching_assets_are_rejected():
    """Fails if selection silently chooses between two matching installer assets."""
    releases = load_fixture("current.json")
    releases[0]["assets"].append(copy.deepcopy(releases[0]["assets"][0]))

    with pytest.raises(ManifestError, match="multiple matching Windows assets"):
        build_manifest(releases, "xhan145/roar", "2026-08-06T12:00:00Z")


def test_generated_at_is_deterministic():
    """Fails if the generator substitutes the wall clock for the supplied timestamp."""
    manifest = build_manifest(
        load_fixture("current.json"), "xhan145/roar", "2026-08-06T12:00:00Z"
    )

    assert manifest["generated_at"] == "2026-08-06T12:00:00Z"


def test_sha256_is_normalized_without_digest_prefix():
    """Fails if the GitHub digest prefix leaks into the public SHA-256 field."""
    windows = build_manifest(
        load_fixture("current.json"), "xhan145/roar", "2026-08-06T12:00:00Z"
    )["platforms"]["windows"]

    assert windows["sha256"] == "ed7180f00bd4a3c923c97eeb8b84c43f263b0fced9aa38d903489eed4ad768e3"


def test_current_windows_metadata_is_preserved_exactly():
    """Fails if verified release metadata is altered during manifest generation."""
    windows = build_manifest(
        load_fixture("current.json"), "xhan145/roar", "2026-08-06T12:00:00Z"
    )["platforms"]["windows"]

    assert windows == {
        "available": True,
        "channel": "stable",
        "version": "0.35.2",
        "release_name": "ROAR v0.35.2 — installer honesty, continued",
        "published_at": "2026-08-03T19:20:31Z",
        "architecture": "x86_64",
        "package_type": "exe",
        "asset_name": "ROAR-Setup-0.35.2.exe",
        "asset_url": "https://github.com/xhan145/roar/releases/download/v0.35.2/ROAR-Setup-0.35.2.exe",
        "asset_size_bytes": 908794228,
        "sha256": "ed7180f00bd4a3c923c97eeb8b84c43f263b0fced9aa38d903489eed4ad768e3",
        "release_notes_url": "https://github.com/xhan145/roar/releases/tag/v0.35.2",
    }


def valid_windows_record():
    return {
        "available": True,
        "channel": "stable",
        "version": "0.35.2",
        "release_name": "ROAR v0.35.2",
        "published_at": "2026-08-03T19:20:31Z",
        "architecture": "x86_64",
        "package_type": "exe",
        "asset_name": "ROAR-Setup-0.35.2.exe",
        "asset_url": "https://github.com/xhan145/roar/releases/download/v0.35.2/ROAR-Setup-0.35.2.exe",
        "asset_size_bytes": 1,
        "sha256": "a" * 64,
        "release_notes_url": "https://github.com/xhan145/roar/releases/tag/v0.35.2",
    }


def base_manifest(windows):
    return {
        "schema_version": 1,
        "repository": "xhan145/roar",
        "generated_at": "2026-08-06T12:00:00Z",
        "platforms": {
            "windows": windows,
            "linux": {"available": False, "channel": "preview"},
        },
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("asset_size_bytes", 0),
        ("sha256", "not-a-digest"),
        ("asset_url", "http://example.test/file.exe"),
    ],
)
def test_available_record_rejects_invalid_asset_metadata(field, value):
    """Fails if a manifest can claim an unsafe available download."""
    record = valid_windows_record()
    record[field] = value

    with pytest.raises(ManifestError):
        validate_manifest(base_manifest(windows=record))


def test_generated_manifest_passes_runtime_validation():
    """Fails if the generator emits a manifest its own consumer validator rejects."""
    manifest = build_manifest(
        load_fixture("windows-and-linux.json"),
        "xhan145/roar",
        "2026-08-06T12:00:00Z",
    )

    assert validate_manifest(manifest) is None
