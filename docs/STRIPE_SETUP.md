# Selling ROAR with Stripe Payment Links

ROAR's site is **static** (GitHub Pages), so there is no server to create
Checkout Sessions and nothing to receive a webhook. Payment Links are the right
fit: Stripe hosts the payment page, and the amount is fixed on Stripe's side, so
a visitor cannot tamper with the price even though the link is public.

## 1. Create three one-time prices

In the Stripe Dashboard create three products, each with a **one-time** price
(never recurring — ROAR is not a subscription):

| Product          | Price |
|------------------|------:|
| ROAR Pro         |   $19 |
| ROAR Developer   |   $29 |
| ROAR Supporter   |   $49 |

These must match `PRICING` in `commercial_config.py`. That dict is the single
source of truth for what ROAR costs; Stripe is just where the money moves.

## 2. Create a Payment Link per product

For each product, create a Payment Link. Under "After payment", set a redirect
to:

    https://xhan145.github.io/roar/purchase/success.html

Collect the buyer's email — you need it to send the licence.

## 3. Put the links in the site

Paste each link into the `purchase` block near the bottom of `site/index.html`:

```js
purchase: {
  pro: "https://buy.stripe.com/…",
  developer: "https://buy.stripe.com/…",
  supporter: "https://buy.stripe.com/…",
},
```

Commit and push; GitHub Pages redeploys from `site/`. Any edition left as `""`
keeps the pre-order email fallback, so you can turn checkout on one tier at a
time.

Payment Links are **public URLs and are safe to commit**. A Stripe *secret key*
or *webhook secret* is never safe to commit — and this setup does not need one.

## 4. Fulfil the licence

> **Stripe payment completion must not automatically imply that a license was
> delivered.** Delivery only counts once you have issued the licence and sent
> it. The success page says the licence "will be delivered" for exactly this
> reason — never edit it to claim one was emailed.

Fulfilment is manual and deliberately so: the Ed25519 signing key lives only on
the owner's machine (`~/.roar-signing/`), never on a server and never in this
repository.

1. Stripe notifies you that a payment succeeded.
2. Confirm it in the Stripe Dashboard. Never trust a redirect or a URL
   parameter as proof of payment.
3. Sign the licence offline:

   ```bash
   export ROAR_LICENSE_PRIVATE_KEY_FILE=~/.roar-signing/roar_license_private_key.pem
   python scripts/issue_license.py --edition pro --name "Buyer Name" --email buyer@example.com
   ```

4. Email the resulting `.json` to the buyer. They import it under
   Settings → License; verification happens on their own device.
5. Record the Stripe payment id you fulfilled, so a duplicate notification
   cannot produce a second licence for one sale.

`fulfillment.py` marks where an automated version of step 3 would live. It
validates a request and then refuses, on purpose — see
`docs/WEBSITE_IMPLEMENTATION.md` for what a real implementation would have to
do first.

## 5. Test before charging anyone

Use Stripe **test mode** first: complete a purchase, cancel one, and repeat a
purchase to see what a double-buy looks like. Keep test and live links
separate — never paste a test link into the live site.

## Refunds

Refund in Stripe. A refunded licence stays technically valid, because validation
is offline and there is nothing to phone home to. That makes refunds a trust
matter rather than a technical one: record them alongside the issued-licence
log. See `docs/REFUND_POLICY.md`.

## What we deliberately do not do

- No account, no login, no customer portal.
- No telemetry, and no purchase data inside the app.
- No licence key in the browser, and no signing key on any server.
- No subscription, and no recurring price in Stripe.
