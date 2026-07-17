"""Grandfathering for installs that predate commercial gating.

Every paid-target feature shipped FREE up to v0.21.0. Gating them outright would
take features away from existing users of a public, free app, so an install that
predates gating receives a ONE-TIME grant of exactly those features.

Hard invariants (these are what make the grant safe):
  * A grant is a set of FEATURE IDs — it NEVER confers an edition. Only a signed
    license can do that, so "no unsigned value unlocks an edition" still holds.
  * A grant NEVER includes a feature that never shipped free (project vocabulary,
    developer snippet packs, file tagging stay Developer-only for everyone).
  * It is written once and stamped in config, so it is idempotent.
  * A fresh install gets NO grant and is gated normally.

Honest limit: this is local unsigned state. All local-only licensing is
honor-based — ROAR has no server by design. The blast radius is bounded: a grant
can never escalate to an edition, and never unlocks anything the user couldn't
already use.

Privacy: reads config keys + its own file only. Never transcript, audio,
history, snippets, vocabulary, clipboard, or the network.
"""
import json
import os

import paths

# The schema marker written into config once gating exists. Its ABSENCE in an
# existing config is what identifies a pre-gating install.
SCHEMA_KEY = "commercial_schema"
SCHEMA_VERSION = 1

# Exactly the paid-target features that shipped FREE through v0.21.0.
# Deliberately EXCLUDES never-shipped (planned) features:
#   vocabulary.project, snippets.developer_packs, files.tagging
GRANTED_FEATURES = frozenset({
    "snippets.packs", "snippets.variables_extended",
    "formatting.smart", "cleanup.advanced",
    "vocabulary.suggestions", "milestones.advanced",
    "history.filters", "settings.import_export",
    "profiles.apps", "profiles.per_app_language",
    "code.mode", "code.symbols",
})


def is_legacy_install(cfg) -> bool:
    """True when `cfg` came from a build that predates gating: a REAL, existing
    config that has not yet been stamped with the current schema. Pure.

    The caller must pass an EMPTY dict for a fresh install (no config.json on
    disk before this run) — an empty/None cfg is never legacy. This matters
    because `config.load()` merges DEFAULTS, so the schema key is always present
    after a load; only its VALUE distinguishes stamped from unstamped."""
    if not isinstance(cfg, dict) or not cfg:
        return False
    try:
        stamped = int(cfg.get(SCHEMA_KEY, 0) or 0)
    except (TypeError, ValueError):
        stamped = 0
    return stamped < SCHEMA_VERSION


def grant_for(cfg) -> frozenset:
    """The features a pre-gating install keeps. Pure; empty for fresh installs."""
    return GRANTED_FEATURES if is_legacy_install(cfg) else frozenset()


def load_grants(path=None) -> frozenset:
    """Read the recorded grant. Any problem → no grants (fail closed here: a
    missing/corrupt grant simply means 'gated', never a crash)."""
    path = path or paths.legacy_grant_path()
    try:
        if not os.path.exists(path):
            return frozenset()
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return frozenset()
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return frozenset()
    # Only ever honour features we actually grandfather — a hand-edited file
    # can never widen the grant beyond the shipped-free set, and can never
    # name an edition.
    return frozenset(f for f in features
                     if isinstance(f, str) and f in GRANTED_FEATURES)


def ensure_grant(cfg, path=None, log=print) -> frozenset:
    """Write the one-time grant for a pre-gating install and return the active
    grants. Idempotent: once the config carries the schema marker (stamped by
    the caller after this returns), this never grants again. Never raises."""
    path = path or paths.legacy_grant_path()
    existing = load_grants(path)
    if existing:
        return existing
    if not is_legacy_install(cfg):
        return frozenset()
    features = sorted(grant_for(cfg))
    try:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"schema": SCHEMA_VERSION, "reason": "pre_gating_install",
                       "features": features}, fh, indent=2)
    except Exception as e:
        log(f"could not record the legacy feature grant ({e}); "
            "continuing without it")
        return frozenset()
    log(f"grandfathered {len(features)} previously-free features for this "
        "existing install")
    return frozenset(features)
