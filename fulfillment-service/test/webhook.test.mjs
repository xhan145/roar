// Webhook handler matrix with injected fakes: the hardened trust chain.
import { test } from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { makeHandler, AMOUNT_TO_EDITION, signingKeyFor }
  from "../api/paypal-webhook.js";

const { privateKey } = generateKeyPairSync("ed25519");
const PRIV_PEM = privateKey.export({ type: "pkcs8", format: "pem" });
const LIVE = "https://api-m.paypal.com";

const PAYPAL_HEADERS = {
  "paypal-auth-algo": "SHA256withRSA",
  "paypal-cert-url": "https://api.paypal.com/cert",
  "paypal-transmission-id": "t-1",
  "paypal-transmission-sig": "sig",
  "paypal-transmission-time": "2026-08-01T00:00:00Z",
};

function fakeRes() {
  return { statusCode: 0, body: "", end(t) { this.body = t || ""; } };
}

function event(over = {}) {
  return {
    event_type: over.event_type ?? "PAYMENT.CAPTURE.COMPLETED",
    resource: {
      id: "CAP-123", status: "COMPLETED",
      amount: { value: "19.00", currency_code: "USD" },
      payee: { merchant_id: "MERCH1" },
      supplementary_data: { related_ids: { order_id: "ORDER-9" } },
      ...(over.resource || {}),
    },
  };
}

function reqFor(body, over = {}) {
  return { method: "POST", headers: { ...PAYPAL_HEADERS },
           rawBody: JSON.stringify(body), ...over };
}

let calls;
function deps(over = {}) {
  calls = { verify: [], claimed: [], signed: [], issued: [], failed: [],
            emails: [], alerts: [], orderLookups: [] };
  return {
    verifyWebhook: async (h, raw) => { calls.verify.push(raw); return true; },
    getOrderPayer: async (id) => {
      calls.orderLookups.push(id);
      return { email: "buyer@example.com", name: "Ada L" };
    },
    store: {
      claim: async (id) => { calls.claimed.push(id); return { state: "claimed" }; },
      markSigned: async (id, row) => calls.signed.push({ id, ...row }),
      markIssued: async (id) => calls.issued.push(id),
      markFailed: async (id, err) => calls.failed.push({ id, err }),
    },
    email: {
      sendLicense: async (m) => calls.emails.push(m),
      alertOwner: async (m) => calls.alerts.push(m),
    },
    log: () => {},
    env: { FULFILLMENT_PRIVATE_KEY_PEM: PRIV_PEM,
           PAYPAL_API_BASE: LIVE,
           PAYPAL_MERCHANT_ID: "MERCH1",
           OWNER_EMAIL: "owner@example.com" },
    ...over,
  };
}

test("happy path: headers -> raw verify -> claim -> order payer -> sign(persist) -> email -> issued", async () => {
  const res = fakeRes();
  await makeHandler(deps())(reqFor(event()), res);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body, "issued");
  assert.deepEqual(calls.orderLookups, ["ORDER-9"]);
  assert.equal(calls.signed.length, 1);          // persisted BEFORE email
  assert.equal(calls.emails.length, 1);
  assert.deepEqual(calls.issued, ["CAP-123"]);
  const license = calls.signed[0].license;
  assert.match(license.license_id, /^ROAR-PRO-[23456789A-HJ-NP-Z]{8}$/);
  assert.equal(license.env, undefined);          // never a dev licence
  // verification saw the RAW body string, not a re-serialization
  assert.equal(calls.verify[0], JSON.stringify(event()));
});

test("missing paypal headers: 400 with ZERO outbound calls", async () => {
  const res = fakeRes();
  await makeHandler(deps())(reqFor(event(), { headers: {} }), res);
  assert.equal(res.statusCode, 400);
  assert.equal(calls.verify.length, 0);
  assert.equal(calls.claimed.length, 0);
});

test("unverified webhook: 400, nothing happens", async () => {
  const d = deps({ verifyWebhook: async () => false });
  const res = fakeRes();
  await makeHandler(d)(reqFor(event()), res);
  assert.equal(res.statusCode, 400);
  assert.equal(calls.claimed.length, 0);
});

test("wrong amount / currency / event type: ignored, no claim", async () => {
  for (const body of [
    event({ resource: { amount: { value: "18.99", currency_code: "USD" } } }),
    event({ resource: { amount: { value: "19.00", currency_code: "EUR" } } }),
    event({ event_type: "PAYMENT.CAPTURE.REFUNDED" }),
  ]) {
    const res = fakeRes();
    await makeHandler(deps())(reqFor(body), res);
    assert.equal(res.statusCode, 200);
    assert.match(res.body, /ignored/);
    assert.equal(calls.claimed.length, 0);
  }
});

