// The trust-critical test: JS canonicalization must be byte-identical to
// Python's license.canonical_bytes, proven against a Python-generated fixture
// (regenerate with scripts/make_fulfillment_fixture.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createPublicKey, verify as edVerify } from "node:crypto";
import { canonicalBytes } from "../lib/canonical.js";
import { signLicense, buildPayload, tokenFromBytes } from "../lib/sign.js";
import { generateKeyPairSync } from "node:crypto";

const fixture = JSON.parse(readFileSync(
  new URL("./fixtures/canonical.json", import.meta.url), "utf-8"));

test("canonical bytes match Python byte-for-byte (incl. non-ASCII)", () => {
  const ours = canonicalBytes(fixture.payload).toString("utf-8");
  assert.equal(ours, fixture.canonical);
});

test("Python's signature verifies over OUR canonical bytes", () => {
  const key = createPublicKey(fixture.public_key_pem);
  const ok = edVerify(null, canonicalBytes(fixture.payload),
                      key, Buffer.from(fixture.signature_b64, "base64"));
  assert.equal(ok, true);
});

test("signature key is excluded from canonical form", () => {
  const withSig = { ...fixture.payload, signature: "AAAA" };
  assert.equal(canonicalBytes(withSig).toString("utf-8"), fixture.canonical);
});

test("JS sign -> JS verify round trip", () => {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const payload = buildPayload({
    edition: "developer", name: "Röund Trip", emailHash: "b".repeat(64),
    issuedAt: "2026-08-01", token: tokenFromBytes(Buffer.alloc(8, 7)),
  });
  const signed = signLicense(payload,
    privateKey.export({ type: "pkcs8", format: "pem" }));
  const ok = edVerify(null, canonicalBytes(signed), publicKey,
                      Buffer.from(signed.signature, "base64"));
  assert.equal(ok, true);
});

test("floats are refused — Python emits them differently", () => {
  assert.throws(() => canonicalBytes({ a: 1.5 }));
});
