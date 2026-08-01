// PayPal → licence fulfilment. The ONLY entry point of this service.
//
// Trust chain, in order, all mandatory:
//   0. Cheap pre-filter: all paypal-transmission-* headers must be present
//      before ANY outbound call — floods cost us nothing.
//   1. PayPal webhook signature verification over the RAW body bytes.
//   2. Event validation: PAYMENT.CAPTURE.COMPLETED, COMPLETED, USD, an amount
//      mapping EXACTLY to an edition, and (when configured) OUR merchant id.
//   3. Atomic idempotent claim (see lib/supabase.js) — one capture id can
//      never mint twice, crashes resume with the SAME licence.
//   4. Buyer identity from the ORDER (payer isn't on the capture), sign with
//      the environment-bound key, persist the licence, THEN email, then mark
//      issued.
//
// Sandbox never touches the production key: the signing key is selected by
// PAYPAL_API_BASE, so play money can only mint licences the shipped app does
// not trust.
import { createHash } from "node:crypto";
import { issueLicense } from "../lib/sign.js";

export const config = { api: { bodyParser: false } };   // raw bytes required

export const AMOUNT_TO_EDITION = {
  "19.00": "pro",
  "29.00": "developer",
  "49.00": "supporter",
};

const LIVE_API = "https://api-m.paypal.com";

export function signingKeyFor(env) {
  if (env.PAYPAL_API_BASE === LIVE_API) {
    return env.FULFILLMENT_PRIVATE_KEY_PEM;
  }
  // sandbox/testing: a throwaway key whose public half is NOT in the app
  return env.FULFILLMENT_SANDBOX_PRIVATE_KEY_PEM;
}

const REQUIRED_HEADERS = ["paypal-auth-algo", "paypal-cert-url",
  "paypal-transmission-id", "paypal-transmission-sig",
  "paypal-transmission-time"];

async function readRawBody(req) {
  if (typeof req.rawBody === "string") return req.rawBody;      // tests
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf-8");
}

export function makeHandler(deps) {
  const { verifyWebhook, getOrderPayer, store, email, log, env } = deps;

  return async function handler(req, res) {
    if (req.method !== "POST") {
      res.statusCode = 405;
      return res.end("method not allowed");
    }
    // 0. Pre-filter before any outbound call.
    for (const h of REQUIRED_HEADERS) {
      if (!req.headers?.[h]) {
        res.statusCode = 400;
        return res.end("missing paypal headers");
      }
    }
    const rawBody = await readRawBody(req);
    let event;
    try {
      event = JSON.parse(rawBody);
    } catch {
      res.statusCode = 400;
      return res.end("bad json");
    }
    if (!event || typeof event !== "object") {
      res.statusCode = 400;
      return res.end("bad body");
    }

    // 1. Signature over the raw bytes — never act on an unverified body.
    if (!(await verifyWebhook(req.headers, rawBody))) {
      log("webhook: signature verification FAILED");
      res.statusCode = 400;
      return res.end("unverified");
    }

    // 2. Only completed USD captures at an exact edition price, for us.
    if (event.event_type !== "PAYMENT.CAPTURE.COMPLETED") {
      res.statusCode = 200;
      return res.end("ignored: event type");
    }
    const capture = event.resource || {};
    const amount = capture.amount || {};
    const edition = AMOUNT_TO_EDITION[amount.value];
    if (capture.status !== "COMPLETED" || amount.currency_code !== "USD"
        || !edition || !capture.id) {
      log(`webhook: ignored capture ${capture.id || "?"} `
          + `(${amount.value} ${amount.currency_code}, ${capture.status})`);
      res.statusCode = 200;
      return res.end("ignored: not an edition purchase");
    }
    if (env.PAYPAL_MERCHANT_ID
        && capture.payee?.merchant_id !== env.PAYPAL_MERCHANT_ID) {
      log(`webhook: ignored capture ${capture.id} — payee mismatch`);
      res.statusCode = 200;
      return res.end("ignored: not our merchant");
    }
    const signingKey = signingKeyFor(env);
    if (!signingKey) {
      log("webhook: NO SIGNING KEY for this environment — refusing");
      res.statusCode = 500;
      return res.end("misconfigured");
    }

    // 3. Atomic claim / resume.
    let claim;
    try {
      claim = await store.claim(capture.id, { edition });
    } catch (err) {
      log(`webhook: claim failed CLOSED for ${capture.id}: ${err}`);
      res.statusCode = 500;                  // never guess — let PayPal retry
      return res.end("store unavailable");
    }
    if (claim.state === "done") {
      res.statusCode = 200;
      return res.end("already fulfilled");
    }
    if (claim.state === "in-progress") {
      res.statusCode = 200;
      return res.end("in progress");
    }

    try {
      let license, buyerEmail, buyerName;
      if (claim.state === "resume") {
        // A previous run signed and persisted but may not have emailed:
        // reuse the SAME licence. Never sign twice for one capture.
        ({ license, buyerEmail, buyerName } = claim);
      } else {
        // 4. Buyer identity lives on the ORDER, not the capture.
        const orderId =
          capture.supplementary_data?.related_ids?.order_id || null;
        if (!orderId) throw new Error("capture carries no order id");
        const payer = await getOrderPayer(orderId);
        buyerEmail = payer.email;
        buyerName = payer.name;
        if (!buyerEmail) throw new Error("order has no payer email");
        const emailHash = createHash("sha256")
          .update(buyerEmail.trim().toLowerCase()).digest("hex");
        license = issueLicense({ edition, name: buyerName, emailHash,
                                 privateKeyPem: signingKey });
        await store.markSigned(capture.id,
                               { edition, buyerEmail, buyerName, license });
      }
      await email.sendLicense({
        to: buyerEmail, bcc: env.OWNER_EMAIL, edition, license,
        buyerName, captureId: capture.id,
      });
      await store.markIssued(capture.id);
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
  const [paypal, { storeFactory }, { emailFactory }] = await Promise.all([
    import("../lib/paypal.js"),
    import("../lib/supabase.js"),
    import("../lib/email.js"),
  ]);
  const env = process.env;
  const handler = makeHandler({
    verifyWebhook: paypal.verifyWebhookFactory(env),
    getOrderPayer: paypal.orderPayerFactory(env),
    store: storeFactory(env),
    email: emailFactory(env),
    log: console.log,
    env,
  });
  return handler(req, res);
}
