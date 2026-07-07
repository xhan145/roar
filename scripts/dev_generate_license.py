#!/usr/bin/env python3
"""LOCAL TESTING ONLY — generate a signed ROAR test license.

NOT FOR PRODUCTION. The production signing key must live in a secret manager and
never touch this repo. This script is a standalone developer tool; the app never
imports it. The private key is read from the environment, never from the repo.

Usage:
    export ROAR_LICENSE_PRIVATE_KEY_FILE=/path/to/dev_private_key.pem
    python scripts/dev_generate_license.py --edition pro --out roar_license.json
"""
import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import license as lic  # noqa: E402


def _load_private_key():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    pem = os.environ.get("ROAR_LICENSE_PRIVATE_KEY_PEM")
    key_file = os.environ.get("ROAR_LICENSE_PRIVATE_KEY_FILE")
    if not pem and key_file:
        with open(key_file, "rb") as fh:
            pem = fh.read()
    if not pem:
        sys.exit("Set ROAR_LICENSE_PRIVATE_KEY_PEM or ROAR_LICENSE_PRIVATE_KEY_FILE.")
    if isinstance(pem, str):
        pem = pem.encode()
    return load_pem_private_key(pem, password=None)


def main():
    if getattr(sys, "frozen", False):
        sys.exit("Developer tool — must not run inside a packaged ROAR build.")
    print("=== LOCAL TESTING ONLY — not for production ===", file=sys.stderr)

    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", default="pro",
                    choices=["pro", "developer", "supporter"])
    ap.add_argument("--name", default="Local Tester")
    ap.add_argument("--major", type=int, default=1)
    ap.add_argument("--out", default="roar_license.json")
    args = ap.parse_args()

    priv = _load_private_key()
    payload = {
        "license_id": f"ROAR-{args.edition.upper()}-DEV",
        "name": args.name,
        "email_hash": None,
        "edition": args.edition,
        "issued_at": "dev",
        "valid_for_major": args.major,
        "env": "dev",   # rejected by a production verifier — see license.py
    }
    payload["signature"] = base64.b64encode(
        priv.sign(lic.canonical_bytes(payload))).decode()
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"wrote {args.out} (edition={args.edition})")


if __name__ == "__main__":
    main()
