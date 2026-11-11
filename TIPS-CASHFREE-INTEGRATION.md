# UPI tip page + Tips by amount: integration and go-live notes

Status on 2026-11-12: **code built, tested offline, pushed. Not deployed, not released.** It's waiting on Cashfree.

Commits on `main`:
- `fed67ba`: UPI tip page and QR through Cashfree Easy Split; old gateway setup tab removed.
- `914e52c`: Tips by amount (alert design steps).

---

## 1. What we decided, and why

| Decision | Choice | Why |
|---|---|---|
| How streamers get tips | ZunimiLabs' own tip page + QR per streamer. Viewer enters name, message and amount, pays by UPI. The streamer only adds a receiving account (UPI ID or bank + IFSC) and PAN. | Razorpay/Stripe/Cashfree webhook setups were too hard for streamers. Google Pay, Paytm and PhonePe merchant QR accounts have no alert API. |
| Who holds the money | **Cashfree Easy Split**: streamers are Cashfree "vendors", and Cashfree settles their share straight to them. | Collecting into ZunimiLabs' own bank and paying out later is payment aggregation, which needs an RBI licence. Money must sit with a licensed aggregator. |
| Why not Dodo | Not used for tips. | Dodo's Merchant Acceptance Policy restricts marketplaces and forwarding funds. Risking that account would endanger Clip Studio Premium sales. Dodo stays for selling our own apps only. |
| Commission | **2% to ZunimiLabs**, 98% to the streamer. Cashfree's own fee can also be taken from the streamer's share (`TIP_GATEWAY_FEE_PCT`). | For comparison: YouTube Super Chat 30%, StreamTipz 5% (or ₹2 per tip), Streamlabs, StreamElements and Ko-fi 0% plus processor fees, Stream Alert 0% plus ₹249 a month. |
| Payout schedule | `schedule_option: 2` = T+2 (two working days). | The user asked for "every 3–4 days". The documented options are T+1, T+2, weekly, monthly and instant. |
| International viewers | **Postponed** by the user. | The proposal was Ko-fi: card and PayPal, paid to the streamer's PayPal, with a webhook into ChatDoom. Cross-border payments through Cashfree with split payouts are unlikely to be approved. |
| Old gateway tab | Removed from the app, at the user's request. | The cloud `/hook/<gateway>/<id>` endpoints still work for anyone who already connected one. |

## 2. What the user must do (open items)

**Cashfree ticket** (the user raised it on 2026-11-12). It must cover:
1. **Rename the business** "SimpleSolve" to **ZunimiLabs**. Viewers see this name on the checkout, so it matters. Also check for a separate brand/display name in Settings.
2. **Enable Easy Split** for "a tip page for live streamers; streamers are added as vendors and paid by Cashfree".
3. **A direct UPI QR that Google Pay and PhonePe can scan, with Easy Split still working.** Ask for either:
   - **S2S UPI QR** (Order Pay, `payment_method.upi.channel = "qrcode"`). The docs say this needs the S2S flag plus a GST return showing turnover above ₹1 crore for non-card modes. Ask whether they can enable it anyway.
   - **A virtual UPI ID / static QR per vendor** that works with Easy Split. This would be a fixed QR; payments carry the payer's UPI name but no message.

**Also:**
4. **Ask a CA** about GST on the 2% commission, and TCS/TDS as an e-commerce operator.
5. **Send the sandbox keys:** Cashfree dashboard → Developers → API keys, in **Test** mode: Client ID and Client Secret.

## 3. Go-live checklist (for Claude, after the steps above)

1. Store the secrets:
   ```
   cd ChatDoom/cloud
   npx wrangler secret put CASHFREE_CLIENT_ID
   npx wrangler secret put CASHFREE_CLIENT_SECRET
   ```
