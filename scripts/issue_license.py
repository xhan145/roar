#!/usr/bin/env python3
"""Issue a signed ROAR license for a real customer (offline fulfilment).

This is the tool you run when someone buys ROAR: it mints a unique license id,
stamps today's date, signs the payload with your PRIVATE key, writes the JSON,
and then re-verifies it against the matching PUBLIC key so you never send a
broken file.

Unlike scripts/dev_generate_license.py, the output carries NO `env: "dev"`
marker, so a production build (IS_PRODUCTION = True) accepts it.

The private key is read from the environment or --key — NEVER from the repo:
    export ROAR_LICENSE_PRIVATE_KEY_FILE=~/.roar-signing/roar_license_private_key.pem
    python scripts/issue_license.py --edition pro --name "Ada Lovelace" \
        --email ada@example.com --out ada_roar_license.json

The customer's email is only ever stored as a salted-free SHA-256 hash (for
support lookups); the raw address is never written to the license.
"""
import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
from datetime import date, timezone, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import license as lic  # noqa: E402
import license_issuer as iss  # noqa: E402
import commercial_config  # noqa: E402


def _load_private_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    pem = os.environ.get("ROAR_LICENSE_PRIVATE_KEY_PEM")
    key_file = os.environ.get("ROAR_LICENSE_PRIVATE_KEY_FILE")
    if not pem and key_file:
        with open(os.path.expanduser(key_file), "rb") as fh:
            pem = fh.read()
    if not pem:
        sys.exit("Set ROAR_LICENSE_PRIVATE_KEY_FILE (or _PEM), or pass --key.")
    if isinstance(pem, str):
        pem = pem.encode()
    return load_pem_private_key(pem, password=None)


def _email_hash(email):
    if not email:
        return None
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def main():
    if getattr(sys, "frozen", False):
        sys.exit("Developer tool — must not run inside a packaged ROAR build.")

    ap = argparse.ArgumentParser(description="Issue a signed ROAR license.")
    ap.add_argument("--edition", required=True,
                    choices=list(iss.SELLABLE_EDITIONS))
    ap.add_argument("--name", default="", help="customer name (shown in-app)")
    ap.add_argument("--email", default="", help="hashed for support; never stored raw")
    ap.add_argument("--major", type=int, default=commercial_config.CURRENT_MAJOR_VERSION,
                    help="major version this license is valid for")
    ap.add_argument("--key", help="private-key PEM file (overrides env)")
    ap.add_argument("--out", help="output path (default: roar_<edition>_<id>.json)")
    args = ap.parse_args()

    if args.key:
        os.environ["ROAR_LICENSE_PRIVATE_KEY_FILE"] = args.key
    priv = _load_private_key()

    token = iss.token_from_bytes(secrets.token_bytes(8), length=8)
    license_id = iss.new_license_id(args.edition, token)
    payload = iss.build_payload(
        edition=args.edition,
        name=args.name,
        license_id=license_id,
        issued_at=date.today().isoformat(),
        valid_for_major=args.major,
        email_hash=_email_hash(args.email),
    )
    payload["signature"] = base64.b64encode(
        priv.sign(lic.canonical_bytes(payload))).decode()

    out = args.out or f"roar_{args.edition}_{token}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    # Self-verify against the PUBLIC key baked into the app, in production mode,
    # so a key mismatch or a stale build fails here instead of at the customer.
    verifier = lic.CryptographySignatureVerifier(
        commercial_config.LICENSE_PUBLIC_KEY_PEM)
    result = lic.validate_license(payload, verifier=verifier,
                                  current_major=args.major, is_production=True)
    if not (result.valid and result.edition == iss.normalize_edition(args.edition)):
        sys.exit(f"REFUSING TO SHIP: the signed license did not verify against "
                 f"the app's public key (reason={result.reason}). Your private "
                 f"key does not match commercial_config.LICENSE_PUBLIC_KEY_PEM.")

    print(f"Issued {license_id}  ({args.edition})")
    print(f"  file:  {out}")
    print(f"  major: {args.major}   issued: {payload['issued_at']}")
    print("  verified against the app public key (production mode): OK")
    print("Send this file to the customer; they import it in Settings -> License.")


if __name__ == "__main__":
    main()
