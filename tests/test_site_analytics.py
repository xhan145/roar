"""Site analytics: exactly one sanctioned tracker seam, honest and inert-by-default.

The ROAR app promises "no telemetry" — the WEBSITE may count visits, but only
through the single GA4 seam, only when a Measurement ID is configured, and
always with a disclosure injected into the privacy section. These tests make
any other tracker (or a sneaky second script host) a build failure.
"""

import pathlib
import re

INDEX = pathlib.Path("site/index.html")
SUCCESS = pathlib.Path("site/purchase/success.html")

# The ONLY external script host the site may ever reference.
ALLOWED_SCRIPT_HOSTS = {"www.googletagmanager.com"}


def _html():
    return INDEX.read_text(encoding="utf-8")


def test_only_the_sanctioned_script_host_appears():
    for page in (INDEX, SUCCESS):
        text = page.read_text(encoding="utf-8")
        hosts = set(re.findall(r'https?://([^/"\'\s)]+)/[^"\']*\.js', text))
        assert hosts <= ALLOWED_SCRIPT_HOSTS, (page, hosts)


def test_ga4_seam_is_empty_or_a_measurement_id():
    m = re.search(r'ga4:\s*"([^"]*)"', _html())
    assert m, "the ga4 config seam must exist"
    assert m.group(1) == "" or re.fullmatch(r"G-[A-Z0-9]+", m.group(1)), \
        m.group(1)


def test_loader_is_gated_on_a_validated_id():
    html = _html()
    # the loader must validate the ID shape before injecting anything
    assert "/^G-[A-Z0-9]+$/.test(ROAR.ga4)" in html
    # and must never be an unconditional <script src=...gtag...> tag
    assert not re.search(r'<script[^>]+googletagmanager', html)


def test_loader_is_gated_on_explicit_consent():
    """Strict opt-in: GA4 loads only after Allow; Decline and silence load
    nothing. The stored choice is a plain localStorage key."""
    html = _html()
    assert 'CONSENT_KEY = "roar-analytics-consent"' in html
    assert 'if (choice === "granted") roarLoadGA4();' in html
    assert 'else if (choice !== "denied") roarConsentBanner();' in html
    # loading is never unconditional on config alone: the only CALL sites are
    # the granted branch and the Allow button ("();" excludes the definition)
    assert html.count("roarLoadGA4();") == 2


def test_banner_offers_a_real_decline():
    html = _html()
    assert '"denied"' in html
    assert "Decline" in html
    assert "Allow" in html


def test_disclosure_ships_with_the_tracker():
    """If analytics loads, the privacy section must say so in the same block."""
    html = _html()
    loader = html.split("test(ROAR.ga4)")[1].split("</script>")[0]
    assert "Google Analytics" in loader          # disclosure text present
    assert "app never does" in loader            # and it draws the app line
    assert "#privacy" in loader                  # appended to the privacy list


def test_no_other_known_trackers_anywhere():
    banned = ("google-analytics.com/analytics.js", "gtag/js?id=G-",  # hardcoded
              "facebook.net", "hotjar", "segment.com", "mixpanel",
              "plausible.io", "clarity.ms", "doubleclick")
    for page in (INDEX, SUCCESS):
        text = page.read_text(encoding="utf-8")
        for host in banned:
            assert host not in text, (page, host)


def test_success_page_stays_script_free():
    # Guarded in test_site_purchase_pages too; restated here in analytics
    # terms: nothing may ever record a checkout redirect's query params.
    assert "<script" not in SUCCESS.read_text(encoding="utf-8")
