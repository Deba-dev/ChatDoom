// ZunimiLabs tip page: a streamer's own UPI tip page and QR code, paid through Cashfree Easy Split.
//
// The money never touches ZunimiLabs. Cashfree (an RBI-licensed payment aggregator) takes the viewer's UPI payment, keeps
// it in its own escrow, and settles the streamer's share straight to the streamer's bank account or UPI ID on the
// vendor's settlement schedule. ZunimiLabs' commission (TIP_COMMISSION_PCT, 2% by default) stays in the ZunimiLabs
// Cashfree account. The streamer is a Cashfree Easy Split "vendor"; this file never stores their PAN or account number.
//
// Flow: viewer scans the QR on stream -> /t/<slug> -> types name, message, amount -> Cashfree's hosted checkout (UPI QR on
// a PC, UPI apps on a phone) -> back to /t/<slug>/done. The payment is recorded once, from whichever arrives first: the
// signed Cashfree webhook or the done page asking Cashfree for the order's status. The tip then goes into the same
// "tips" table as every other payment alert, so the desktop app reads it aloud and shows the OBS alert as usual.
//
// Cashfree settings (secrets): CASHFREE_CLIENT_ID, CASHFREE_CLIENT_SECRET. Vars: CASHFREE_ENV ("production" for real
// money, anything else is the sandbox), TIP_COMMISSION_PCT (default 2), TIP_GATEWAY_FEE_PCT (default 0: Cashfree's own
// fee, also taken from the streamer's share so ZunimiLabs does not pay it).
import qrcode from "./vendor/qrcode.js";

const API_VERSION = "2026-01-01";
const SLUG = /^[a-z0-9](?:[a-z0-9-]{1,28}[a-z0-9])$/;
const RESERVED = new Set(["admin", "api", "app", "chatdoom", "zunimi", "zunimilabs", "support", "help", "login", "setup",
  "cashfree", "test", "tips", "tip", "pay", "payment", "payments", "official", "staff"]);
const MIN_TIP = 10, MAX_TIP = 100000;
const ORDER_LIMIT_PER_MINUTE = 6;      // per viewer IP, so nobody can flood a streamer with unpaid orders

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clean = (v, max) => String(v == null ? "" : v).replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
const rand = (n) => Array.from(crypto.getRandomValues(new Uint8Array(n)), (b) => "abcdefghijkmnpqrstuvwxyz23456789"[b % 32]).join("");
const enc = new TextEncoder();

export const commission = (env) => clampPct(env.TIP_COMMISSION_PCT, 2);
export const gatewayFee = (env) => clampPct(env.TIP_GATEWAY_FEE_PCT, 0);
function clampPct(v, fallback) {
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n < 20 ? n : fallback;
}
// What the streamer gets, in percent of each tip
export const streamerShare = (env) => Math.round((100 - commission(env) - gatewayFee(env)) * 100) / 100;

export const tipsConfigured = (env) => !!(env.CASHFREE_CLIENT_ID && env.CASHFREE_CLIENT_SECRET);
const live = (env) => String(env.CASHFREE_ENV || "").toLowerCase() === "production";
const base = (env) => (live(env) ? "https://api.cashfree.com/pg" : "https://sandbox.cashfree.com/pg");

