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
  python scripts/roar_versions.py --install-hook   # add a pre-commit --check hook

Pure parsing helpers (find_version / sync_badge) are unit-tested; file I/O is
kept thin around them.
"""
import argparse
import os
import re
import sys

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
    },
    {
        "name": "ROAR Android",
        "root": ANDROID,
        "canonical": ("app/build.gradle.kts",
                      r'versionName\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"'),
        "echo": [],
        "readme": "README.md",
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


def scan(component):
    root = component["root"]
    result = {"name": component["name"], "root": root, "version": None,
              "found": os.path.isdir(root), "drift": []}
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
             "", "| Component | Version | Source | Status |",
             "|---|---|---|---|"]
    for r in results:
        if not r["found"]:
            lines.append(f"| {r['name']} | — | not found | ⚠️ missing |")
        elif r["drift"]:
            lines.append(f"| {r['name']} | v{r['version']} | `{r['root']}` | "
                         f"❌ {len(r['drift'])} drift |")
        else:
            lines.append(f"| {r['name']} | v{r['version']} | `{r['root']}` | ✅ in sync |")
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
    ap.add_argument("--install-hook", action="store_true")
    args = ap.parse_args()

    if args.install_hook:
        install_hook()
        return 0

    results = [scan(c) for c in COMPONENTS]
    if args.fix:
        for c, r in zip(COMPONENTS, results):
            if r["found"] and r["version"]:
                changed = apply_fix(c, r["version"])
                if changed:
                    print(f"fixed {r['name']}: {', '.join(changed)}")
        results = [scan(c) for c in COMPONENTS]  # rescan post-fix

    write_dashboard(results)
    drift = False
    for r in results:
        tag = ("missing" if not r["found"]
               else f"v{r['version']}" if not r["drift"] else "DRIFT")
        print(f"{r['name']:28} {tag}")
        for d in r["drift"]:
            drift = True
            print(f"    - {d}")
    if args.check and drift:
        print("version drift detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
