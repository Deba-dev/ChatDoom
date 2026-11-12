// Offline test of the ZunimiLabs tip page: setup, the page, orders with the split, the webhook and status checks.
// A real SQLite database, a fake KV, and a fake Cashfree. Run: node test-tips.mjs
import worker from "./src/index.js";
import { validSetup } from "./src/tips.js";
import { fakeEnv } from "./test-studio.mjs";

let fails = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };

const SECRET = "cf-secret";
const env = Object.assign(fakeEnv(), { DISCORD_CLIENT_ID: "d", DISCORD_CLIENT_SECRET: "d", DISCORD_BOT_TOKEN: "d",
  CASHFREE_CLIENT_ID: "cf-id", CASHFREE_CLIENT_SECRET: SECRET });
await env.KV.put("token:appkey", JSON.stringify("123456789012345678"));
await env.KV.put("guild:123456789012345678", JSON.stringify({ guildName: "DRXSHI", config: {} }));

// Fake Cashfree
const cf = { calls: [], vendorStatus: "IN_BENE_CREATION", payments: {}, refuseVendor: false };
globalThis.fetch = async (u, o = {}) => {
  const url = new URL(String(u)), body = o.body ? JSON.parse(o.body) : null;
  cf.calls.push({ method: o.method, path: url.pathname, body, headers: o.headers });
  const reply = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
  if (o.headers["x-client-secret"] !== SECRET || o.headers["x-api-version"] !== "2026-01-01") return reply({ message: "auth" }, 401);
  if (url.pathname === "/pg/easy-split/vendors" && o.method === "POST")
    return cf.refuseVendor ? reply({ message: "invalid pan" }, 400) : reply({ ...body, status: cf.vendorStatus });
  if (url.pathname.startsWith("/pg/easy-split/vendors/")) return reply({ status: cf.vendorStatus, remarks: "" });
  if (url.pathname === "/pg/orders" && o.method === "POST") return reply({ order_id: body.order_id, payment_session_id: "session_" + body.order_id, order_status: "ACTIVE" });
  const m = url.pathname.match(/^\/pg\/orders\/([^/]+)\/payments$/);
  if (m) return reply(cf.payments[m[1]] || []);
  return reply({ message: "unexpected " + url.pathname }, 404);
};

const BASE = "https://cloud.zunimilabs.online";
const call = async (method, path, { body, key = "appkey", headers = {}, raw } = {}) => {
  const h = { ...headers };
  if (key) h.authorization = "Bearer " + key;
  if (body !== undefined || raw !== undefined) h["content-type"] = "application/json";
  const res = await worker.fetch(new Request(BASE + path, { method, headers: h, body: raw ?? (body === undefined ? undefined : JSON.stringify(body)) }), env);
  const type = res.headers.get("content-type") || "";
  return { status: res.status, type, data: type.includes("json") ? await res.json() : await res.text() };
};
const sign = async (ts, raw) => {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(ts + raw)))));
};
const tips = async () => (await call("GET", "/api/events?after=0")).data.events;

// ---- validation
const good = { slug: "drxshi", name: "DRXSHI", holder: "Debarshi Parasar", email: "a@b.in", phone: "+91 98765 43210", pan: "abcde1234f", vpa: "drxshi@okicici" };
ok(!validSetup(good, true).error && validSetup(good, true).phone === "9876543210" && validSetup(good, true).pan === "ABCDE1234F", "good details pass, phone and PAN are tidied");
ok(validSetup({ ...good, slug: "admin" }, true).error && validSetup({ ...good, slug: "a b" }, true).error, "reserved or bad page names are refused");
ok(validSetup({ ...good, pan: "123" }, true).error, "a bad PAN is refused");
ok(validSetup({ ...good, vpa: "", account: "1234", ifsc: "HDFC0001234" }, true).error, "a bank account needs a real number");
ok(!validSetup({ ...good, vpa: "", account: "123456789012", ifsc: "hdfc0001234" }, true).error, "a bank account with IFSC works instead of UPI");
ok(!validSetup({ slug: "drxshi", name: "DRXSHI" }, false).error, "changing only the page needs no bank details again");