async function cashfree(env, method, path, body) {
  const headers = { "x-client-id": env.CASHFREE_CLIENT_ID, "x-client-secret": env.CASHFREE_CLIENT_SECRET,
    "x-api-version": API_VERSION, accept: "application/json" };
  if (body) {
    headers["content-type"] = "application/json";
    headers["x-idempotency-key"] = crypto.randomUUID();
  }
  const r = await fetch(base(env) + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}
const cfError = (r) => clean((r.data && (r.data.message || r.data.code)) || "Cashfree answered " + r.status, 200);

// ---------------- storage ----------------
let ready = null;
async function store(env) {
  if (!env.DB) throw new Error("Cloudflare D1 storage is not set up (see CLOUD-SETUP.txt)");
  if (!ready) {
    ready = (async () => {
      await env.DB.prepare("CREATE TABLE IF NOT EXISTS tip_pages (slug TEXT PRIMARY KEY, guild TEXT NOT NULL UNIQUE, vendor_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, remarks TEXT, payout TEXT, min_amount REAL NOT NULL, enabled INTEGER NOT NULL, created INTEGER NOT NULL)").run();
      await env.DB.prepare("CREATE TABLE IF NOT EXISTS tip_orders (order_id TEXT PRIMARY KEY, guild TEXT NOT NULL, slug TEXT NOT NULL, name TEXT, message TEXT, amount REAL NOT NULL, status TEXT NOT NULL, created INTEGER NOT NULL)").run();
      await env.DB.prepare("CREATE INDEX IF NOT EXISTS tip_orders_created ON tip_orders (created)").run();
      // Every page name a streamer ever used stays theirs: an old QR or link on a past stream must never pay someone else.
      await env.DB.prepare("CREATE TABLE IF NOT EXISTS tip_slugs (slug TEXT PRIMARY KEY, guild TEXT NOT NULL, created INTEGER NOT NULL)").run();
    })().catch((e) => { ready = null; throw e; });
  }
  await ready;
  return env.DB;
}
const pageBySlug = async (d, slug) => d.prepare("SELECT * FROM tip_pages WHERE slug = ?").bind(slug).first();
const pageByGuild = async (d, guild) => d.prepare("SELECT * FROM tip_pages WHERE guild = ?").bind(guild).first();
const slugOwner = async (d, slug) => {
  const live = await pageBySlug(d, slug);
  if (live) return live.guild;
  const old = await d.prepare("SELECT guild FROM tip_slugs WHERE slug = ?").bind(slug).first();
  return old ? old.guild : null;
};
const keepSlug = (d, slug, guild) =>
  d.prepare("INSERT OR IGNORE INTO tip_slugs (slug, guild, created) VALUES (?, ?, ?)").bind(slug, guild, Math.floor(Date.now() / 1000)).run();
// The page a link points to: its current name, or a name its streamer used before (old QR codes keep working for them).
async function pageForSlug(d, slug) {
  const p = await pageBySlug(d, slug);
  if (p) return p;
  const old = await d.prepare("SELECT guild FROM tip_slugs WHERE slug = ?").bind(slug).first();
  return old ? pageByGuild(d, old.guild) : null;
}

function publicPage(env, origin, p) {
  if (!p) return null;
  return { slug: p.slug, name: p.name, status: p.status, remarks: p.remarks || "", payout: p.payout || "",
    minAmount: p.min_amount, enabled: !!p.enabled, url: origin + "/t/" + p.slug, qrUrl: origin + "/t/" + p.slug + "/qr.svg",
    ready: p.status === "ACTIVE" && !!p.enabled };
}
const terms = (env) => ({ commissionPct: commission(env), gatewayFeePct: gatewayFee(env), streamerSharePct: streamerShare(env),
  sandbox: !live(env), configured: tipsConfigured(env), minTip: MIN_TIP });

// ---------------- desktop app API (/api/tips...), already signed in with the server key ----------------
export async function handleTipApi(request, env, url, guildId, body) {
  const route = request.method + " " + url.pathname;
  if (!tipsConfigured(env)) return json({ error: "The ZunimiLabs tip page is not switched on yet.", terms: terms(env) }, 503);
  const d = await store(env);

  if (route === "GET /api/tips") {
    let p = await pageByGuild(d, guildId);
    if (p && p.status !== "ACTIVE" && p.status !== "BLOCKED") p = (await refreshVendor(env, d, p)) || p;
    return json({ page: publicPage(env, url.origin, p), terms: terms(env) });
  }

  if (route === "POST /api/tips/setup") {
    const existing = await pageByGuild(d, guildId);
    const v = validSetup(body, !existing);
    if (v.error) return json({ error: v.error }, 400);
    const owner = await slugOwner(d, v.slug);
    if (owner && owner !== String(guildId)) return json({ error: "That page name is taken. Try another." }, 409);
    const digits = String(guildId).replace(/\D/g, "");
    if (!existing && !digits) return json({ error: "Connect your Discord server in CHATDOOM first." }, 400);
    const vendorId = existing ? existing.vendor_id : "cd_" + digits.slice(0, 30);     // one Cashfree account per streamer
    const vendor = { vendor_id: vendorId, status: "ACTIVE", name: v.holder, email: v.email, phone: v.phone,
      verify_account: true, dashboard_access: false, schedule_option: 2,      // T+2: every working day, two days later
      kyc_details: { account_type: "INDIVIDUAL", business_type: "Content creator", pan: v.pan },
      ...(v.vpa ? { upi: { vpa: v.vpa, account_holder: v.holder } }
        : { bank: { account_number: v.account, account_holder: v.holder, ifsc: v.ifsc } }) };
    let r;
    if (!existing) r = await cashfree(env, "POST", "/easy-split/vendors", vendor);
    else if (v.payoutChanged) r = await cashfree(env, "PATCH", "/easy-split/vendors/" + vendorId, vendor);
    else r = { ok: true, data: {} };
    if (!r.ok) return json({ error: "Cashfree did not accept these details: " + cfError(r) }, 400);

    const payout = v.vpa ? "UPI " + maskVpa(v.vpa) : v.account ? "Bank account ending " + v.account.slice(-4) + " (" + v.ifsc + ")" : (existing && existing.payout) || "";
    const status = r.data.status || (existing ? existing.status : "IN_BENE_CREATION");
    try {
      if (existing) {
        await keepSlug(d, existing.slug, String(guildId));
        await d.prepare("UPDATE tip_pages SET slug = ?, name = ?, min_amount = ?, payout = ?, status = ? WHERE guild = ?")
          .bind(v.slug, v.name, v.minAmount, payout, status, guildId).run();
      } else
        await d.prepare("INSERT INTO tip_pages (slug, guild, vendor_id, name, status, remarks, payout, min_amount, enabled, created) VALUES (?, ?, ?, ?, ?, '', ?, ?, 1, ?)")
          .bind(v.slug, guildId, vendorId, v.name, status, payout, v.minAmount, Math.floor(Date.now() / 1000)).run();
      await keepSlug(d, v.slug, String(guildId));
    } catch (e) {
      if (/UNIQUE|constraint/i.test(String(e && e.message))) return json({ error: "That page name is taken. Try another." }, 409);
      throw e;
    }
    return json({ ok: true, page: publicPage(env, url.origin, await pageByGuild(d, guildId)), terms: terms(env) });
  }

  if (route === "PUT /api/tips") {
    const p = await pageByGuild(d, guildId);
    if (!p) return json({ error: "Set up your tip page first." }, 404);
    const enabled = body.enabled === undefined ? p.enabled : body.enabled ? 1 : 0;
    const min = body.minAmount === undefined ? p.min_amount : Math.round(Number(body.minAmount));
    if (!(min >= MIN_TIP && min <= MAX_TIP)) return json({ error: "The smallest tip must be between ₹" + MIN_TIP + " and ₹" + MAX_TIP + "." }, 400);
    await d.prepare("UPDATE tip_pages SET enabled = ?, min_amount = ? WHERE guild = ?").bind(enabled, min, guildId).run();
    return json({ ok: true, page: publicPage(env, url.origin, await pageByGuild(d, guildId)) });
  }
  return json({ error: "not found" }, 404);
}

function maskVpa(vpa) {
  const [user, bank] = vpa.split("@");
  return (user.length > 3 ? user.slice(0, 2) + "***" + user.slice(-1) : user[0] + "**") + "@" + bank;
}

export function validSetup(b, first) {
  const slug = clean(b.slug, 30).toLowerCase();
  if (!SLUG.test(slug) || RESERVED.has(slug)) return { error: "Page name: 3 to 30 letters, numbers or dashes (like drxshi), and not a reserved word." };
  const name = clean(b.name, 40);
  if (name.length < 2) return { error: "Type the name viewers see on your page." };
  const minAmount = b.minAmount === undefined ? 20 : Math.round(Number(b.minAmount));
  if (!(minAmount >= MIN_TIP && minAmount <= MAX_TIP)) return { error: "The smallest tip must be between ₹" + MIN_TIP + " and ₹" + MAX_TIP + "." };
  const out = { slug, name, minAmount };
  const payoutGiven = !!(b.vpa || b.account || b.pan);
  if (!first && !payoutGiven) return out;       // only the page changes
  out.payoutChanged = true;
  out.holder = clean(b.holder, 100).replace(/[^A-Za-z .&/-]/g, "");
  if (out.holder.length < 3) return { error: "Type the account holder's name exactly as the bank has it." };
  out.email = clean(b.email, 100);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(out.email)) return { error: "Type a valid email address." };
  out.phone = clean(b.phone, 15).replace(/\D/g, "").replace(/^91(?=\d{10}$)/, "");
  if (!/^[6-9]\d{9}$/.test(out.phone)) return { error: "Type a 10-digit Indian mobile number." };
  out.pan = clean(b.pan, 10).toUpperCase();
  if (!/^[A-Z]{5}\d{4}[A-Z]$/.test(out.pan)) return { error: "Type your PAN (like ABCDE1234F). Cashfree needs it to pay you." };
  const vpa = clean(b.vpa, 60).toLowerCase();
  const account = clean(b.account, 20).replace(/\s/g, ""), ifsc = clean(b.ifsc, 11).toUpperCase();
  if (vpa) {
    if (!/^[a-z0-9._-]{2,256}@[a-z][a-z0-9]{1,63}$/.test(vpa)) return { error: "Type a valid UPI ID (like name@okicici)." };
    out.vpa = vpa;
  } else {
    if (!/^\d{9,18}$/.test(account)) return { error: "Type a UPI ID, or a bank account number (9 to 18 digits) with its IFSC." };
    if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(ifsc)) return { error: "Type the branch IFSC (like HDFC0001234)." };
    out.account = account;
    out.ifsc = ifsc;
  }
  return out;
}

