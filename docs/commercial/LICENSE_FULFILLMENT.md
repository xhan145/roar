# ROAR License Fulfillment Runbook

How to generate a signed license for a customer. Offline, one private key, no
server. Editions and the feature matrix live in the commercial spec; this doc is
just the operational "someone bought it, now what" steps.

## One-time setup (already done)

The production signing keypair was generated with:

```bash
python scripts/generate_keypair.py
```

- **Private key:** `~/.roar-signing/roar_license_private_key.pem` — kept OFF the
  repo. Back it up somewhere safe (a password manager or an encrypted drive). If
  you lose it you can't sign new licenses; if it leaks, anyone can mint them.
- **Public key:** baked into `commercial_config.LICENSE_PUBLIC_KEY_PEM`, with
  `IS_PRODUCTION = True`. This is what every shipped ROAR build verifies against.

Rotating the key (`--force`) invalidates **every license already sold**, so
treat the current keypair as permanent.

## Per sale

When someone buys (via the pre-order email, or later a checkout processor):

```bash
export ROAR_LICENSE_PRIVATE_KEY_FILE=~/.roar-signing/roar_license_private_key.pem

python scripts/issue_license.py \
    --edition pro \
    --name "Ada Lovelace" \
    --email ada@example.com \
    --out ada_roar_license.json
```

- `--edition` is one of `pro`, `developer`, `supporter` (Core is free — never
  needs a license).
- `--name` shows in the customer's License screen.
- `--email` is **hashed** (SHA-256) into the license for support lookups; the
  raw address is never written to the file.
- The tool mints a unique id (`ROAR-PRO-XXXXXXXX`), stamps today's date, signs,
  and then **re-verifies the result against the app's public key in production
  mode** — if your private key doesn't match the shipped public key it refuses
  to write, so you can't email a dead license.

Then email `ada_roar_license.json` to the customer. They open ROAR →
**Settings → License → Import**, pick the file, and the edition activates
offline. Nothing phones home.

## Verifying / supporting a license

To check a file a customer sends back ("it says Core"):

```bash
python scripts/verify_license_file.py ada_roar_license.json
# edition=pro valid=True reason=ok
```

Common `reason` values and what they mean: `ok` (good), `bad_signature`
(tampered, or signed with the wrong key — e.g. an old dev build), `wrong_major`
(license was issued for a different major version), `dev_rejected` (a test
license on a production build), `core`/`missing` (no valid license → free tier).

## Guardrails baked in

- Issued licenses carry **no `env:"dev"`** marker, so production builds accept
  them (dev/test licenses are rejected).
- Customer email is only ever stored **hashed**.
- `.gitignore` blocks `*_private_key.pem` and `roar_*_<edition>_*.json`, so a key
  or an issued license can't be committed by accident.
- The signer never touches transcripts, audio, history, vocabulary, or the
  network — it only reads the private key and writes one JSON file.

## Important: the customer needs a build with the production key

Licenses signed here verify against the **production** public key. A ROAR build
must be shipped with `IS_PRODUCTION = True` and this public key (i.e. built from
this commit or later) for the license to activate. The v0.22.0 build that
predates the production keypair trusts the old dev key and will read these
licenses as Core — the first production-signed release supersedes it.