// ---- setup
let r = await call("GET", "/api/tips", { key: "wrong" });
ok(r.status === 401, "the app API needs the server key");
r = await call("GET", "/api/tips");
ok(r.status === 200 && r.data.page === null && r.data.terms.commissionPct === 2 && r.data.terms.streamerSharePct === 98 && r.data.terms.sandbox, "no page yet; 2% commission, 98% to the streamer, sandbox by default");
cf.refuseVendor = true;
r = await call("POST", "/api/tips/setup", { body: good });
ok(r.status === 400 && /invalid pan/.test(r.data.error), "Cashfree's refusal is shown to the streamer");
cf.refuseVendor = false;
r = await call("POST", "/api/tips/setup", { body: good });
const vendorCall = cf.calls.filter((c) => c.path === "/pg/easy-split/vendors").pop();
ok(r.status === 200 && r.data.page.url === BASE + "/t/drxshi" && r.data.page.status === "IN_BENE_CREATION" && !r.data.page.ready, "setup creates the page, waiting for Cashfree to check the account");
ok(vendorCall.body.upi.vpa === "drxshi@okicici" && vendorCall.body.kyc_details.pan === "ABCDE1234F" && vendorCall.body.vendor_id === "cd_123456789012345678", "the streamer becomes a Cashfree vendor with their UPI ID and PAN");
const stored = JSON.stringify(await env.DB.prepare("SELECT * FROM tip_pages").bind().all());
ok(!stored.includes("ABCDE1234F") && !stored.includes("drxshi@okicici") && r.data.page.payout.includes("***"), "PAN and full UPI ID are not kept by ZunimiLabs");
await env.KV.put("token:other", JSON.stringify("999"));
await env.KV.put("guild:999", JSON.stringify({ guildName: "X", config: {} }));
r = await call("POST", "/api/tips/setup", { body: good, key: "other" });
ok(r.status === 409, "another streamer cannot take the same page name");

r = await call("GET", "/t/drxshi", { key: null });
ok(r.status === 200 && r.data.includes("not taking tips right now"), "the page waits until Cashfree has checked the account");
r = await call("POST", "/t/drxshi/order", { key: null, body: { name: "Rahul", amount: 100 } });
ok(r.status === 409, "no orders before the account is checked");
cf.vendorStatus = "ACTIVE";
r = await call("GET", "/api/tips");
ok(r.data.page.status === "ACTIVE" && r.data.page.ready, "the app sees the account become active");

// ---- the page and the QR
r = await call("GET", "/t/drxshi", { key: null });
ok(r.status === 200 && r.data.includes("Tip DRXSHI") && r.data.includes("Test mode") && r.data.includes("sdk.cashfree.com/js/v3/cashfree.js") && r.data.includes("keeps 2%"), "the tip page shows the streamer, test mode and the 2% note");
r = await call("GET", "/t/DRXSHI/qr.svg", { key: null });
ok(r.status === 200 && r.type === "image/svg+xml" && r.data.startsWith("<svg"), "the QR code is an SVG (page names ignore case)");
r = await call("GET", "/t/nobody", { key: null });
ok(r.status === 404, "unknown pages are 404");

