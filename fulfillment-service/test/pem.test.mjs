// Env-var PEM normalization: Vercel's env editor (and .env round-trips)
// flatten multiline PEMs — newlines become spaces, or arrive as literal
// backslash-n, or CRLF. signLicense must accept all of them, because a
// mangled key otherwise fails EVERY sale with DECODER routines::unsupported.
import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, verify as edVerify } from "node:crypto";

import { normalizePem, signLicense } from "../lib/sign.js";
import { canonicalBytes } from "../lib/canonical.js";

const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const PRIV_PEM = privateKey.export({ type: "pkcs8", format: "pem" });

const PAYLOAD = {
  license_id: "ROAR-PRO-TESTTEST",
  name: "Test Buyer",
  email_hash: null,
  edition: "pro",
  issued_at: "2026-08-01",
  valid_for_major: 1,
};

function assertSigns(pemVariant, label) {
  const signed = signLicense(PAYLOAD, pemVariant);
  const ok = edVerify(null, canonicalBytes(PAYLOAD),
                      publicKey, Buffer.from(signed.signature, "base64"));
  assert.equal(ok, true, `${label}: signature must verify`);
}

test("pristine multiline PEM still signs", () => {
  assertSigns(PRIV_PEM, "pristine");
});

test("PEM with newlines flattened to spaces signs (Vercel paste)", () => {
  assertSigns(PRIV_PEM.replace(/\r?\n/g, " "), "flattened");
});

test("PEM with literal backslash-n escapes signs (.env style)", () => {
  assertSigns(PRIV_PEM.replace(/\r?\n/g, "\\n"), "escaped");
});

test("PEM with CRLF line endings signs (Windows clipboard)", () => {
  assertSigns(PRIV_PEM.replace(/\n/g, "\r\n"), "crlf");
});

test("PEM with newlines removed entirely signs", () => {
  // headers keep their hyphens; base64 runs together
  const squashed = PRIV_PEM
    .replace(/-----\r?\n/g, "----- ")
    .replace(/\r?\n-----/g, " -----")
    .replace(/\r?\n/g, "");
  assertSigns(squashed, "squashed");
});

test("headerless base64 body signs (headers lost in paste)", () => {
  const bodyOnly = PRIV_PEM
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  assertSigns(bodyOnly, "headerless");
});

test("headerless base64 with stray whitespace signs", () => {
  const bodyOnly = PRIV_PEM
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .trim();
  assertSigns("  " + bodyOnly + "\n", "headerless-ws");
});

test("normalizePem leaves non-PEM garbage unchanged for a loud failure", () => {
  assert.equal(normalizePem("not a key"), "not a key");
  assert.throws(() => signLicense(PAYLOAD, "not a key"));
});

test("normalizePem output is byte-stable for already-clean input", () => {
  const once = normalizePem(PRIV_PEM);
  assert.equal(normalizePem(once), once);
});
