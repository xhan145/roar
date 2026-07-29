"""The automated fulfilment seam must refuse loudly — never fake a licence."""

import pathlib

import pytest

import fulfillment


def test_unknown_edition_is_rejected():
    with pytest.raises(ValueError):
        fulfillment.issue_license("bogus", "cs_test_123")


def test_core_is_not_purchasable():
    with pytest.raises(ValueError):
        fulfillment.issue_license("core", "cs_test_123")


def test_missing_session_id_is_rejected():
    with pytest.raises(ValueError):
        fulfillment.issue_license("pro", "")
    with pytest.raises(ValueError):
        fulfillment.issue_license("pro", "   ")
    with pytest.raises(ValueError):
        fulfillment.issue_license("pro", None)


def test_unsupported_major_version_is_rejected():
    with pytest.raises(ValueError):
        fulfillment.issue_license("pro", "cs_test_123", major_version=2)


def test_valid_request_fails_explicitly_not_silently():
    # No secure server and no signing key here, so it must raise — never
    # return a made-up "delivered" result.
    with pytest.raises(fulfillment.FulfillmentUnavailable) as excinfo:
        fulfillment.issue_license("pro", "cs_test_123", "buyer@example.com")
    assert "manual" in str(excinfo.value).lower()


def test_result_type_is_shaped_for_the_future_implementation():
    r = fulfillment.LicenseDeliveryResult(
        delivered=False, edition="pro", stripe_session_id="cs_test_123",
        reason="stub")
    assert r.delivered is False
    assert r.edition == "pro"
    assert r.stripe_session_id == "cs_test_123"


def test_module_never_touches_the_signing_key():
    source = pathlib.Path("fulfillment.py").read_text(encoding="utf-8")
    for forbidden in ("Ed25519PrivateKey", "private_bytes", ".pem",
                      "load_pem_private_key"):
        assert forbidden not in source, forbidden


def test_module_reads_no_user_data():
    """Licensing code never touches transcripts, audio, history, or clipboard."""
    source = pathlib.Path("fulfillment.py").read_text(encoding="utf-8")
    for forbidden in ("import history", "import clipboard", "import config",
                      "open(", "requests", "urllib"):
        assert forbidden not in source, forbidden
