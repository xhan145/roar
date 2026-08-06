import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "roar_versions",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "roar_versions.py"))
rv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rv)


def test_find_version():
    assert rv.find_version('APP_VERSION = "0.16.0"',
                           r'APP_VERSION\s*=\s*"([0-9.]+)"') == "0.16.0"
    assert rv.find_version('versionName = "0.1.0"',
                           r'versionName\s*=\s*"([0-9.]+)"') == "0.1.0"
    assert rv.find_version("nope", r'x = "([0-9.]+)"') is None


def test_sync_badge_inserts_then_updates():
    md = "# ROAR\n\nsome text\n"
    once = rv.sync_badge(md, "0.16.0")
    assert "**Version:** v0.16.0" in once
    assert once.count(rv.BADGE_START) == 1
    # re-running to a new version replaces, never duplicates
    twice = rv.sync_badge(once, "0.17.0")
    assert "**Version:** v0.17.0" in twice
    assert "v0.16.0" not in twice
    assert twice.count(rv.BADGE_START) == 1


def test_echo_drift_and_rewrite():
    text = 'assert s["version"] == "0.15.0"\nassert APP_VERSION == "0.15.0"'
    pat = r'"version"\] == "([0-9.]+)"'
    assert rv.echo_drift(text, pat, "0.16.0") == ["0.15.0"]
    fixed = rv.rewrite_echo(text, pat, "0.16.0")
    assert '"version"] == "0.16.0"' in fixed
    assert rv.echo_drift(fixed, pat, "0.16.0") == []


# -- GitHub release parity (pure helpers; no network in tests) ---------------

def test_tag_to_version():
    assert rv.tag_to_version("v0.22.0") == "0.22.0"
    assert rv.tag_to_version("0.22.0") == "0.22.0"
    assert rv.tag_to_version(" v1.0.0 ") == "1.0.0"
    for junk in ("latest", "v1.2", "", None, "v1.2.3-beta"):
        assert rv.tag_to_version(junk) is None


def test_release_in_sync_is_no_drift():
    assert rv.release_drift("0.22.0", "v0.22.0", asset_count=1) == []


def test_stale_release_is_drift():
    """The real failure this exists to catch: the app moved on, the download
    everyone gets did not."""
    drift = rv.release_drift("0.22.0", "v0.7.0", asset_count=1)
    assert len(drift) == 1
    assert "v0.7.0" in drift[0] and "v0.22.0" in drift[0]


def test_no_release_at_all_is_drift():
    drift = rv.release_drift("0.22.0", None)
    assert len(drift) == 1 and "no GitHub release" in drift[0]


def test_release_without_an_asset_is_drift():
    """A tag with nothing attached means there is nothing to download."""
    drift = rv.release_drift("0.22.0", "v0.22.0", asset_count=0)
    assert len(drift) == 1 and "no downloadable asset" in drift[0]


def test_nonstandard_tag_is_reported():
    drift = rv.release_drift("0.22.0", "release-2026", asset_count=1)
    assert any("not vX.Y.Z" in d for d in drift)


def test_no_canonical_version_means_no_release_opinion():
    assert rv.release_drift(None, None) == []


def test_every_component_declares_its_github_repo():
    for c in rv.COMPONENTS:
        assert c.get("github"), c["name"]


def test_readme_prose_carries_the_app_version():
    """README version prose remains managed by --fix."""
    import pathlib
    import re

    import paths
    readme = pathlib.Path("README.md").read_text(encoding="utf-8")
    m = re.search(r"Current app version: `([0-9.]+)`", readme)
    assert m and m.group(1) == paths.APP_VERSION


def test_desktop_version_echoes_do_not_stamp_release_assets():
    """A release asset is selected from the verified manifest, not APP_VERSION."""
    echoes = rv.COMPONENTS[0]["echo"]
    assert all("site/" not in rel.replace("\\", "/") for rel, _ in echoes)


def test_site_hero_has_no_hardcoded_latest_release_version():
    """The hero must not drift from release metadata shown in download cards."""
    import pathlib

    html = pathlib.Path("site/index.html").read_text(encoding="utf-8")
    assert "Latest release:" not in html
    assert 'id="roar-version"' not in html


def test_dashboard_uses_stable_desktop_source_and_keeps_external_source(tmp_path, monkeypatch):
    """The dashboard must not leak a worktree-specific desktop path."""
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    android = tmp_path.parent / "roar-android"
    monkeypatch.setattr(rv, "DESKTOP", str(desktop))

    rv.write_dashboard([
        {"name": "ROAR Desktop (Windows)", "root": str(desktop),
         "version": "0.35.2", "found": True, "drift": [], "release": "v0.35.2"},
        {"name": "ROAR Android", "root": str(android),
         "version": "0.7.0", "found": True, "drift": [], "release": None},
    ])

    dashboard = (desktop / "VERSIONS.md").read_text(encoding="utf-8")
    assert "| ROAR Desktop (Windows) | v0.35.2 | v0.35.2 | `.` |" in dashboard
    assert f"| ROAR Android | v0.7.0 | \u2014 | `{android}` |" in dashboard
