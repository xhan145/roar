// PayPal REST helpers: OAuth token + webhook signature verification.
// The verification call is the trust anchor — a webhook body is meaningless
// until PayPal itself confirms the transmission.

async function accessToken(env) {
  const basic = Buffer.from(
    `${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_SECRET}`).toString("base64");
  const r = await fetch(`${env.PAYPAL_API_BASE}/v1/oauth2/token`, {
    method: "POST",
    headers: { Authorization: `Basic ${basic}`,
               "Content-Type": "application/x-www-form-urlencoded" },
    body: "grant_type=client_credentials",
  });
  if (!r.ok) throw new Error(`paypal token: HTTP ${r.status}`);
  return (await r.json()).access_token;
}

export function verifyWebhookFactory(env) {
  return async function verifyWebhook(headers, event) {
    try {
      const token = await accessToken(env);
      const r = await fetch(
        `${env.PAYPAL_API_BASE}/v1/notifications/verify-webhook-signature`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`,
                     "Content-Type": "application/json" },
          body: JSON.stringify({
            auth_algo: headers["paypal-auth-algo"],
            cert_url: headers["paypal-cert-url"],
            transmission_id: headers["paypal-transmission-id"],
            transmission_sig: headers["paypal-transmission-sig"],
            transmission_time: headers["paypal-transmission-time"],
            webhook_id: env.PAYPAL_WEBHOOK_ID,
            webhook_event: event,
          }),
        });
      if (!r.ok) return false;
      return (await r.json()).verification_status === "SUCCESS";
    } catch {
      return false;                         // fail closed, always
    }
  };
}
