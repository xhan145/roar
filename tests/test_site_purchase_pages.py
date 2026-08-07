"""The success page must never claim a licence was already delivered."""

import pathlib

PAGE = pathlib.Path("site/purchase/success.html")


def _html():
    return PAGE.read_text(encoding="utf-8")


def test_success_page_exists():
    assert PAGE.is_file()


def test_says_purchase_received():
    assert "Purchase received" in _html()


def test_never_claims_a_licence_was_sent():
    html = _html().lower()
    for lie in ("has been sent", "we've emailed", "we have emailed",
                "check your inbox", "license attached", "licence attached",
                "sent to your email"):
        assert lie not in html, lie


def test_does_not_treat_query_params_as_proof_of_payment():
    html = _html()
    # No client-side script may read a session id and unlock or assert anything.
    assert "URLSearchParams" not in html
    assert "<script" not in html


def test_links_back_to_download_and_activation_help():
    html = _html()
    assert "../index.html#download" in html
    assert "ROAR-Setup-" not in html
    assert "<script" not in html.lower()
    assert "index.html#faq" in html


def test_activation_help_actually_exists_on_the_site():
    """The success page points at the FAQ — the answer had better be there."""
    site = pathlib.Path("site/index.html").read_text(encoding="utf-8")
    assert 'id="faq"' in site
    assert "How do I activate a licence?" in site


def test_is_not_indexed():
    assert 'name="robots"' in _html()
