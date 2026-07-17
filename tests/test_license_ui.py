"""The License section is display + activation only: always reachable, never a
gate, no startup upgrade nag, and purchase URLs come from configuration rather
than literals sprinkled through the markup."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = (ROOT / "settings.html").read_text(encoding="utf-8")
BRIDGE = (ROOT / "settings_ui.py").read_text(encoding="utf-8")


def test_license_section_has_activation_controls():
    for el in ("b-license-paste", "b-license-file", "b-license-remove",
               "b-buy-pro", "b-buy-dev", "b-buy-supporter",
               "a-license-status", "a-license-message", "a-license-meta"):
        assert f'id="{el}"' in HTML, el


def test_bridge_exposes_license_actions():
    for fn in ("def license_info", "def license_import",
               "def license_import_file", "def license_remove"):
        assert fn in BRIDGE, fn


def test_purchase_urls_come_from_configuration_not_hardcoded_markup():
    assert "info.purchase_urls" in HTML          # read from the bridge
    assert "example.com/roar" not in HTML        # never hard-coded in markup


def test_no_upgrade_prompt_opens_at_startup():
    """The purchase flow may only ever be BOUND to a click handler — never
    invoked during boot. Upgrade UI appears solely on intentional interaction."""
    opens = list(re.finditer(r"window\.open\(", HTML))
    assert opens, "expected the purchase buttons to open a URL on click"
    for m in opens:
        prefix = HTML[max(0, m.start() - 40):m.start()]
        assert "=>" in prefix, (
            "window.open must sit inside a click handler, not run at load")
    # and no auto-invoked upgrade/purchase modal
    assert not re.search(r"(showUpgrade|openUpgrade|upgradeModal)\s*\(\s*\)\s*;", HTML)


def test_bridge_rejects_oversize_paste_before_the_service():
    assert "MAX_IMPORT_BYTES" in BRIDGE


def test_remove_license_copy_reassures_data_is_kept():
    assert "your data is untouched" in HTML.lower()


def test_license_section_states_offline_and_no_account():
    low = HTML.lower()
    assert "validated locally" in low or "verified" in low
    assert "no account is required" in low


def test_upgrade_policy_copy_present_and_has_no_banned_terms():
    low = HTML.lower()
    assert "buy once and keep the version you purchased" in low
    for banned in ("lifetime updates", "limited-time", "trial expired",
                   "monthly plan", "annual plan"):
        assert banned not in low
