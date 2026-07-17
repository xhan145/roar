#!/usr/bin/env python3
"""ROAR version parity — one source of truth per component, everything else
checked/synced against it.

Each component has a CANONICAL version (a version constant in one file). This
tool:
  * reads the canonical version for every ROAR component it can find,
  * keeps a managed `**Version:** vX.Y.Z` badge in each README in sync,
  * verifies (and, with --fix, rewrites) the files that must echo that version
    (e.g. the version-asserting tests), so docs/tests can never drift again,
  * writes a cross-component dashboard to VERSIONS.md.

Usage:
  python scripts/roar_versions.py            # report + (re)write VERSIONS.md
  python scripts/roar_versions.py --check    # exit 1 on any drift (CI / pre-release)
  python scripts/roar_versions.py --fix      # sync READMEs + echo files, then report
  python scripts/roar_versions.py --github   # ALSO check the published GitHub release
  python scripts/roar_versions.py --install-hook   # add a pre-commit --check hook

GitHub parity (--github) answers "does what we ship match what we built?": it
compares each component's canonical version against the latest PUBLISHED GitHub
release and checks that release actually has a downloadable asset. It is
deliberately OPT-IN, because `--check` runs as a pre-commit hook and a hook must
never need the network. CI runs `--check --github` on every push instead — see
.github/workflows/version-parity.yml.

This tool NEVER publishes a release. Cutting a public release is a deliberate
act; the checker reports drift and leaves the decision to a human.

Pure parsing helpers (find_version / sync_badge / tag_to_version /
release_drift) are unit-tested; file I/O and network are kept thin around them.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.dirname(HERE)                       # ...\flowlocal
ANDROID = os.path.join(os.path.dirname(DESKTOP),
                       "StudioProjects", "roar-android")
ANDROID = os.environ.get("ROAR_ANDROID_DIR", ANDROID)

BADGE_START = "<!-- ROAR-VERSION -->"
BADGE_END = "<!-- /ROAR-VERSION -->"

# Each component: canonical source (file, regex with one capture group) + the
# files that MUST echo that exact version (file, regex whose match is rewritten).
COMPONENTS = [
    {
        "name": "ROAR Desktop (Windows)",
        "root": DESKTOP,
        "canonical": ("paths.py", r'APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"'),
        "echo": [
            ("tests/test_paths.py", r'APP_VERSION == "([0-9.]+)"'),
            ("tests/test_settings_bridge.py", r's\["version"\] == "([0-9.]+)"'),
        ],
        "readme": "README.md",
        "github": "xhan145/roar",
    },
    {
        "name": "ROAR Android",
        "root": ANDROID,
        "canonical": ("app/build.gradle.kts",
                      r'versionName\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"'),
        "echo": [],
        "readme": "README.md",
        "github": "xhan145/roar-android",
    },
]


# -- pure helpers ------------------------------------------------------------
def find_version(text, pattern):
    """First capture group of `pattern` in `text`, or None."""
    m = re.search(pattern, text)
    return m.group(1) if m else None


def sync_badge(readme_text, version):
    """Return README text with the managed version badge set to `version`.
    Inserts the badge just after the first heading if it isn't present yet."""
    block = f"{BADGE_START}\n**Version:** v{version}\n{BADGE_END}"
    if BADGE_START in readme_text and BADGE_END in readme_text:
        return re.sub(re.escape(BADGE_START) + r".*?" + re.escape(BADGE_END),
                      block, readme_text, count=1, flags=re.DOTALL)
    lines = readme_text.splitlines()
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    lines[insert_at:insert_at] = ["", block, ""]
    return "\n".join(lines) + ("\n" if readme_text.endswith("\n") else "")


def echo_drift(text, pattern, canonical):
    """List of mismatched versions this echo file currently holds."""
    return [m.group(1) for m in re.finditer(pattern, text)
            if m.group(1) != canonical]


def tag_to_version(tag):
    """'v0.22.0' / '0.22.0' -> '0.22.0'. Anything else -> None. Pure."""
    if not isinstance(tag, str):
        return None
    m = re.match(r"^v?([0-9]+\.[0-9]+\.[0-9]+)$", tag.strip())
    return m.group(1) if m else None


def release_drift(canonical, latest_tag, asset_count=0):
    """How the PUBLISHED GitHub release differs from what we built. Pure.

    This is the check that catches the failure nobody notices: the app bumps to
    v0.22.0 while the newest thing a user can actually download is v0.7.0.
    """
    if not canonical:
        return []
    if latest_tag is None:
        return [f"no GitHub release published - users cannot download v{canonical}"]
    published = tag_to_version(latest_tag)
    out = []
    if published is None:
        out.append(f"latest release tag {latest_tag!r} is not vX.Y.Z")
    elif published != canonical:
        out.append(f"latest GitHub release is v{published}, but this repo builds "
                   f"v{canonical} - publish a release")
    if asset_count == 0:
        out.append(f"release {latest_tag} has no downloadable asset")
    return out


# -- GitHub (network; opt-in, never in the pre-commit hook) -------------------
def fetch_latest_release(repo, timeout=10):
    """(tag, asset_count) for `repo`'s latest release; (None, 0) when there is
    none. Returns ('?', -1) when the lookup itself failed (offline, rate-limited,
    no auth) so callers can say "unknown" instead of crying drift. Never raises.
    """
    payload = _gh_api(f"repos/{repo}/releases/latest") or \
        _http_api(f"https://api.github.com/repos/{repo}/releases/latest", timeout)
    if payload == "none":
        return None, 0                      # 404 -> genuinely no release yet
    if not isinstance(payload, dict):
        return "?", -1                      # lookup failed -> unknown
    return payload.get("tag_name"), len(payload.get("assets") or [])


