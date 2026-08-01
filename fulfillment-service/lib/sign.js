// Licence signing with the SUBORDINATE fulfilment key (env:
// FULFILLMENT_PRIVATE_KEY_PEM). Payload shape mirrors license_issuer.py
// exactly; the app verifies with license.MultiKeyVerifier.
import { createPrivateKey, randomBytes, sign as edSign } from "node:crypto";
import { canonicalBytes } from "./canonical.js";

// Same unambiguous alphabet as license_issuer._TOKEN_ALPHABET.
const TOKEN_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
export const SELLABLE_EDITIONS = ["pro", "developer", "supporter"];

export function tokenFromBytes(raw, length = 8) {
  let out = "";
  for (let i = 0; i < length; i++) {
    out += TOKEN_ALPHABET[raw[i] % TOKEN_ALPHABET.length];
  }
  return out;
}

export function buildPayload({ edition, name, emailHash, issuedAt, token }) {
  if (!SELLABLE_EDITIONS.includes(edition)) {
    throw new Error(`not a sellable edition: ${edition}`);
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(issuedAt)) {
    throw new Error(`issued_at must be YYYY-MM-DD, got ${issuedAt}`);
  }
  if (!/^[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{8}$/.test(token)) {
    throw new Error("bad token");
  }
  return {
    license_id: `ROAR-${edition.toUpperCase()}-${token}`,
    name: String(name || ""),
    email_hash: emailHash || null,
    edition,
    issued_at: issuedAt,
    valid_for_major: 1,
  };
}

export function signLicense(payload, privateKeyPem) {
  const key = createPrivateKey(privateKeyPem);
  const signature = edSign(null, canonicalBytes(payload), key);
  return { ...payload, signature: signature.toString("base64") };
}

export function issueLicense({ edition, name, emailHash, privateKeyPem, now }) {
  const token = tokenFromBytes(randomBytes(8));
  const issuedAt = (now || new Date()).toISOString().slice(0, 10);
  const payload = buildPayload({ edition, name, emailHash, issuedAt, token });
  return signLicense(payload, privateKeyPem);
}
