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
