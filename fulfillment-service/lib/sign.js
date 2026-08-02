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

// Env editors mangle pasted PEMs: Vercel flattens newlines to spaces (or
// strips them), .env files carry literal "\n", Windows clipboards add CRLF.
// Rebuild the canonical form from the base64 body so createPrivateKey never
// chokes on a paste artifact. Non-PEM input is returned untouched so it still
// fails loudly downstream.
export function normalizePem(pem) {
  const s = String(pem || "").replace(/\\n/g, "\n").trim();
  const m = s.match(/-----BEGIN ([A-Z0-9 ]+)-----([\s\S]*?)-----END \1-----/);
  if (m) {
    return wrapPem(m[1], m[2]);
  }
  // Headers lost entirely: a bare base64 body of key-like length is
  // unambiguous, so re-wrap it as PKCS8. Anything else passes through
  // untouched and fails loudly in createPrivateKey.
  const bare = s.replace(/\s+/g, "");
  if (/^[A-Za-z0-9+/]{40,}={0,2}$/.test(bare)) {
    return wrapPem("PRIVATE KEY", bare);
  }
  return s;
}

function wrapPem(label, body) {
  const b64 = body.replace(/[^A-Za-z0-9+/=]/g, "");
  const wrapped = b64.replace(/(.{64})/g, "$1\n").trim();
  return `-----BEGIN ${label}-----\n${wrapped}\n-----END ${label}-----\n`;
}

export function signLicense(payload, privateKeyPem) {
  const key = createPrivateKey(normalizePem(privateKeyPem));
  const signature = edSign(null, canonicalBytes(payload), key);
  return { ...payload, signature: signature.toString("base64") };
}

export function issueLicense({ edition, name, emailHash, privateKeyPem, now }) {
  const token = tokenFromBytes(randomBytes(8));
  const issuedAt = (now || new Date()).toISOString().slice(0, 10);
  const payload = buildPayload({ edition, name, emailHash, issuedAt, token });
  return signLicense(payload, privateKeyPem);
}
