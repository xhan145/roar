"""Cross-cutting guarantees for the commercial layer: it must never touch user
dictation data or the network, must fail safe to Core, and its copy must never
imply a subscription/account/cloud model."""
import ast
import pathlib
import re

import commercial_config  # noqa: F401
import diagnostics
import entitlements as ent
import license as lic
import upgrade_prompts

ROOT = pathlib.Path(__file__).resolve().parent.parent

_USER_DATA_OR_NET = {
    "history", "audio", "transcriber", "recorder", "clipboard",
    "socket", "urllib", "requests", "http",
}


def _imported_modules(py_path):
    tree = ast.parse(pathlib.Path(py_path).read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def test_commercial_modules_import_no_user_data_or_network():
    for mod in ("license.py", "entitlements.py", "commercial_config.py",
                "upgrade_prompts.py", "license_service.py", "legacy_grant.py"):
        assert not (_imported_modules(ROOT / mod) & _USER_DATA_OR_NET), mod


def test_core_runs_without_any_license():
    assert lic.get_current_edition() == ent.CORE
    assert lic.get_current_edition(None) == ent.CORE
    # a core-defining feature is always usable with no license at all
    assert ent.allowed("dictation.push_to_talk") is True
    assert ent.allowed("privacy.controls") is True


def test_redact_diagnostics_removes_transcript_like_fields():
    out = diagnostics.redact_diagnostics({
        "version": "0.17.0", "transcript": "SECRET", "clipboard": "PW",
        "signature": "sig==", "email": "a@b.com",
    })
    assert out == {"version": "0.17.0"}


def test_dev_scripts_not_imported_by_any_app_module():
    banned = {"dev_generate_license", "verify_license_file"}
    for py in ROOT.glob("*.py"):
        assert not (_imported_modules(py) & banned), py.name


# --- copy hygiene: no positive subscription/account/cloud model -------------
_COMMERCIAL_COPY = [
    "README.md", "upgrade_prompts.py", "license_service.py",
    *[f"docs/{n}" for n in (
        "MONETIZATION.md", "PRICING.md", "FAQ.md", "PRIVACY_PROMISE.md",
        "FEATURE_MATRIX.md", "SUPPORT.md", "REFUND_POLICY.md",
        "COMMERCIAL_READINESS_CHECKLIST.md", "CHECKOUT_SETUP.md",
        "FOUNDER_COMPANY_READINESS.md", "LICENSING.md")],
]

# phrases that would signal the WRONG model. Bare words (subscription/account/
# cloud) are allowed because they appear only in negations and FAQ questions.
_FORBIDDEN_PHRASES = [
    "monthly", "per month", "recurring", "free trial", "subscribe",
    "billed", "create an account", "sign up", "sign in", "log in",
    "processed in the cloud", "upload your voice", "requires an account",
    "requires a subscription",
]


def test_commercial_copy_has_no_wrong_model_phrasing():
    for rel in _COMMERCIAL_COPY:
        text = (ROOT / rel).read_text(encoding="utf-8").lower()
        for phrase in _FORBIDDEN_PHRASES:
            assert phrase not in text, f"{rel}: {phrase!r}"


def test_pricing_states_the_reassurances():
    text = (ROOT / "docs" / "PRICING.md").read_text(encoding="utf-8").lower()
    for must in ("no subscription", "no account", "no cloud transcription"):
        assert must in text, must


# --- guard: every gated feature referenced in code is registered ------------
def test_referenced_features_are_registered():
    """If runtime code ever calls entitlements with a feature literal, that
    feature must be in KNOWN_FEATURES — so a gate can never silently miss one."""
    pat = re.compile(
        r"(?:allowed|can_use|requires_upgrade|minimum_edition_for)\(\s*[\"']([\w.]+)[\"']")
    referenced = set()
    for py in ROOT.glob("*.py"):
        referenced |= set(pat.findall(py.read_text(encoding="utf-8")))
    unregistered = referenced - ent.KNOWN_FEATURES
    assert not unregistered, f"unregistered features referenced in code: {unregistered}"
