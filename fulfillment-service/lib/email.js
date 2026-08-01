// Buyer + owner email via Resend (plain REST). The licence travels as a JSON
// attachment; the body repeats the activation steps from the site FAQ.

async function send(env, message) {
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`,
               "Content-Type": "application/json" },
    body: JSON.stringify(message),
  });
  if (!r.ok) {
    throw new Error(`resend: HTTP ${r.status} ${await r.text()}`);
  }
}

const EDITION_NAMES = {
  pro: "ROAR Pro", developer: "ROAR Developer", supporter: "ROAR Supporter",
};

export function emailFactory(env) {
  return {
    async sendLicense({ to, bcc, edition, license, buyerName, captureId }) {
      const name = EDITION_NAMES[edition] || edition;
      await send(env, {
        from: env.FULFILLMENT_FROM,
        to: [to],
        bcc: bcc ? [bcc] : undefined,
        subject: `Your ${name} license`,
        text:
`Hi${buyerName ? " " + buyerName : ""},

Thanks for buying ${name}. Your license file is attached.

To activate:
  1. Open ROAR from the tray and go to Settings -> License.
  2. Choose the attached file (${`roar-license-${edition}.json`}).
  3. Done - it's verified on your own device. No account, no internet needed.

Keep the file with your backups; re-importing it restores your edition any
time. Reply to this email if anything doesn't work.

- ROAR
(PayPal transaction ${captureId})
`,
        attachments: [{
          filename: `roar-license-${edition}.json`,
          content: Buffer.from(JSON.stringify(license, null, 2))
            .toString("base64"),
        }],
      });
    },

    async alertOwner({ to, captureId, error }) {
      await send(env, {
        from: env.FULFILLMENT_FROM,
        to: [to],
        subject: `ROAR fulfilment FAILED: ${captureId}`,
        text: `Automatic fulfilment failed and will be retried by PayPal.\n\n`
          + `Capture: ${captureId}\nError: ${error}\n\n`
          + `If retries keep failing, issue manually with scripts/issue_license.py `
          + `after verifying the payment in the PayPal dashboard.`,
      });
    },
  };
}
