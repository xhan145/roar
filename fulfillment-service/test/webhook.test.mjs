// Webhook handler matrix with injected fakes: the trust chain in order.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { makeHandler, AMOUNT_TO_EDITION } from "../api/paypal-webhook.js";

const { privateKey } = generateKeyPairSync("ed25519");
const PRIV_PEM = privateKey.export({ type: "pkcs8", format: "pem" });

function fakeRes() {
  return { statusCode: 0, body: "", end(t) { this.body = t || ""; } };
}

function event(over = {}) {
  return {
    event_type: over.event_type ?? "PAYMENT.CAPTURE.COMPLETED",
    resource: {
      id: "CAP-123", status: "COMPLETED",
      amount: { value: "19.00", currency_code: "USD" },
      payer: { email_address: "buyer@example.com",
               name: { given_name: "Ada", surname: "L" } },
      ...(over.resource || {}),
    },
  };
}

let calls;
function deps(over = {}) {
  calls = { claimed: [], issued: [], failed: [], emails: [], alerts: [] };
  return {
    verifyWebhook: async () => true,
    store: {
      claim: async (id) => { calls.claimed.push(id); return "claimed"; },
      markIssued: async (id, row) => calls.issued.push({ id, ...row }),
      markFailed: async (id, err) => calls.failed.push({ id, err }),
    },
    email: {
      sendLicense: async (m) => calls.emails.push(m),
      alertOwner: async (m) => calls.alerts.push(m),
    },
    log: () => {},
    env: { FULFILLMENT_PRIVATE_KEY_PEM: PRIV_PEM,
           OWNER_EMAIL: "owner@example.com" },
    ...over,
  };
}

test("happy path: verify -> claim -> sign -> email -> issued", async () => {
  const res = fakeRes();
  await makeHandler(deps())({ method: "POST", headers: {}, body: event() }, res);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body, "issued");
  assert.deepEqual(calls.claimed, ["CAP-123"]);
  assert.equal(calls.emails.length, 1);
  assert.equal(calls.emails[0].to, "buyer@example.com");
  const license = calls.issued[0].license;
  assert.match(license.license_id, /^ROAR-PRO-[23456789A-HJ-NP-Z]{8}$/);
  assert.equal(license.edition, "pro");
  assert.equal(license.valid_for_major, 1);
  assert.ok(license.signature.length > 60);
  assert.equal(license.env, undefined);          // never a dev licence
});

test("unverified webhook: 400, NOTHING happens", async () => {
  const d = deps({ verifyWebhook: async () => false });
  const res = fakeRes();
  await makeHandler(d)({ method: "POST", headers: {}, body: event() }, res);
  assert.equal(res.statusCode, 400);
  assert.equal(calls.claimed.length, 0);
  assert.equal(calls.emails.length, 0);
});

test("wrong amount: ignored, no claim", async () => {
  const res = fakeRes();
  await makeHandler(deps())({ method: "POST", headers: {}, body: event({
    resource: { amount: { value: "18.99", currency_code: "USD" } } }) }, res);
  assert.equal(res.statusCode, 200);
  assert.match(res.body, /ignored/);
  assert.equal(calls.claimed.length, 0);
});

test("wrong currency: ignored", async () => {
  const res = fakeRes();
  await makeHandler(deps())({ method: "POST", headers: {}, body: event({
    resource: { amount: { value: "19.00", currency_code: "EUR" } } }) }, res);
  assert.match(res.body, /ignored/);
  assert.equal(calls.claimed.length, 0);
});

test("other event types: ignored", async () => {
  const res = fakeRes();
  await makeHandler(deps())({ method: "POST", headers: {},
    body: event({ event_type: "PAYMENT.CAPTURE.REFUNDED" }) }, res);
  assert.match(res.body, /ignored/);
});

test("duplicate capture: single licence, 200", async () => {
  const d = deps();
  d.store.claim = async () => "already-issued";
  const res = fakeRes();
  await makeHandler(d)({ method: "POST", headers: {}, body: event() }, res);
  assert.equal(res.statusCode, 200);
  assert.match(res.body, /already/);
  assert.equal(calls.emails.length, 0);
});

test("email failure: failed row + owner alert + 500 for retry", async () => {
  const d = deps();
  d.email.sendLicense = async () => { throw new Error("resend down"); };
  const res = fakeRes();
  await makeHandler(d)({ method: "POST", headers: {}, body: event() }, res);
  assert.equal(res.statusCode, 500);
  assert.equal(calls.failed.length, 1);
  assert.equal(calls.alerts.length, 1);
  assert.equal(calls.issued.length, 0);
});

test("missing buyer email: failed + alert, never a silent licence", async () => {
  const res = fakeRes();
  await makeHandler(deps())({ method: "POST", headers: {}, body: event({
    resource: { payer: {} } }) }, res);
  assert.equal(res.statusCode, 500);
  assert.equal(calls.emails.length, 0);
  assert.equal(calls.failed.length, 1);
});

test("non-POST is rejected", async () => {
  const res = fakeRes();
  await makeHandler(deps())({ method: "GET", headers: {} }, res);
  assert.equal(res.statusCode, 405);
});

test("amount map covers exactly the three editions", () => {
  assert.deepEqual(Object.values(AMOUNT_TO_EDITION).sort(),
                   ["developer", "pro", "supporter"]);
});