async function refreshVendor(env, d, p) {
  const r = await cashfree(env, "GET", "/easy-split/vendors/" + p.vendor_id);
  if (!r.ok || !r.data.status) return null;
  const remarks = clean(r.data.remarks || "", 200);
  await d.prepare("UPDATE tip_pages SET status = ?, remarks = ? WHERE slug = ?").bind(r.data.status, remarks, p.slug).run();
  return { ...p, status: r.data.status, remarks };
}

// ---------------- public: the tip page, its QR code, orders, the webhook ----------------
export async function handleTipPublic(request, env, url, addTip) {
  const parts = url.pathname.split("/").filter(Boolean);       // ["t", slug, ...] or ["cashfree", "webhook"]
  if (parts[0] === "cashfree" && parts[1] === "webhook" && request.method === "POST") return webhook(request, env, addTip);
  if (parts[0] !== "t" || !parts[1]) return null;
  if (!tipsConfigured(env)) return tipHtml("Tips are not on yet", "<p>This tip page is not open yet.</p>", 503);
  const d = await store(env);
  const asked = clean(parts[1], 30).toLowerCase();
  const p = await pageForSlug(d, asked);
  if (!p) return tipHtml("Page not found", "<p>There is no tip page with this name. Check the link on stream.</p>", 404);
  const action = parts[2] || "";

  if (action === "qr.svg") return qrSvg(url.origin + "/t/" + p.slug);
  if (action === "order" && request.method === "POST") return createOrder(request, env, url, d, p);
  if (action === "status" && parts[3]) return orderStatus(env, d, p, parts[3], addTip);
  if (action === "done") return donePage(env, p, url.searchParams.get("order_id") || "");
  if (action === "" && asked !== p.slug) return Response.redirect(url.origin + "/t/" + p.slug, 301);   // renamed: same streamer
  if (action === "") return tipPage(env, p);
  return tipHtml("Page not found", "<p>Nothing here.</p>", 404);
}

