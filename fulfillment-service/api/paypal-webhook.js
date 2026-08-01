// PayPal → licence fulfilment. The ONLY entry point of this service.
//
// Trust chain, in order, all mandatory:
//   1. PayPal webhook signature verification (verify-webhook-signature API) —
//      the request body is untrusted until PayPal confirms it.
//   2. Event/amount validation — only PAYMENT.CAPTURE.COMPLETED with an amount
//      that maps EXACTLY to an edition mints anything.
//   3. Idempotency — the capture id is claimed in the store BEFORE signing;
//      one sale can never produce two licences, even across PayPal retries.
//   4. Sign with the SUBORDINATE fulfilment key, email via Resend, record.
//
// Failures after the claim mark the row "failed" and return 500 so PayPal
// retries; a retry may complete a failed row but never re-issue an issued one.
import { createHash } from "node:crypto";
import { issueLicense } from "../lib/sign.js";

export const AMOUNT_TO_EDITION = {
  "19.00": "pro",
  "29.00": "developer",
  "49.00": "supporter",
};

export function makeHandler(deps) {
  const { verifyWebhook, store, email, log, env } = deps;

  return async function handler(req, res) {
    if (req.method !== "POST") {
      res.statusCode = 405;
      return res.end("method not allowed");
    }
    let event = req.body;
    try {
      if (typeof event === "string") event = JSON.parse(event);
    } catch {
      res.statusCode = 400;
      return res.end("bad json");
    }
    if (!event || typeof event !== "object") {
      res.statusCode = 400;
      return res.end("bad body");
    }

    // 1. Signature — never act on an unverified body.
    const verified = await verifyWebhook(req.headers, event);
    if (!verified) {
      log("webhook: signature verification FAILED");
      res.statusCode = 400;
      return res.end("unverified");
    }

    // 2. Only completed captures with an exact edition amount.
    if (event.event_type !== "PAYMENT.CAPTURE.COMPLETED") {
      res.statusCode = 200;
      return res.end("ignored: event type");
    }
    const capture = event.resource || {};
    const amount = capture.amount || {};
    const edition = AMOUNT_TO_EDITION[amount.value];
    if (capture.status !== "COMPLETED" || amount.currency_code !== "USD"
        || !edition) {
      log(`webhook: ignored capture ${capture.id} `
          + `(${amount.value} ${amount.currency_code}, ${capture.status})`);
      res.statusCode = 200;
      return res.end("ignored: not an edition purchase");
    }
    if (!capture.id) {
      res.statusCode = 400;
      return res.end("no capture id");
    }

    // Buyer identity comes from the verified event only.
    const payer = event.resource?.payer
      || event.resource?.supplementary_data?.payer || {};
    const buyerEmail = payer.email_address
      || capture.payee_email || capture.payer_email || null;
    const buyerName = [payer.name?.given_name, payer.name?.surname]
      .filter(Boolean).join(" ");

    // 3. Claim the capture id BEFORE signing (idempotency).
    const claim = await store.claim(capture.id, { edition });
    if (claim === "already-issued") {
      log(`webhook: capture ${capture.id} already fulfilled`);
      res.statusCode = 200;
      return res.end("already fulfilled");
    }

    try {
      // 4. Sign + deliver.
      const emailHash = buyerEmail
        ? createHash("sha256").update(buyerEmail.trim().toLowerCase())
            .digest("hex")
        : null;
      const license = issueLicense({
        edition, name: buyerName, emailHash,
        privateKeyPem: env.FULFILLMENT_PRIVATE_KEY_PEM,
      });
      if (!buyerEmail) {
        throw new Error("no buyer email on verified capture");
      }
      await email.sendLicense({
        to: buyerEmail, bcc: env.OWNER_EMAIL, edition, license,
        buyerName, captureId: capture.id,
      });
      await store.markIssued(capture.id, {
        edition, buyerEmail, buyerName, license,
      });
      log(`webhook: issued ${license.license_id} for capture ${capture.id}`);
      res.statusCode = 200;
      return res.end("issued");
    } catch (err) {
      log(`webhook: FULFILMENT FAILED for capture ${capture.id}: ${err}`);
      try {
        await store.markFailed(capture.id, String(err));
        await email.alertOwner({
          to: env.OWNER_EMAIL, captureId: capture.id, error: String(err),
        });
      } catch { /* alerting must not mask the retryable 500 */ }
      res.statusCode = 500;               // PayPal retries; claim keeps it safe
      return res.end("fulfilment failed");
    }
  };
}

// Vercel entry point with real dependencies.
export default async function (req, res) {
  const [{ verifyWebhookFactory }, { storeFactory }, { emailFactory }] =
    await Promise.all([
      import("../lib/paypal.js"),
      import("../lib/supabase.js"),
      import("../lib/email.js"),
    ]);
  const env = process.env;
  const handler = makeHandler({
    verifyWebhook: verifyWebhookFactory(env),
    store: storeFactory(env),
    email: emailFactory(env),
    log: console.log,
    env,
  });
  return handler(req, res);
}
