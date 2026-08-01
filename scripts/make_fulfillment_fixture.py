#!/usr/bin/env python3
"""Generate the cross-language canonicalization fixture for the fulfilment
service. The JS signer must produce byte-identical canonical bytes to
license.canonical_bytes — this fixture is the proof.

Writes fulfillment-service/test/fixtures/canonical.json containing a payload
(with a deliberately non-ASCII name to pin ensure_ascii behaviour), the exact
canonical string Python signs, a signature from an EPHEMERAL test key, and
that key's PUBLIC pem. No private key is written anywhere.
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import license as lic  # noqa: E402
import license_issuer as iss  # noqa: E402

from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey)
from cryptography.hazmat.primitives.serialization import (  # noqa: E402
    Encoding, PublicFormat)

priv = Ed25519PrivateKey.generate()
pub_pem = priv.public_key().public_bytes(
    Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

payload = iss.build_payload(
    edition="pro",
    name="José Ñandú — ROAR tester",     # non-ASCII on purpose (ensure_ascii)
    license_id="ROAR-PRO-TEST2345",
    issued_at="2026-08-01",
    valid_for_major=1,
    email_hash="a" * 64,
)
canonical = lic.canonical_bytes(payload).decode("utf-8")
signature = base64.b64encode(priv.sign(lic.canonical_bytes(payload))).decode()

out = {
    "payload": payload,
    "canonical": canonical,
    "signature_b64": signature,
    "public_key_pem": pub_pem,
}
dest = os.path.join(os.path.dirname(__file__), "..", "fulfillment-service",
                    "test", "fixtures", "canonical.json")
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=True)
print(f"fixture written: {dest}")
