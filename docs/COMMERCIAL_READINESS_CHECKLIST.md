# Commercial Readiness Checklist

Do not tag a paid release or take payment until every box is checked.

## Company & ownership
- [ ] Entity formed (LLC vs C-Corp decided with CPA/attorney)
- [ ] Founder agreement signed
- [ ] IP assigned to the company
- [ ] Repository under company control
- [ ] Domain under company control

## Commerce
- [ ] Payment processor configured (see [CHECKOUT_SETUP.md](CHECKOUT_SETUP.md))
- [ ] Support email configured (replace `support@example.com`)
- [ ] Purchase URLs set in `commercial_config.py` (replace `example.com` placeholders)

## Licensing
- [ ] Production Ed25519 keypair generated; **private key in a secret manager**
- [ ] Public key swapped into `commercial_config.LICENSE_PUBLIC_KEY_PEM`
- [ ] `commercial_config.IS_PRODUCTION = True` in the release build
- [ ] License generation process tested end-to-end
- [ ] License validation tested **offline**
- [ ] Dev-signed licenses confirmed **rejected** by the production build

## Product & docs
- [ ] Installer tested (fresh install / upgrade / uninstall / reinstall)
- [ ] Core works with no license
- [ ] Privacy controls + delete history/audio confirmed free
- [ ] Pricing page reviewed
- [ ] Privacy promise reviewed
- [ ] Refund policy reviewed (with counsel)

## Release
- [ ] Full test suite green
- [ ] `docs/RELEASE_TEST_PLAN.md` manual matrix completed
- [ ] Release candidate signed and tagged
