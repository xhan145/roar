"""Build a verified, static download manifest from GitHub release metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


WINDOWS_ASSET = re.compile(r"^ROAR-Setup-(\d+\.\d+\.\d+)\.exe$")
LINUX_ASSET = re.compile(r"^ROAR-Linux-(\d+\.\d+\.\d+)-x86_64\.AppImage$")
DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
TRUSTED_REPOSITORY = "xhan145/roar"


class ManifestError(ValueError):
    """Raised when release metadata cannot safely become a public download link."""


def build_manifest(releases: list[dict], repository: str, generated_at: str) -> dict:
    """Select independent Windows Stable and Linux Preview download records."""
    if not isinstance(releases, list):
        raise ManifestError("release list must be a JSON array")
    if repository != TRUSTED_REPOSITORY:
        raise ManifestError(f"repository must be {TRUSTED_REPOSITORY}")
    _require_datetime(generated_at, "generated_at")

    manifest = {
        "schema_version": 1,
        "repository": repository,
        "generated_at": generated_at,
        "platforms": {
            "windows": _select_platform(releases, "windows"),
            "linux": _select_platform(releases, "linux"),
        },
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict) -> None:
    """Validate the schema's security-critical constraints without dependencies."""
    if not isinstance(manifest, dict):
        raise ManifestError("manifest must be an object")
    _require_exact_keys(
        manifest,
        {"schema_version", "repository", "generated_at", "platforms"},
        "manifest",
    )
    if manifest["schema_version"] != 1:
        raise ManifestError("schema_version must be 1")
    if manifest["repository"] != TRUSTED_REPOSITORY:
        raise ManifestError(f"repository must be {TRUSTED_REPOSITORY}")
    _require_datetime(manifest["generated_at"], "generated_at")

    platforms = manifest["platforms"]
    if not isinstance(platforms, dict):
        raise ManifestError("platforms must be an object")
    _require_exact_keys(platforms, {"windows", "linux"}, "platforms")
    _validate_platform_record(platforms["windows"], "windows")
    _validate_platform_record(platforms["linux"], "linux")


def _select_platform(releases: list[dict], platform: str) -> dict:
    channel = "stable" if platform == "windows" else "preview"
    asset_pattern = WINDOWS_ASSET if platform == "windows" else LINUX_ASSET
    eligible = [
        release
        for release in releases
        if isinstance(release, dict)
        and release.get("draft") is False
        and (
            release.get("prerelease") is False
            or (platform == "linux" and release.get("prerelease") is True)
        )
        and isinstance(release.get("published_at"), str)
    ]
    eligible.sort(key=lambda release: release["published_at"], reverse=True)

    for release in eligible:
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        matches = [
            asset
            for asset in assets
            if isinstance(asset, dict)
            and isinstance(asset.get("name"), str)
            and asset_pattern.fullmatch(asset["name"])
        ]
        if not matches:
            continue
        if len(matches) > 1:
            raise ManifestError(f"multiple matching {platform.title()} assets")

        asset = matches[0]
        version = asset_pattern.fullmatch(asset["name"]).group(1)
        if release.get("tag_name") != f"v{version}":
            raise ManifestError(f"asset version {version} does not match release tag")
        return _available_record(release, asset, platform, channel, version)

    return {"available": False, "channel": channel}


def _available_record(
    release: dict, asset: dict, platform: str, channel: str, version: str
) -> dict:
    release_name = release.get("name")
    published_at = release.get("published_at")
    release_notes_url = release.get("html_url")
    if not isinstance(release_name, str) or not release_name:
        raise ManifestError("release name must be a non-empty string")
    _require_datetime(published_at, "published_at")
    _require_release_notes_url(release_notes_url)

    asset_name = asset["name"]
    asset_url = asset.get("browser_download_url")
    asset_size_bytes = asset.get("size")
    digest = asset.get("digest")
    if not _is_trusted_download_url(asset_url, release["tag_name"], asset_name):
        raise ManifestError("browser_download_url must be a trusted GitHub HTTPS release URL")
    if not isinstance(asset_size_bytes, int) or isinstance(asset_size_bytes, bool) or asset_size_bytes < 1:
        raise ManifestError("asset size must be a positive integer")
    if not isinstance(digest, str) or not (digest_match := DIGEST.fullmatch(digest)):
        raise ManifestError("asset digest must be sha256:<64 lowercase hex>")

    record = {
        "available": True,
        "channel": channel,
        "version": version,
        "release_name": release_name,
        "published_at": published_at,
        "architecture": "x86_64",
        "package_type": "exe" if platform == "windows" else "AppImage",
        "asset_name": asset_name,
        "asset_url": asset_url,
        "asset_size_bytes": asset_size_bytes,
        "sha256": digest_match.group(1),
        "release_notes_url": release_notes_url,
    }
    if platform == "linux":
        record["tested_environments"] = ["Ubuntu 24.04 (x86_64, X11)"]
        record["known_limitations_url"] = "/linux/"
    return record