test("payee mismatch: ignored — a payment to someone else mints nothing", async () => {
  const res = fakeRes();
  await makeHandler(deps())(reqFor(event({
    resource: { payee: { merchant_id: "SOMEONE-ELSE" } } })), res);
  assert.match(res.body, /not our merchant/);
  assert.equal(calls.claimed.length, 0);
});

test("duplicate capture (done): 200, no second licence", async () => {
  const d = deps();
  d.store.claim = async () => ({ state: "done" });
  const res = fakeRes();
  await makeHandler(d)(reqFor(event()), res);
  assert.match(res.body, /already/);
  assert.equal(calls.emails.length, 0);
});

test("concurrent claim (in-progress): 200 back-off, no second licence", async () => {
  const d = deps();
  d.store.claim = async () => ({ state: "in-progress" });
  const res = fakeRes();
  await makeHandler(d)(reqFor(event()), res);
  assert.match(res.body, /in progress/);
  assert.equal(calls.emails.length, 0);
});

test("store error on claim: fail CLOSED with 500, nothing minted", async () => {
  const d = deps();
  d.store.claim = async () => { throw new Error("supabase 401"); };
  const res = fakeRes();
  await makeHandler(d)(reqFor(event()), res);
  assert.equal(res.statusCode, 500);
  assert.equal(calls.emails.length, 0);
  assert.equal(calls.signed.length, 0);
});

test("resume: stored licence is re-emailed, NEVER re-signed", async () => {
  const d = deps();
  const stored = { license_id: "ROAR-PRO-STORED234", edition: "pro",
                   signature: "sig" };
  d.store.claim = async () => ({ state: "resume", license: stored,
                                 buyerEmail: "buyer@example.com",
                                 buyerName: "Ada" });
  const res = fakeRes();
  await makeHandler(d)(reqFor(event()), res);
  assert.equal(res.body, "issued");
  assert.equal(calls.signed.length, 0);            // no new signature
  assert.equal(calls.emails[0].license.license_id, "ROAR-PRO-STORED234");
  assert.deepEqual(calls.issued, ["CAP-123"]);
});

test("email failure: failed row + owner alert + 500 for retry", async () => {
  const d = deps();
  d.email.sendLicense = async () => { throw new Error("resend down"); };
  const res = fakeRes();
  await makeHandler(d)(reqFor(event()), res);
  assert.equal(res.statusCode, 500);
  assert.equal(calls.failed.length, 1);
  assert.equal(calls.alerts.length, 1);
  assert.equal(calls.issued.length, 0);
  assert.equal(calls.signed.length, 1);            // licence persisted for resume
});

test("no order id / no payer email: failed + alert, no silent licence", async () => {
  const res1 = fakeRes();
  await makeHandler(deps())(reqFor(event({
    resource: { supplementary_data: {} } })), res1);
  assert.equal(res1.statusCode, 500);
  assert.equal(calls.emails.length, 0);

  const d = deps({ getOrderPayer: async () => ({ email: null, name: "" }) });
  const res2 = fakeRes();
  await makeHandler(d)(reqFor(event()), res2);
  assert.equal(res2.statusCode, 500);
  assert.equal(calls.emails.length, 0);
});

test("sandbox never signs with the production key", () => {
  const env = { PAYPAL_API_BASE: "https://api-m.sandbox.paypal.com",
                FULFILLMENT_PRIVATE_KEY_PEM: "PROD",
                FULFILLMENT_SANDBOX_PRIVATE_KEY_PEM: "SANDBOX" };
  assert.equal(signingKeyFor(env), "SANDBOX");
  assert.equal(signingKeyFor({ ...env, PAYPAL_API_BASE: LIVE }), "PROD");
});

test("sandbox with no sandbox key configured: 500, nothing signed", async () => {
  const d = deps();
  d.env = { ...d.env, PAYPAL_API_BASE: "https://api-m.sandbox.paypal.com",
            FULFILLMENT_SANDBOX_PRIVATE_KEY_PEM: undefined };
  const res = fakeRes();
  await makeHandler(d)(reqFor(event()), res);
  assert.equal(res.statusCode, 500);
  assert.equal(calls.claimed.length, 0);
  assert.equal(calls.signed.length, 0);
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