2. `wrangler.toml` `[vars]` already holds `CASHFREE_ENV = "sandbox"`, `TIP_COMMISSION_PCT = "2"` and `TIP_GATEWAY_FEE_PCT = "0"`. Set the fee once Cashfree states its UPI rate.
3. In Cashfree (Test mode), add the webhook `https://cloud.zunimilabs.online/cashfree/webhook` for **payment success**.
4. `npx wrangler deploy`. Auto mode blocks production deploys, so the user runs it or approves it.
5. **Sandbox end-to-end test.** Check these points against the real sandbox. They were built from the docs and are **unverified**:
   - [ ] Vendor create accepts our body (`kyc_details.account_type "INDIVIDUAL"`, `business_type "Content creator"`, `upi` or `bank`). Sandbox vendors turn ACTIVE in about 10 minutes.
   - [ ] Vendor update uses `PATCH /easy-split/vendors/{id}` with the same body. This is only used when the streamer changes payout details.
   - [ ] An order with `order_splits: [{vendor_id, percentage: 98}]` is accepted with `payment_methods: "upi"`.
   - [ ] `customer_phone` placeholder `9999999999` is accepted when the viewer gives no phone number.
   - [ ] The hosted checkout opens from `Cashfree({mode}).checkout({paymentSessionId, redirectTarget: "_self"})` (SDK `https://sdk.cashfree.com/js/v3/cashfree.js`) and returns to `/t/<slug>/done?order_id=…`.
   - [ ] The webhook's `type` is `PAYMENT_SUCCESS_WEBHOOK` or `PAYMENT_SUCCESS`. The code accepts both by prefix.
   - [ ] The webhook signature is `base64(HMAC_SHA256(timestamp + rawBody, client secret))`, and the timestamp is in seconds. The code accepts seconds or milliseconds, with a 15-minute window.
   - [ ] `cf_payment_id` can arrive as a number or a string. Both are handled.
   - [ ] The split actually settles to the vendor (check in Cashfree's Easy Split reports).
   - [ ] The tip reaches the app and is read aloud: `GET /api/events`, then the app's poller, then the OBS alert.
6. Switch to live: put the live keys in the same secrets, set `CASHFREE_ENV = "production"`, add the live webhook, deploy, and do one real ₹10 tip.
7. **Release ChatDoom** with both features: bump `app/version.py`, `installer.iss` and `version_info.txt`; push a tag (it builds); add notes with `gh release edit`. Update the site's ChatDoom privacy and terms (tip page, Cashfree, 2%, no refunds, data kept), and add a tips section.
8. If Cashfree enables a direct UPI QR, swap the stream QR from "link to the tip page" to a real UPI QR, and keep the page for messages.

## 4. How it works (code map)

### Cloud: `cloud/src/tips.js`
Wired in `cloud/src/index.js`. The shared `addTip()` writes to the existing `tips` table, so every payment is read once.

| Route | Who calls it | What it does |
|---|---|---|
| `GET /api/tips` | app (server key) | The streamer's page and terms (98/2, sandbox flag). Refreshes the vendor status from Cashfree while it isn't ACTIVE yet. |
| `POST /api/tips/setup` | app | Validates and creates (or PATCHes) the Cashfree vendor, then stores the page. **PAN and account numbers are not stored**; only a masked payout label is kept. |
| `PUT /api/tips` | app | Pause or resume, and the smallest tip (₹10 or more). |
| `GET /t/<slug>` | viewer | The tip page: name, message (200 characters), amount buttons. Shows the 2% note and a Test-mode badge in the sandbox. |
| `GET /t/<slug>/qr.svg` | OBS, app | QR code of the page link (vendored `src/vendor/qrcode.js`, qrcode-generator 1.4.4, MIT). |
| `POST /t/<slug>/order` | tip page | Creates the Cashfree order (UPI only, 30-minute expiry, split to the vendor). Rate limit: 6 per minute per IP. |
| `GET /t/<slug>/done` and `/status/<order>` | viewer's browser | Asks Cashfree for the payment status and records the tip if it was paid. This is the backup if the webhook is missed. |
| `POST /cashfree/webhook` | Cashfree | Checks the signature, timestamp and amount, then records the tip once. |

**D1 tables:**
- `tip_pages`: slug, guild, vendor_id, name, status, remarks, payout (masked), min_amount, enabled, created.
- `tip_orders`: order_id, guild, slug, name, message, amount, status, created. Unpaid orders are deleted after 7 days.

**Page names:** 3–30 characters (a–z, 0–9, dashes), with reserved words blocked. Vendor ID is `cd_<discord guild id>`.

### App
- **`app/payments_page.py`:** tabs **UPI tip page** (setup form, status, link, QR, copy QR link for OBS, pause), **Read aloud**, and **Other tip link**. After a successful save, the payout fields are cleared, so a later rename doesn't resend them.
- **`app/ui.py`:**
  - `on_tip` sets `Message.rupees` for INR tips.
  - The paid-message alert sends `value` to the overlay.
  - The stats tile shows the tip page state.
  - The overlay config gets `tipTiers`.
- **Tips by amount:**
  - `app/alert_styles.py` holds the tier logic: `tip_tiers`, `tier_design`, `tier_index`, `add_tier`, `set_tier`, `remove_tier`, `overlay_tip_tiers`, `MAX_TIERS = 5`, and presets that get bigger at each step.
  - The setting is `ov_tip_tiers: [{from, design}]`.
  - `app/overlay_html.py` `designFor(cat, e)` picks the highest step at or below `e.value`, for tips only. A step's own sound beats the Tips sound.
  - `app/alerts_page.py` has the "Tips by amount" tab, and steps appear in the Editing list as `tier:<from>`.

## 5. Tests

| Test | Command | Status |
|---|---|---|
| Cloud tip flow (fake Cashfree, 36 checks) | `cd cloud && node test-tips.mjs` | all pass |
| App (Qt, offscreen) | `set PYTHONIOENCODING=utf-8 & set QT_QPA_PLATFORM=offscreen & set PYTHONPATH=. & python tests\test_app.py` | all pass |
| Overlay | `python tests\make_overlay_pages.py`, then `node tests\overlay_page.test.cjs` | all pass |

- **Overlay test:** needs `jsdom`, which isn't in the repo. Install it somewhere else and point `NODE_PATH` at its `node_modules`.
- **Known, unrelated:** `cloud/test.mjs` has 4 failing `/api/grant` role tests. They predate this work and come from the 1.4.4 YouTube no-rewards rule. Fix them separately.

## 6. Later ideas (not built)
- **International tips through Ko-fi.** The streamer pastes ChatDoom's webhook into Ko-fi and Ko-fi's verification token into ChatDoom. Add an "Outside India? Tip by card or PayPal" button on the tip page. Convert foreign amounts to rupees so they land in the right step.
- **A streamer earnings view.** Tips list and payouts, from Cashfree's Easy Split APIs.
- **Tip page themes**, and the streamer's own banner and avatar on the page.