def _validate_platform_record(record: Any, platform: str) -> None:
    channel = "stable" if platform == "windows" else "preview"
    if not isinstance(record, dict):
        raise ManifestError(f"{platform} record must be an object")
    if record.get("available") is False:
        _require_exact_keys(record, {"available", "channel"}, f"{platform} unavailable record")
        if record["channel"] != channel:
            raise ManifestError(f"{platform} channel must be {channel}")
        return
    if record.get("available") is not True:
        raise ManifestError(f"{platform} availability must be a boolean")

    expected = {
        "available",
        "channel",
        "version",
        "release_name",
        "published_at",
        "architecture",
        "package_type",
        "asset_name",
        "asset_url",
        "asset_size_bytes",
        "sha256",
        "release_notes_url",
    }
    if platform == "linux":
        expected |= {"tested_environments", "known_limitations_url"}
    _require_exact_keys(record, expected, f"{platform} available record")

    if record["channel"] != channel:
        raise ManifestError(f"{platform} channel must be {channel}")
    if not isinstance(record["version"], str) or not re.fullmatch(r"\d+\.\d+\.\d+", record["version"]):
        raise ManifestError("version must be a semantic version")
    if not isinstance(record["release_name"], str) or not record["release_name"]:
        raise ManifestError("release_name must be a non-empty string")
    _require_datetime(record["published_at"], "published_at")
    if record["architecture"] != "x86_64":
        raise ManifestError("architecture must be x86_64")
    expected_package = "exe" if platform == "windows" else "AppImage"
    if record["package_type"] != expected_package:
        raise ManifestError(f"{platform} package_type must be {expected_package}")

    pattern = WINDOWS_ASSET if platform == "windows" else LINUX_ASSET
    name_match = pattern.fullmatch(record["asset_name"]) if isinstance(record["asset_name"], str) else None
    if not name_match or name_match.group(1) != record["version"]:
        raise ManifestError("asset_name must match the platform package and version")
    if not _is_trusted_download_url(
        record["asset_url"], f"v{record['version']}", record["asset_name"]
    ):
        raise ManifestError("asset_url must be a trusted GitHub HTTPS release URL")
    if not isinstance(record["asset_size_bytes"], int) or isinstance(record["asset_size_bytes"], bool) or record["asset_size_bytes"] < 1:
        raise ManifestError("asset_size_bytes must be a positive integer")
    if not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
        raise ManifestError("sha256 must be 64 lowercase hexadecimal characters")
    _require_release_notes_url(record["release_notes_url"])

    if platform == "linux":
        environments = record["tested_environments"]
        if not isinstance(environments, list) or not environments or not all(
            isinstance(environment, str) and environment for environment in environments
        ):
            raise ManifestError("tested_environments must be a non-empty string list")
        if record["known_limitations_url"] != "/linux/":
            raise ManifestError("known_limitations_url must be /linux/")


def _is_trusted_download_url(value: Any, release_tag: str, asset_name: str) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    expected_path = (
        f"/{TRUSTED_REPOSITORY}/releases/download/"
        f"{quote(release_tag, safe='')}/{quote(asset_name, safe='')}"
    )
    return (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and parsed.path == expected_path
        and not parsed.params
    )


def _require_release_notes_url(value: Any) -> None:
    if not isinstance(value, str):
        raise ManifestError("release_notes_url must be an HTTPS GitHub release URL")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or not parsed.path.startswith(f"/{TRUSTED_REPOSITORY}/releases/tag/")
    ):
        raise ManifestError("release_notes_url must be an HTTPS GitHub release URL")


def _require_datetime(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise ManifestError(f"{field} must be an ISO 8601 date-time string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestError(f"{field} must be an ISO 8601 date-time string") from error
    if parsed.tzinfo is None:
        raise ManifestError(f"{field} must include a timezone")


def _require_exact_keys(value: dict, expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ManifestError(
            f"{context} keys must be exactly {sorted(expected)}; got {sorted(actual)}"
        )


def _fetch_releases(repository: str) -> list[dict]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/repos/{repository}/releases", headers=headers)
    with urlopen(request) as response:  # noqa: S310 - repository is validated by build_manifest
        return json.loads(response.read().decode("utf-8"))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    generated_at = args.generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        releases = (
            json.loads(args.input.read_text(encoding="utf-8"))
            if args.input
            else _fetch_releases(args.repository)
        )
        manifest = build_manifest(releases, args.repository, generated_at)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, ManifestError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
