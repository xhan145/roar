"""Commercial constants for ROAR — pricing, purchase URLs, support address, and
the bundled license-verification public key.

Pure constants only. This module imports nothing from the app's runtime and
never touches transcript/audio/history/vocabulary/clipboard/network. Editions
live in `entitlements.py` (the single source of truth for the vocabulary).

Placeholders marked `# TODO before launch` must be replaced with real values
(and IS_PRODUCTION flipped, with the real public key swapped in) before any paid
release. See docs/COMMERCIAL_READINESS_CHECKLIST.md.
"""

DEFAULT_EDITION = "core"
CURRENT_MAJOR_VERSION = 1

# One-time prices, USD. Buy once, use forever; no subscription.
PRO_PRICE_USD = 19
DEVELOPER_PRICE_USD = 29
SUPPORTER_PRICE_USD = 49

PURCHASE_URL_PRO = "https://example.com/roar/pro"                # TODO before launch
PURCHASE_URL_DEVELOPER = "https://example.com/roar/developer"    # TODO before launch
PURCHASE_URL_SUPPORTER = "https://example.com/roar/supporter"    # TODO before launch
SUPPORT_EMAIL = "support@example.com"                            # TODO before launch

# When False (repo/dev builds), dev-signed licenses are accepted so the app can
# be exercised end-to-end. A production build sets this True AND swaps in the
# real public key below; then dev-signed licenses are rejected. See license.py.
IS_PRODUCTION = False

# DEV license-verification public key (Ed25519). The matching PRIVATE key is
# NEVER committed — it lives only in the developer's environment for
# scripts/dev_generate_license.py. Swap this for the real key at production
# build time.  # TODO before launch
LICENSE_PUBLIC_KEY_PEM = """\
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEARhDZhd3AFXcTXUFWXArczqVwqVu4tNW9EElg5jbX08Q=
-----END PUBLIC KEY-----
"""