// ---- orders
r = await call("POST", "/t/drxshi/order", { key: null, body: { name: "Rahul", message: "Great stream bhai", amount: 5 } });
ok(r.status === 400, "tips under the smallest amount are refused");
r = await call("POST", "/t/drxshi/order", { key: null, body: { name: "Rahul", message: "Great stream bhai", amount: 100 }, headers: { "cf-connecting-ip": "5.5.5.5" } });
const order = cf.calls.filter((c) => c.path === "/pg/orders").pop().body;
ok(r.status === 200 && r.data.paymentSessionId === "session_" + r.data.orderId && r.data.mode === "sandbox", "an order starts Cashfree's checkout");
ok(order.order_splits[0].vendor_id === "cd_123456789012345678" && order.order_splits[0].percentage === 98 && order.order_amount === 100 && order.order_meta.payment_methods === "upi", "the order sends 98% to the streamer, UPI only");
ok(order.order_meta.notify_url === BASE + "/cashfree/webhook" && order.order_meta.return_url.includes(r.data.orderId), "Cashfree is told where to send the webhook and the viewer");
const orderId = r.data.orderId;
for (let i = 0; i < 6; i++) await call("POST", "/t/drxshi/order", { key: null, body: { amount: 100 }, headers: { "cf-connecting-ip": "6.6.6.6" } });
r = await call("POST", "/t/drxshi/order", { key: null, body: { amount: 100 }, headers: { "cf-connecting-ip": "6.6.6.6" } });
ok(r.status === 429, "one viewer cannot flood orders");

// ---- webhook
const hook = (data) => JSON.stringify({ type: "PAYMENT_SUCCESS_WEBHOOK", event_time: "now", data });
const paid = (id, amount = 100) => hook({ order: { order_id: id, order_amount: amount }, payment: { cf_payment_id: 555, payment_status: "SUCCESS", payment_amount: amount } });
let raw = paid(orderId), ts = String(Math.floor(Date.now() / 1000));
r = await call("POST", "/cashfree/webhook", { key: null, raw, headers: { "x-webhook-timestamp": ts, "x-webhook-signature": "nope" } });
ok(r.status === 401 && (await tips()).length === 0, "a webhook with a bad signature is refused");
r = await call("POST", "/cashfree/webhook", { key: null, raw: paid(orderId, 1), headers: { "x-webhook-timestamp": ts, "x-webhook-signature": await sign(ts, paid(orderId, 1)) } });
ok(r.status === 200 && (await tips()).length === 0, "a payment for a different amount is not a tip");
r = await call("POST", "/cashfree/webhook", { key: null, raw, headers: { "x-webhook-timestamp": ts, "x-webhook-signature": await sign(ts, raw) } });
let list = await tips();
ok(r.status === 200 && list.length === 1 && list[0].name === "Rahul" && list[0].message === "Great stream bhai" && list[0].display === "₹100", "a signed payment webhook becomes a tip the app reads aloud");
await call("POST", "/cashfree/webhook", { key: null, raw, headers: { "x-webhook-timestamp": ts, "x-webhook-signature": await sign(ts, raw) } });
r = await call("GET", "/t/drxshi/status/" + orderId, { key: null });
ok((await tips()).length === 1 && r.data.status === "PAID", "a repeated webhook and the done page do not read it twice");
const oldTs = String(Math.floor(Date.now() / 1000) - 3600);
r = await call("POST", "/cashfree/webhook", { key: null, raw, headers: { "x-webhook-timestamp": oldTs, "x-webhook-signature": await sign(oldTs, raw) } });
ok(r.status === 401, "an old, replayed webhook is refused");

// ---- the done page finds a payment when no webhook came
r = await call("POST", "/t/drxshi/order", { key: null, body: { name: "Priya", message: "", amount: 50 }, headers: { "cf-connecting-ip": "7.7.7.7" } });
const second = r.data.orderId;
r = await call("GET", "/t/drxshi/status/" + second, { key: null });
ok(r.data.status === "PENDING", "an unpaid order is pending");
cf.payments[second] = [{ cf_payment_id: 777, payment_status: "SUCCESS", payment_amount: 50 }];
r = await call("GET", "/t/drxshi/status/" + second, { key: null });
list = await tips();
ok(r.data.status === "PAID" && list.length === 2 && list[1].name === "Priya" && list[1].id === "cf:777", "the done page asks Cashfree and records the tip");
r = await call("GET", "/t/drxshi/done?order_id=" + second, { key: null });
ok(r.status === 200 && r.data.includes("Checking your payment"), "the done page renders");