function qrSvg(text) {
  const q = qrcode(0, "M");
  q.addData(text);
  q.make();
  // white quiet zone so phones read it on a dark overlay
  return new Response(q.createSvgTag({ cellSize: 8, margin: 4, scalable: true }).replace("<svg ", '<svg style="background:#fff" '),
    { headers: { "content-type": "image/svg+xml", "cache-control": "public, max-age=3600", "access-control-allow-origin": "*" } });
}

async function createOrder(request, env, url, d, p) {
  if (p.status !== "ACTIVE" || !p.enabled) return json({ error: "This streamer's tip page is not taking tips right now." }, 409);
  const ip = request.headers.get("cf-connecting-ip") || "?";
  const minute = Math.floor(Date.now() / 60000);
  const rateKey = "tiprate:" + ip + ":" + minute;
  const used = parseInt((await env.KV.get(rateKey)) || "0", 10) || 0;
  if (used >= ORDER_LIMIT_PER_MINUTE) return json({ error: "Too many tries. Wait a minute and try again." }, 429);
  await env.KV.put(rateKey, String(used + 1), { expirationTtl: 120 });

  const b = await request.json().catch(() => ({}));
  const name = clean(b.name, 40) || "Someone";
  const message = clean(b.message, 200);
  const amount = Math.round(Number(b.amount) * 100) / 100;
  if (!(amount >= p.min_amount && amount <= MAX_TIP)) return json({ error: "Tips here start at ₹" + p.min_amount + "." }, 400);

  const orderId = "cd_" + Date.now().toString(36) + rand(10);
  const phone = clean(b.phone, 15).replace(/\D/g, "").slice(-10);
  const order = {
    order_id: orderId, order_amount: amount, order_currency: "INR",
    // Cashfree needs a customer id and phone. A viewer may stay anonymous, so an unknown phone is a placeholder.
    customer_details: { customer_id: "viewer_" + rand(12), customer_phone: /^[6-9]\d{9}$/.test(phone) ? phone : "9999999999",
      ...(name.length >= 3 ? { customer_name: name.replace(/[^\p{L}\p{N} .'-]/gu, "").slice(0, 100) || undefined } : {}) },
    order_meta: { return_url: url.origin + "/t/" + p.slug + "/done?order_id=" + orderId, notify_url: url.origin + "/cashfree/webhook",
      payment_methods: "upi" },
    order_note: clean("Tip for " + p.name, 200),
    order_tags: { kind: "chatdoom_tip", page: p.slug },
    order_expiry_time: new Date(Date.now() + 30 * 60000).toISOString(),
    order_splits: [{ vendor_id: p.vendor_id, percentage: streamerShare(env) }],
  };
  const r = await cashfree(env, "POST", "/orders", order);
  if (!r.ok || !r.data.payment_session_id) return json({ error: "The payment could not start: " + cfError(r) }, 502);
  await d.prepare("INSERT INTO tip_orders (order_id, guild, slug, name, message, amount, status, created) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?)")
    .bind(orderId, p.guild, p.slug, name, message, amount, Math.floor(Date.now() / 1000)).run();
  await d.prepare("DELETE FROM tip_orders WHERE created < ? AND status != 'PAID'").bind(Math.floor(Date.now() / 1000) - 7 * 86400).run();
  return json({ orderId, paymentSessionId: r.data.payment_session_id, mode: live(env) ? "production" : "sandbox" });
}

// Records a paid order once, whichever of the webhook and the done page gets here first.
async function settle(d, order, paymentId, addTip) {
  const claimed = await d.prepare("UPDATE tip_orders SET status = 'PAID' WHERE order_id = ? AND status != 'PAID'").bind(order.order_id).run();
  if (!claimed.meta || !claimed.meta.changes) return false;
  await addTip(order.guild, { id: "cf:" + (paymentId || order.order_id), name: order.name || "Someone", message: order.message || "",
    value: order.amount, currency: "INR" });
  return true;
}

async function orderStatus(env, d, p, orderId, addTip) {
  const order = await d.prepare("SELECT * FROM tip_orders WHERE order_id = ? AND guild = ?").bind(clean(orderId, 45), p.guild).first();
  if (!order) return json({ status: "UNKNOWN" }, 404);
  if (order.status === "PAID") return json({ status: "PAID" });
  const r = await cashfree(env, "GET", "/orders/" + order.order_id + "/payments");
  const paid = r.ok && Array.isArray(r.data) ? r.data.find((x) => x.payment_status === "SUCCESS") : null;
  if (paid) {
    await settle(d, order, String(paid.cf_payment_id || ""), addTip);
    return json({ status: "PAID" });
  }
  const failed = r.ok && Array.isArray(r.data) && r.data.length && r.data.every((x) => ["FAILED", "USER_DROPPED", "CANCELLED", "VOID"].includes(x.payment_status));
  return json({ status: failed ? "FAILED" : "PENDING" });
}

async function webhook(request, env, addTip) {
  if (!tipsConfigured(env)) return json({ error: "not set up" }, 503);
  const raw = await request.text();
  const ts = request.headers.get("x-webhook-timestamp") || "";
  const sig = request.headers.get("x-webhook-signature") || "";
  const key = await crypto.subtle.importKey("raw", enc.encode(env.CASHFREE_CLIENT_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const want = btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(ts + raw)))));
  if (!ts || !sig || !same(sig, want)) return json({ error: "bad signature" }, 401);
  const age = Math.abs(Date.now() - Number(ts) * (String(ts).length <= 10 ? 1000 : 1));
  if (!(age < 15 * 60000)) return json({ error: "old webhook" }, 401);

  const body = JSON.parse(raw || "{}");
  const type = String(body.type || "");
  const payment = (body.data && body.data.payment) || {};
  const orderId = body.data && body.data.order && body.data.order.order_id;
  if (!type.startsWith("PAYMENT_SUCCESS") || payment.payment_status !== "SUCCESS" || !orderId) return json({ ok: true, ignored: type || "unknown" });
  const d = await store(env);
  const order = await d.prepare("SELECT * FROM tip_orders WHERE order_id = ?").bind(String(orderId)).first();
  if (!order) return json({ ok: true, ignored: "not a tip order" });
  if (Math.abs(Number(payment.payment_amount) - order.amount) > 0.01) return json({ ok: true, ignored: "amount mismatch" });
  await settle(d, order, String(payment.cf_payment_id || ""), addTip);
  return json({ ok: true });
}

function same(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

// ---------------- pages ----------------
const STYLE = `*{box-sizing:border-box}body{font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:#0b0d14;color:#eef0f7;margin:0;min-height:100vh;display:grid;place-items:center;padding:16px}
main{width:100%;max-width:440px;background:#141826;border:1px solid #262c40;border-radius:18px;padding:24px}
h1{font-size:22px;margin:0 0 4px}.sub{color:#9aa3bd;font-size:14px;margin:0 0 18px}label{display:block;font-size:13px;color:#b9c0d6;margin:14px 0 6px}
input,textarea{width:100%;font:inherit;color:#eef0f7;background:#0e111b;border:1px solid #2c3349;border-radius:10px;padding:11px 12px}textarea{resize:vertical;min-height:76px}
input:focus,textarea:focus{outline:2px solid #7c5cff;border-color:transparent}.amounts{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.amounts button{font:inherit;background:#1b2133;color:#eef0f7;border:1px solid #2c3349;border-radius:10px;padding:10px 0;cursor:pointer}.amounts button.on{border-color:#7c5cff;background:#251e4a}
.go{width:100%;margin-top:20px;font:600 17px system-ui;color:#fff;background:linear-gradient(90deg,#7c5cff,#ff4d8d);border:0;border-radius:12px;padding:14px;cursor:pointer}
.go:disabled{opacity:.6;cursor:default}.err{color:#ff7a90;font-size:14px;min-height:20px;margin-top:10px}.fine{color:#7f88a3;font-size:12px;margin-top:16px}
.count{float:right;color:#7f88a3}.badge{display:inline-block;font-size:12px;background:#3a2a00;color:#ffcf5a;border-radius:6px;padding:2px 8px;margin-bottom:10px}`;

function tipHtml(title, body, status = 200) {
  return new Response(`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title><meta name="robots" content="noindex"><style>${STYLE}</style><main>${body}</main></html>`,
  { status, headers: { "content-type": "text/html; charset=utf-8", "referrer-policy": "no-referrer" } });
}

function tipPage(env, p) {
  if (p.status !== "ACTIVE" || !p.enabled)
    return tipHtml("Tip " + p.name, `<h1>Tip ${esc(p.name)}</h1><p class="sub">This tip page is not taking tips right now. Check back on stream.</p>`);
  const presets = [p.min_amount, 50, 100, 200, 500].filter((v, i, a) => v >= p.min_amount && a.indexOf(v) === i).slice(0, 4);
  const sandbox = !live(env);
  return tipHtml("Tip " + p.name, `${sandbox ? '<span class="badge">Test mode: no real money</span>' : ""}
<h1>Tip ${esc(p.name)}</h1><p class="sub">Your name and message show up on stream. Pay with any UPI app.</p>
<form id="f"><label for="name">Your name</label><input id="name" maxlength="40" autocomplete="nickname" placeholder="Shown on stream">
<label for="msg">Message <span class="count" id="count">0/200</span></label><textarea id="msg" maxlength="200" placeholder="Say something nice"></textarea>
<label>Amount (₹${esc(p.min_amount)} or more)</label><div class="amounts">${presets.map((v) => `<button type="button" data-v="${v}">₹${v}</button>`).join("")}</div>
<input id="amount" type="number" inputmode="decimal" min="${p.min_amount}" max="${MAX_TIP}" step="1" placeholder="Or type an amount" style="margin-top:8px">
<button class="go" id="go" type="submit">Pay with UPI</button><div class="err" id="err" role="alert"></div></form>
<p class="fine">Payments are processed by Cashfree Payments, an RBI-authorised payment aggregator, and go to ${esc(p.name)}. ZunimiLabs keeps ${commission(env)}% to run this page${gatewayFee(env) ? " and Cashfree's fee of " + gatewayFee(env) + "% also applies" : ""}. Tips are gifts and are not refunded. Messages can be filtered by the streamer. <a href="https://zunimilabs.online/chatdoom/terms/" style="color:#9aa3bd">Terms</a></p>
<script src="https://sdk.cashfree.com/js/v3/cashfree.js"></script>
<script>
const $=(id)=>document.getElementById(id),amt=$("amount"),msg=$("msg");
document.querySelectorAll(".amounts button").forEach(b=>b.onclick=()=>{amt.value=b.dataset.v;document.querySelectorAll(".amounts button").forEach(x=>x.classList.toggle("on",x===b))});
amt.oninput=()=>document.querySelectorAll(".amounts button").forEach(x=>x.classList.toggle("on",x.dataset.v===amt.value));
msg.oninput=()=>$("count").textContent=msg.value.length+"/200";
$("f").onsubmit=async(e)=>{e.preventDefault();$("err").textContent="";const go=$("go");go.disabled=true;go.textContent="Starting payment...";
try{const r=await fetch(location.pathname.replace(/\\/$/,"")+"/order",{method:"POST",headers:{"content-type":"application/json"},
body:JSON.stringify({name:$("name").value,message:msg.value,amount:amt.value})});const d=await r.json();
if(!r.ok)throw new Error(d.error||"Something went wrong");
Cashfree({mode:d.mode}).checkout({paymentSessionId:d.paymentSessionId,redirectTarget:"_self"});}
catch(err){$("err").textContent=err.message;go.disabled=false;go.textContent="Pay with UPI";}};
</script>`);
}

function donePage(env, p, orderId) {
  return tipHtml("Thanks!", `<h1 id="t">Checking your payment...</h1><p class="sub" id="s">This takes a few seconds.</p>
<p><a href="/t/${esc(p.slug)}" style="color:#9aa3bd">Back to ${esc(p.name)}'s tip page</a></p>
<script>
const id=${JSON.stringify(clean(orderId, 45))};let tries=0;
async function check(){tries++;try{const r=await fetch("/t/${esc(p.slug)}/status/"+encodeURIComponent(id));const d=await r.json();
if(d.status==="PAID"){t.textContent="Thank you!";s.textContent="Your tip went through. Your name and message will show up on stream in a moment.";return}
if(d.status==="FAILED"||d.status==="UNKNOWN"){t.textContent="The payment did not go through";s.textContent="No money was taken. You can try again.";return}}catch(e){}
if(tries<40)setTimeout(check,3000);else{t.textContent="Still waiting for your bank";s.textContent="If money left your account, the tip will show up on stream once your bank confirms it."}}
const t=document.getElementById("t"),s=document.getElementById("s");check();
</script>`);
}