def _gh_api(path):
    """Use the gh CLI when present (handles auth + rate limits). None if gh is
    unavailable; 'none' when GitHub says 404."""
    try:
        p = subprocess.run(["gh", "api", path], capture_output=True, timeout=20)
    except Exception:
        return None
    if p.returncode != 0:
        err = (p.stderr or b"").decode("utf-8", "ignore")
        return "none" if "404" in err or "Not Found" in err else None
    try:
        return json.loads(p.stdout.decode("utf-8", "ignore"))
    except Exception:
        return None


def _http_api(url, timeout):
    """Unauthenticated fallback (public repos, 60 req/hr)."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "roar-version-parity"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        return "none" if e.code == 404 else None
    except Exception:
        return None


def rewrite_echo(text, pattern, canonical):
    """Rewrite every capture-group occurrence to `canonical`."""
    def repl(m):
        return m.group(0)[:m.start(1) - m.start()] + canonical + \
            m.group(0)[m.end(1) - m.start():]
    return re.sub(pattern, repl, text)


# -- component scan ----------------------------------------------------------
def _read(root, rel):
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def scan(component, github=False):
    root = component["root"]
    result = {"name": component["name"], "root": root, "version": None,
              "found": os.path.isdir(root), "drift": [], "release": None}
    if not result["found"]:
        return result
    cfile, cpat = component["canonical"]
    ctext = _read(root, cfile)
    result["version"] = find_version(ctext, cpat) if ctext else None
    v = result["version"]
    if v:
        # echo files
        for rel, pat in component["echo"]:
            t = _read(root, rel)
            if t is None:
                result["drift"].append(f"missing echo file {rel}")
                continue
            bad = echo_drift(t, pat, v)
            if bad:
                result["drift"].append(f"{rel} has {sorted(set(bad))}, want {v}")
        # readme badge
        rtext = _read(root, component["readme"])
        if rtext is not None and f"**Version:** v{v}" not in rtext:
            result["drift"].append(f"{component['readme']} badge != v{v}")
        # published GitHub release (opt-in: needs the network)
        if github and component.get("github"):
            tag, assets = fetch_latest_release(component["github"])
            if assets == -1:
                result["release"] = "unknown"   # lookup failed; not drift
            else:
                result["release"] = tag or "none"
                result["drift"].extend(release_drift(v, tag, assets))
    return result


def apply_fix(component, version):
    root = component["root"]
    changed = []
    for rel, pat in component["echo"]:
        t = _read(root, rel)
        if t is None:
            continue
        nt = rewrite_echo(t, pat, version)
        if nt != t:
            with open(os.path.join(root, rel), "w", encoding="utf-8", newline="\n") as f:
                f.write(nt)
            changed.append(rel)
    rrel = component["readme"]
    rtext = _read(root, rrel)
    if rtext is not None:
        nt = sync_badge(rtext, version)
        if nt != rtext:
            with open(os.path.join(root, rrel), "w", encoding="utf-8", newline="\n") as f:
                f.write(nt)
            changed.append(rrel)
    return changed


def write_dashboard(results):
    lines = ["# ROAR version dashboard", "",
             "_Generated by `scripts/roar_versions.py` — do not edit by hand._",
             "", "| Component | Version | Published | Source | Status |",
             "|---|---|---|---|---|"]
    for r in results:
        rel = r.get("release")
        pub = {None: "—", "none": "❌ none", "unknown": "? (offline)"}.get(rel, rel)
        if not r["found"]:
            lines.append(f"| {r['name']} | — | — | not found | ⚠️ missing |")
        elif r["drift"]:
            lines.append(f"| {r['name']} | v{r['version']} | {pub} | `{r['root']}` | "
                         f"❌ {len(r['drift'])} drift |")
        else:
            lines.append(f"| {r['name']} | v{r['version']} | {pub} | `{r['root']}` | "
                         f"✅ in sync |")
    lines.append("")
    lines.append("Components are versioned independently (a port at v0.1 need "
                 "not match the mature app) — this table proves each one is "
                 "internally consistent across its constant, README, and tests.")
    with open(os.path.join(DESKTOP, "VERSIONS.md"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


HOOK = ("#!/bin/sh\n"
        "exec python \"$(git rev-parse --show-toplevel)/scripts/roar_versions.py\" --check\n")


def install_hook():
    hook = os.path.join(DESKTOP, ".git", "hooks", "pre-commit")
    with open(hook, "w", encoding="utf-8", newline="\n") as f:
        f.write(HOOK)
    print(f"installed pre-commit --check hook at {hook}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 on drift")
    ap.add_argument("--fix", action="store_true", help="sync READMEs + echo files")
    ap.add_argument("--github", action="store_true",
                    help="also compare the published GitHub release (needs network; "
                         "deliberately NOT in the pre-commit hook)")
    ap.add_argument("--install-hook", action="store_true")
    args = ap.parse_args()

    if args.install_hook:
        install_hook()
        return 0

    results = [scan(c, github=args.github) for c in COMPONENTS]
    if args.fix:
        for c, r in zip(COMPONENTS, results):
            if r["found"] and r["version"]:
                changed = apply_fix(c, r["version"])
                if changed:
                    print(f"fixed {r['name']}: {', '.join(changed)}")
        results = [scan(c, github=args.github) for c in COMPONENTS]  # rescan post-fix

    write_dashboard(results)
    drift = False
    for r in results:
        tag = ("missing" if not r["found"]
               else f"v{r['version']}" if not r["drift"] else "DRIFT")
        rel = r.get("release")
        suffix = f"   published: {rel}" if rel else ""
        print(f"{r['name']:28} {tag}{suffix}")
        for d in r["drift"]:
            drift = True
            print(f"    - {d}")
    if args.check and drift:
        print("version drift detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