// ---- streamer controls
r = await call("PUT", "/api/tips", { body: { enabled: false } });
ok(r.status === 200 && !r.data.page.ready, "the streamer can pause the page");
r = await call("POST", "/t/drxshi/order", { key: null, body: { amount: 100 }, headers: { "cf-connecting-ip": "8.8.8.8" } });
ok(r.status === 409, "a paused page takes no orders");
r = await call("PUT", "/api/tips", { body: { enabled: true, minAmount: 3 } });
ok(r.status === 400, "the smallest tip cannot go under ₹10");
r = await call("POST", "/api/tips/setup", { body: { slug: "drxshi-live", name: "DRXSHI LIVE" } });
ok(r.status === 200 && r.data.page.url.endsWith("/t/drxshi-live") && cf.calls.filter((c) => c.method === "PATCH").length === 0, "renaming the page leaves the Cashfree account alone");

// ---- every streamer has their own link, QR and Cashfree account; old links never move to someone else
r = await call("GET", "/t/drxshi", { key: null });
ok(r.status === 301 || (r.status === 200 && String(r.data).includes("DRXSHI LIVE")), "the old link still goes to the same streamer after a rename");
await env.KV.put("token:appkey2", JSON.stringify("987654321098765432"));
await env.KV.put("guild:987654321098765432", JSON.stringify({ guildName: "OTHER", config: {} }));
const other = { ...good, slug: "drxshi", name: "Someone else", vpa: "else@okaxis", pan: "zyxwv9876k" };
r = await call("POST", "/api/tips/setup", { body: other, key: "appkey2" });
ok(r.status === 409, "another streamer cannot take a page name the first streamer used before (old QR codes stay safe)");
r = await call("POST", "/api/tips/setup", { body: { ...other, slug: "drxshi-live" }, key: "appkey2" });
ok(r.status === 409, "another streamer cannot take a page name in use");
r = await call("POST", "/api/tips/setup", { body: { ...other, slug: "someone-else" }, key: "appkey2" });
const vendors = cf.calls.filter((c) => c.method === "POST" && c.path === "/pg/easy-split/vendors").map((c) => c.body.vendor_id);
ok(r.status === 200 && r.data.page.url.endsWith("/t/someone-else") && vendors.at(-1) === "cd_987654321098765432" && !vendors.slice(0, -1).includes("cd_987654321098765432"),
   "a second streamer gets their own page and their own Cashfree account");
const qrA = await call("GET", "/t/drxshi-live/qr.svg", { key: null }), qrB = await call("GET", "/t/someone-else/qr.svg", { key: null });
ok(qrA.status === 200 && qrB.status === 200 && qrA.data !== qrB.data, "each streamer's QR code is different");
cf.vendorStatus = "ACTIVE"; await call("GET", "/api/tips", { key: "appkey2" });
r = await call("POST", "/t/someone-else/order", { key: null, body: { name: "V", amount: 100 }, headers: { "cf-connecting-ip": "9.9.9.9" } });
const order2 = cf.calls.filter((c) => c.path === "/pg/orders").pop();
ok(r.status === 200 && order2.body.order_splits[0].vendor_id === "cd_987654321098765432", "a tip on the second page is split to the second streamer only");
r = await call("GET", "/t/drxshi-live/status/" + r.data.orderId, { key: null });
ok(r.status === 404, "one streamer's page cannot see or settle another streamer's order");
r = await call("POST", "/api/tips/setup", { body: { slug: "drxshi", name: "DRXSHI" } });
ok(r.status === 200 && r.data.page.url.endsWith("/t/drxshi"), "the first streamer can take their own old name back");

console.log(fails ? fails + " FAILED" : "all passed");
process.exit(fails ? 1 : 0);
