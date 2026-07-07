#!/usr/bin/env python3
"""Verify a ROAR license file offline and print its edition/validity/reason.

For support and debugging. Uses the bundled public key by default, or a supplied
PEM. Never touches the network; never reads user dictation data.

Usage:
    python scripts/verify_license_file.py roar_license.json
    python scripts/verify_license_file.py roar_license.json --public-key key.pem
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import commercial_config  # noqa: E402
import license as lic  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("license_file")
    ap.add_argument("--public-key",
                    help="PEM public-key file; defaults to the bundled key.")
    args = ap.parse_args()

    if args.public_key:
        with open(args.public_key, "rb") as fh:
            verifier = lic.CryptographySignatureVerifier(fh.read())
    else:
        verifier = lic.CryptographySignatureVerifier(commercial_config.LICENSE_PUBLIC_KEY_PEM)

    result = lic.load_license(args.license_file, verifier=verifier)
    print(f"edition={result.edition} valid={result.valid} reason={result.reason}")
    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
