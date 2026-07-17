#!/usr/bin/env python3
"""Generate the ROAR license SIGNING keypair (Ed25519).

Run this ONCE to bootstrap production signing. It writes the PRIVATE key to a
file OUTSIDE the repository and prints the PUBLIC key PEM to paste into
`commercial_config.LICENSE_PUBLIC_KEY_PEM`.

Security, enforced by this script:
  * the private key is NEVER printed and NEVER written inside the repo tree;
  * it refuses to overwrite an existing private key (use --force only if you
    truly mean to invalidate every license you've already sold);
  * the file is created with owner-only permissions where the OS supports it.

Usage:
    python scripts/generate_keypair.py
    python scripts/generate_keypair.py --out "C:/Users/me/.roar-signing/prod.pem"

Keep the printed public key; guard the private key like a password. If you lose
the private key you can't sign new licenses; if it leaks, anyone can mint them.
"""
import argparse
import os
import stat
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUT = os.path.join(os.path.expanduser("~"), ".roar-signing",
                            "roar_license_private_key.pem")


def _is_inside_repo(path):
    try:
        common = os.path.commonpath([os.path.abspath(path), _REPO])
    except ValueError:  # different drive on Windows
        return False
    return common == _REPO


def main():
    ap = argparse.ArgumentParser(description="Generate the ROAR signing keypair.")
    ap.add_argument("--out", default=_DEFAULT_OUT,
                    help=f"private-key path (default: {_DEFAULT_OUT})")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing private key (DANGEROUS: "
                         "invalidates already-issued licenses)")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    if _is_inside_repo(out):
        sys.exit("Refusing to write a private key inside the repository. "
                 "Choose a path outside the repo (e.g. ~/.roar-signing/).")
    if os.path.exists(out) and not args.force:
        sys.exit(f"{out} already exists. Refusing to overwrite (use --force to "
                 "replace it and invalidate every license signed with the old key).")

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as ser

    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption())
    pub_pem = priv.public_key().public_bytes(
        ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    # Create with owner-only perms, before writing any bytes.
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, priv_pem)
    finally:
        os.close(fd)
    try:
        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 (best-effort on Win)
    except OSError:
        pass

    print(f"Private key written to: {out}")
    print("  -> keep this secret and OFF the repo. Back it up somewhere safe.")
    print()
    print("Paste this PUBLIC key into commercial_config.LICENSE_PUBLIC_KEY_PEM,")
    print("then set IS_PRODUCTION = True and cut a signed release:")
    print()
    sys.stdout.write(pub_pem.decode())


if __name__ == "__main__":
    main()
