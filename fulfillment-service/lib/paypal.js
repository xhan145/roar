// PayPal REST helpers: cached OAuth token, webhook signature verification
// over the RAW transmitted bytes, and order→payer lookup.
//
// Verification detail that matters: PayPal's transmission signature covers a
// CRC32 of the exact bytes it sent. Re-serializing a parsed body can change
// those bytes, so the verify request embeds the raw body string VERBATIM via
// string splicing — never JSON.stringify(parsedEvent).

let cachedToken = null;   // { value, expiresAt } — module-scoped per instance

export async function accessToken(env, fetchImpl = fetch) {
  if (cachedToken && Date.now() < cachedToken.expiresAt - 60_000) {
    return cachedToken.value;
  }
  const basic = Buffer.from(
    `${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_SECRET}`).toString("base64");
  const r = await fetchImpl(`${env.PAYPAL_API_BASE}/v1/oauth2/token`, {
    method: "POST",
    headers: { Authorization: `Basic ${basic}`,
               "Content-Type": "application/x-www-form-urlencoded" },
    body: "grant_type=client_credentials",
  });
  if (!r.ok) throw new Error(`paypal token: HTTP ${r.status}`);
  const data = await r.json();
  cachedToken = { value: data.access_token,
                  expiresAt: Date.now() + (data.expires_in || 300) * 1000 };
  return cachedToken.value;
}

export function _resetTokenCache() { cachedToken = null; }

export function verifyWebhookFactory(env, fetchImpl = fetch) {
  // rawBody: the exact request-body STRING as received.
  return async function verifyWebhook(headers, rawBody) {
    try {
      const token = await accessToken(env, fetchImpl);
      const meta = JSON.stringify({
        auth_algo: headers["paypal-auth-algo"],
        cert_url: headers["paypal-cert-url"],
        transmission_id: headers["paypal-transmission-id"],
        transmission_sig: headers["paypal-transmission-sig"],
        transmission_time: headers["paypal-transmission-time"],
        webhook_id: env.PAYPAL_WEBHOOK_ID,
      });
      // splice the raw bytes in verbatim
      const body = meta.slice(0, -1) + ',"webhook_event":' + rawBody + "}";
      const r = await fetchImpl(
        `${env.PAYPAL_API_BASE}/v1/notifications/verify-webhook-signature`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`,
                     "Content-Type": "application/json" },
          body,
        });
      if (!r.ok) return false;
      return (await r.json()).verification_status === "SUCCESS";
    } catch {
      return false;                         // fail closed, always
    }
  };
}

// The capture event does NOT carry the buyer: payer identity lives on the
// ORDER (resource.supplementary_data.related_ids.order_id).
export function orderPayerFactory(env, fetchImpl = fetch) {
  return async function getOrderPayer(orderId) {
    const token = await accessToken(env, fetchImpl);
    const r = await fetchImpl(
      `${env.PAYPAL_API_BASE}/v2/checkout/orders/${encodeURIComponent(orderId)}`,
      { headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok) throw new Error(`paypal order lookup: HTTP ${r.status}`);
    const order = await r.json();
    const payer = order.payer || {};
    return {
      email: payer.email_address || null,
      name: [payer.name?.given_name, payer.name?.surname]
        .filter(Boolean).join(" "),
    };
  };
}
