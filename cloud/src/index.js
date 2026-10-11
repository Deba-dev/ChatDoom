// CHATDOOM cloud: Discord role linking for streamers. Runs on Cloudflare Workers (free tier).
// It never touches money. It only: (1) installs the bot, (2) links viewers to Discord accounts,
// (3) gives roles when the desktop app reports activity.
import { handlePlatformAuth } from "./platform-auth.js";
import { handlePublicPage } from "./legal-pages.js";

const API = "https://discord.com/api/v10";
const PLATFORMS = ["youtube", "twitch", "kick"];
const enc = new TextEncoder();
const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const TRANSLATION_LANGUAGES = new Set([
  "af", "ar", "bg", "bn", "ca", "cs", "cy", "da", "de", "el", "en", "es", "et", "fa", "fi", "fr", "gu",
  "he", "hi", "hr", "hu", "id", "it", "ja", "jv", "ka", "kk", "km", "kn", "ko", "lo", "lt",
  "lv", "mk", "ml", "mn", "mr", "ms", "my", "ne", "nl", "no", "pa", "pl", "pt", "ro", "ru", "si",
  "sk", "sl", "so", "sq", "sv", "sw", "ta", "te", "th", "tl", "tr", "uk", "ur", "vi", "zh",
]);
const DAILY_TRANSLATION_LIMIT = 300;

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const page = (title, body, status = 200) =>
  new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title><style>body{font:16px system-ui;background:#0e1118;color:#e8ebf3;display:grid;place-items:center;min-height:100vh;margin:0}
main{max-width:520px;padding:28px;background:#161b27;border:1px solid #272d3e;border-radius:16px}
code,.big{background:#0f131c;border:1px solid #272d3e;border-radius:8px;padding:8px 12px;display:block;word-break:break-all;margin:10px 0}
.big{font-size:30px;letter-spacing:4px;text-align:center}a{color:#8ab4ff}h1{margin-top:0}</style><main><h1>${esc(title)}</h1>${body}</main>`,
    { status, headers: { "content-type": "text/html; charset=utf-8" } }
  );

function randomString(len, alphabet) {
  const bytes = crypto.getRandomValues(new Uint8Array(len));
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
}
const newCode = () => { const c = randomString(8, ALPHABET); return c.slice(0, 4) + "-" + c.slice(4); };
const newToken = () => randomString(40, "abcdefghijklmnopqrstuvwxyz0123456789");

async function kvGet(env, key) { const v = await env.KV.get(key); return v ? JSON.parse(v) : null; }
async function kvPut(env, key, val, ttl) {
  await env.KV.put(key, JSON.stringify(val), ttl ? { expirationTtl: ttl } : undefined);
}

// small in-memory cache (per worker instance) so frequent app polls do not burn the free KV read limit
const cache = new Map();
async function cached(key, loader, ttlMs = 30000) {
  const hit = cache.get(key);
  if (hit && hit.exp > Date.now()) return hit.val;
  const val = await loader();
  cache.set(key, { exp: Date.now() + ttlMs, val });
  if (cache.size > 500) cache.clear();
  return val;
}

const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
async function hmacRaw(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return crypto.subtle.sign("HMAC", key, enc.encode(data));
}
const hex = (buf) => Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
async function hmacHex(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}
function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

// D1 (SQLite) holds payment alerts and encrypted platform account tokens.
let dbReady = null;
function db(env) {
  if (!env.DB) throw new Error("Cloudflare D1 storage is not set up (see CLOUD-SETUP.txt)");
  if (!dbReady) {
    dbReady = (async () => {
      await env.DB.prepare("CREATE TABLE IF NOT EXISTS tips (seq INTEGER PRIMARY KEY AUTOINCREMENT, guild TEXT NOT NULL, pay_id TEXT NOT NULL, ts INTEGER NOT NULL, name TEXT, message TEXT, amount REAL, currency TEXT, display TEXT, UNIQUE(guild, pay_id))").run();
      await env.DB.prepare("CREATE INDEX IF NOT EXISTS tips_guild_seq ON tips (guild, seq)").run();
      await env.DB.prepare("CREATE TABLE IF NOT EXISTS platform_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, session_hash TEXT NOT NULL UNIQUE, platform TEXT NOT NULL, provider_user_id TEXT NOT NULL, display_name TEXT NOT NULL, access_token TEXT NOT NULL, refresh_token TEXT NOT NULL, expires_at INTEGER NOT NULL)").run();
      await env.DB.prepare("CREATE TABLE IF NOT EXISTS platform_api_quota (day TEXT PRIMARY KEY, used INTEGER NOT NULL)").run();
    })().catch((e) => { dbReady = null; throw e; });
  }
  return dbReady.then(() => env.DB);
}

const SYMBOLS = { INR: "₹", USD: "$", EUR: "€", GBP: "£", AUD: "A$", CAD: "C$", SGD: "S$", AED: "AED " };
function displayAmount(value, currency) {
  const n = Number.isInteger(value) ? String(value) : value.toFixed(2);
  const sym = SYMBOLS[currency];
  return sym ? sym + n : currency + " " + n;
}
const clean = (v, max) => String(v == null ? "" : v).replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);

// Razorpay: the viewer's own fields (name, message...) arrive in payment.notes
function parseRazorpay(pay) {
  const notes = pay.notes && !Array.isArray(pay.notes) && typeof pay.notes === "object" ? pay.notes : {};
  let name = "", message = "";
  for (const [k, v] of Object.entries(notes)) {
    if (typeof v !== "string" || !v.trim()) continue;
    if (!name && /name|from|donor/i.test(k)) name = v;
    else if (!message && /message|msg|note|comment|wish|text|say/i.test(k)) message = v;
  }
  const currency = String(pay.currency || "INR").toUpperCase();
  const value = (Number(pay.amount) || 0) / 100;
  return { id: String(pay.id), name: clean(name, 40) || "Someone", message: clean(message, 300), value, currency, display: displayAmount(value, currency) };
}

const SOURCES = {
  youtube: { label: "YouTube", role: "YouTube Viewer", color: 0xff4d4d },
  twitch: { label: "Twitch", role: "Twitch Viewer", color: 0x9146ff },
  kick: { label: "Kick", role: "Kick Viewer", color: 0x53fc18 },
};

// Creates (or reuses) a role and a never-expiring invite for each platform, and saves the invite->role rules.
async function discordSetup(env, guildId, guild, body) {
  const wanted = (Array.isArray(body.sources) && body.sources.length ? body.sources : Object.keys(SOURCES)).filter((x) => SOURCES[x]);
  if (!wanted.length) return { status: 400, data: { error: "Choose at least one platform." } };
  const rr = await bot(env, "GET", `/guilds/${guildId}/roles`);
  if (!rr.ok) return { status: 502, data: { error: "The bot cannot read the server's roles. Add it to your server again." } };
  const roles = await rr.json();

  let channelId = /^\d{5,25}$/.test(String(body.channelId || "")) ? String(body.channelId) : "";
  let channelName = "";
  if (!channelId) {
    const gr = await bot(env, "GET", `/guilds/${guildId}`);
    const g = gr.ok ? await gr.json() : {};
    channelId = g.system_channel_id || "";
    if (!channelId) {
      const cr = await bot(env, "GET", `/guilds/${guildId}/channels`);
      const first = cr.ok ? (await cr.json()).filter((c) => c.type === 0).sort((a, b) => a.position - b.position)[0] : null;
      channelId = first ? first.id : "";
      channelName = first ? first.name : "";
    }
  }
  if (!channelId) return { status: 409, data: { error: "The server has no text channel the bot can see. Make one, then try again." } };

  const il = await bot(env, "GET", `/guilds/${guildId}/invites`);
  const liveInvites = new Set(il.ok ? (await il.json()).map((i) => i.code) : []);
  const previous = (guild.config && guild.config.inviteRules) || [];
  const out = [], rules = [];
  for (const src of wanted) {
    const meta = SOURCES[src];
    let role = roles.find((r) => r.name === meta.role);
    let created = false;
    if (!role) {
      const cr = await bot(env, "POST", `/guilds/${guildId}/roles`, { name: meta.role, color: meta.color, mentionable: false, hoist: false, permissions: "0" });
      if (cr.status === 403) return { status: 403, data: { error: "The bot is missing the Manage Roles permission. Add it to your server again from the app." } };
      if (!cr.ok) return { status: 502, data: { error: "Discord would not create the " + meta.role + " role (error " + cr.status + ")." } };
      role = await cr.json();
      roles.push(role);
      created = true;
    }
    const keep = previous.find((r) => r.label === meta.label && r.role === role.id && liveInvites.has(r.code));
    let code = keep ? keep.code : "";
    if (!code) {
      const ir = await bot(env, "POST", `/channels/${channelId}/invites`, { max_age: 0, max_uses: 0, unique: true });
      if (!ir.ok) return { status: ir.status === 403 ? 403 : 502, data: { error: ir.status === 403 ? "The bot cannot create invites in that channel. Add it to your server again from the app." : "Discord would not create an invite (error " + ir.status + ")." } };
      code = (await ir.json()).code;
    }
    rules.push({ code, role: String(role.id), label: meta.label });
    out.push({ source: src, label: meta.label, roleId: String(role.id), roleName: role.name, roleCreated: created, invite: "https://discord.gg/" + code, reused: !!keep });
  }
  const others = previous.filter((r) => !wanted.some((w) => SOURCES[w].label === r.label));
  guild.config = { ...(guild.config || {}), inviteRules: [...others, ...rules].slice(0, 6) };
  await kvPut(env, "guild:" + guildId, guild);
  cache.set("g:" + guildId, { exp: Date.now() + 30000, val: guild });
  const idx = (await kvGet(env, "idx:invites")) || [];
  if (!idx.includes(guildId)) await kvPut(env, "idx:invites", [...idx, guildId]);
  return { status: 200, data: { ok: true, sources: out, channelId, channelName } };
}

function inviteCode(v) {
  v = String(v || "").trim();
  const m = v.match(/^(?:https?:\/\/)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com\/invite)\/([A-Za-z0-9-]{2,32})\/?$/i);
  if (m) return m[1];
  return /^[A-Za-z0-9-]{2,32}$/.test(v) ? v : "";
}

// Looks at which normal invite new members used (invite use counts + new member list) and gives the matching role.
async function checkInvites(env, guildId, guild) {
  const rules = (guild.config && guild.config.inviteRules) || [];
  const report = { rules: [], assigned: [], notes: [] };
  if (!rules.length) { report.notes.push("No invite roles are set up yet."); return report; }
  const ir = await bot(env, "GET", `/guilds/${guildId}/invites`);
  if (ir.status === 401 || ir.status === 403) { report.error = "The bot cannot see invites. Add it to your server again from the app so it gets the Manage Server permission."; return report; }
  if (!ir.ok) { report.error = "Discord error " + ir.status + " while reading invites"; return report; }
  const uses = {};
  for (const i of await ir.json()) uses[i.code] = i.uses || 0;
  for (const r of rules) report.rules.push({ label: r.label, code: r.code, found: r.code in uses, uses: uses[r.code] ?? null });
  const key = "inv:" + guildId;
  const state = await kvGet(env, key);
  if (!state) { await kvPut(env, key, { uses, processed: [] }); report.notes.push("Now watching your invites. People who join from now on are tracked."); return report; }
  const delta = {};
  let total = 0;
  for (const [code, n] of Object.entries(uses)) {
    const d = n - (state.uses[code] ?? 0);
    if (d > 0) { delta[code] = d; total += d; }
  }
  if (total === 0) {                       // nobody joined: no member lookup, and no storage write unless invites changed
    if (JSON.stringify(uses) !== JSON.stringify(state.uses)) { state.uses = uses; await kvPut(env, key, state); }
    return report;
  }
  let members = [], after = "0";
  for (let page = 0; page < 5; page++) {
    const mr = await bot(env, "GET", `/guilds/${guildId}/members?limit=1000&after=${after}`);
    if (mr.status === 403) { report.error = "Turn on 'Server Members Intent' for the bot in the Discord Developer Portal (Bot tab), then try again."; return report; }
    if (!mr.ok) { report.error = "Discord error " + mr.status + " while reading members"; return report; }
    const batch = await mr.json();
    members = members.concat(batch);
    if (batch.length < 1000) break;
    after = batch[batch.length - 1].user.id;
  }
  const done = new Set(state.processed || []);
  const now = Date.now();
  const recent = members
    .filter((m) => m.user && !m.user.bot && !done.has(m.user.id) && now - Date.parse(m.joined_at) < 15 * 60000)
    .sort((a, b) => Date.parse(a.joined_at) - Date.parse(b.joined_at));
  const changed = Object.keys(delta);
  if (changed.length === 1 && recent.length === total) {
    const rule = rules.find((r) => r.code === changed[0]);
    if (rule) {
      for (const m of recent) {
        const g = await grantRole(env, guildId, m.user.id, rule.role);
        report.assigned.push({ user: m.user.id, label: rule.label, ok: g.ok, status: g.status });
      }
    } else report.notes.push("Someone joined through an invite that has no role.");
  } else {
    report.notes.push(`Could not tell which invite ${recent.length} new member(s) used (${total} invite use(s) changed), so no roles were given.`);
  }
  state.uses = uses;
  state.processed = [...(state.processed || []), ...recent.map((m) => m.user.id)].slice(-300);
  await kvPut(env, key, state);
  return report;
}

async function runScheduled(env) {
  if (!env.KV || !env.DISCORD_BOT_TOKEN) return;
  const ids = (await kvGet(env, "idx:invites")) || [];
  for (const id of ids.slice(0, 12)) {
    try {
      const guild = await kvGet(env, "guild:" + id);
      if (guild) await checkInvites(env, id, guild);
    } catch (_) { /* try again next round */ }
  }
}

const ZERO_DECIMAL = new Set(["JPY", "KRW", "VND", "CLP", "ISK", "UGX", "XAF", "XOF"]);
const minorToMajor = (amount, currency) => (ZERO_DECIMAL.has(currency) ? Number(amount) : Number(amount) / 100) || 0;
const NAME_KEY = /(^|[^a-z])(name|donor|from)([^a-z]|$)/i, NAME_BAD = /form|file|order|merchant|business|bank|upi|app|gateway|brand|plan|product|item/i;
const MSG_KEY = /message|msg|note|comment|wish|text|say/i;

// collect (label, value) text pairs from any JSON shape, including [{label, value}] lists
function collectPairs(obj, out = [], depth = 0) {
  if (depth > 6 || obj == null) return out;
  if (Array.isArray(obj)) { obj.forEach((x) => collectPairs(x, out, depth + 1)); return out; }
  if (typeof obj !== "object") return out;
  const label = ["label", "title", "field_name", "key", "name"].map((k) => obj[k]).find((v) => typeof v === "string" || (v && typeof v.custom === "string"));
  const value = ["value", "answer", "field_value"].map((k) => obj[k]).find((v) => typeof v === "string");
  if (label && value) out.push([typeof label === "string" ? label : label.custom, value]);
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === "string") out.push([k, v]);
    else if (v && typeof v === "object") {
      if (typeof v.value === "string" && !Array.isArray(v)) out.push([k, v.value]);          // stripe custom_fields[i].text.value
      collectPairs(v, out, depth + 1);
    }
  }
  return out;
}
function pickNameMessage(pairs) {
  let name = "", message = "";
  for (const [k, v] of pairs) {
    if (!v || !String(v).trim()) continue;
    if (!name && NAME_KEY.test(k) && !NAME_BAD.test(k)) name = v;
    else if (!message && MSG_KEY.test(k) && !/url|link/i.test(k)) message = v;
  }
  return { name, message };
}
function deepFind(obj, key, depth = 0) {
  if (depth > 6 || obj == null || typeof obj !== "object") return undefined;
  if (key in obj && obj[key] != null && typeof obj[key] !== "object") return obj[key];
  for (const v of Object.values(obj)) { const r = deepFind(v, key, depth + 1); if (r !== undefined) return r; }
  return undefined;
}
const mkTip = (id, name, message, value, currency) => ({
  id: String(id), name: clean(name, 40) || "Someone", message: clean(message, 300), value, currency, display: displayAmount(value, currency),
});

function parseStripe(ev) {
  if (!["checkout.session.completed", "checkout.session.async_payment_succeeded"].includes(ev.type)) return { ignored: ev.type };
  const o = (ev.data && ev.data.object) || {};
  if (o.payment_status !== "paid") return { ignored: "not paid yet" };
  const currency = String(o.currency || "usd").toUpperCase();
  // Stripe keeps a field's label and its answer in different places: key/label.custom ... text.value
  const pairs = (Array.isArray(o.custom_fields) ? o.custom_fields : []).map((f) => [
    (f.key || "") + " " + ((f.label && f.label.custom) || ""),
    String((f.text && f.text.value) ?? (f.numeric && f.numeric.value) ?? (f.dropdown && f.dropdown.value) ?? ""),
  ]);
  const f = pickNameMessage(pairs);
  return { tip: mkTip(o.id, f.name || (o.customer_details && o.customer_details.name), f.message, minorToMajor(o.amount_total, currency), currency) };
}
function parseCashfree(body) {
  const t = String(body.type || "").toLowerCase();
  if (!["payment_success_webhook", "payment_form_order_webhook"].includes(t)) return { ignored: t || "unknown" };
  const amount = Number(deepFind(body, "order_amount"));
  if (!(amount > 0)) return { ignored: "no amount" };
  const currency = String(deepFind(body, "order_currency") || "INR").toUpperCase();
  const f = pickNameMessage(collectPairs(body.data || body));
  const id = deepFind(body, "cf_payment_id") || deepFind(body, "order_id");
  if (!id) return { ignored: "no id" };
  return { tip: mkTip(id, f.name, f.message, amount, currency) };
}
function parseGeneric(body) {
  const value = Number(body.amount);
  if (!(value > 0)) return { ignored: "no amount" };
  return { tip: mkTip(body.id || crypto.randomUUID(), body.name, body.message, value, String(body.currency || "INR").toUpperCase()) };
}

async function bot(env, method, path, body) {
  return fetch(API + path, {
    method,
    headers: {
      Authorization: "Bot " + env.DISCORD_BOT_TOKEN,
      "Content-Type": "application/json",
      "User-Agent": "DiscordBot (https://github.com/Deba-dev/ChatDoom, 1.0)",
      "X-Audit-Log-Reason": "CHATDOOM role sync",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

async function exchange(env, code, redirectUri) {
  const r = await fetch(API + "/oauth2/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.DISCORD_CLIENT_ID, client_secret: env.DISCORD_CLIENT_SECRET,
      grant_type: "authorization_code", code, redirect_uri: redirectUri,
    }),
  });
  if (!r.ok) {
    let why = "";
    try { const j = await r.json(); why = j.error_description || j.error || ""; } catch (_) {}
    throw new Error("Discord refused the login (" + r.status + (why ? ": " + why : "") + ")");
  }
  return r.json();
}

function authorizeUrl(env, redirectUri, scope, state, extra = {}) {
  const p = new URLSearchParams({
    client_id: env.DISCORD_CLIENT_ID, response_type: "code", redirect_uri: redirectUri, scope, state, ...extra,
  });
  return "https://discord.com/oauth2/authorize?" + p;
}

async function grantRole(env, guildId, userId, roleId) {
  if (!roleId) return { ok: false, status: 0, skipped: true };
  const r = await bot(env, "PUT", `/guilds/${guildId}/members/${userId}/roles/${roleId}`);
  return { ok: r.status === 204 || r.status === 200, status: r.status };
}

// ---------------- pages (browser) ----------------
const loginProblem = (e) => page("Discord login failed",
  `<p>${esc(e.message)}</p><p>Check these, then try again:</p><ul>
   <li>DISCORD_CLIENT_SECRET is the <b>Client Secret</b> (OAuth2 tab), not the bot token</li>
   <li>DISCORD_CLIENT_ID is the long number under OAuth2 &gt; Client ID</li>
   <li>Both redirect links are saved in OAuth2 &gt; Redirects, exactly as in the guide</li></ul>
   <p>Open <code>/health</code> on this address to see which settings are missing.</p>`, 400);

function missingConfig(env) {
  const m = [];
  if (!env.KV || typeof env.KV.get !== "function") m.push("KV (storage)");
  for (const k of ["DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_BOT_TOKEN"]) if (!env[k]) m.push(k);
  return m;
}

function health(env) {
  const set = (k) => !!env[k];
  return json({
    storage_ok: !!(env.KV && typeof env.KV.get === "function"),
    DISCORD_CLIENT_ID: { set: set("DISCORD_CLIENT_ID"), looks_right: /^\d{17,20}$/.test(env.DISCORD_CLIENT_ID || "") },
    DISCORD_CLIENT_SECRET: { set: set("DISCORD_CLIENT_SECRET"), looks_right: (env.DISCORD_CLIENT_SECRET || "").length >= 28 },
    DISCORD_BOT_TOKEN: { set: set("DISCORD_BOT_TOKEN"), looks_right: (env.DISCORD_BOT_TOKEN || "").split(".").length === 3 },
    payments_storage_ok: !!env.DB,
    GOOGLE_OAUTH_CLIENT_ID: { set: set("GOOGLE_OAUTH_CLIENT_ID"), looks_right: (env.GOOGLE_OAUTH_CLIENT_ID || "").endsWith(".apps.googleusercontent.com") },
    GOOGLE_OAUTH_CLIENT_SECRET: { set: set("GOOGLE_OAUTH_CLIENT_SECRET") },
    TWITCH_CLIENT_ID: { set: set("TWITCH_CLIENT_ID"), looks_right: (env.TWITCH_CLIENT_ID || "").length >= 10 },
    TWITCH_CLIENT_SECRET: { set: set("TWITCH_CLIENT_SECRET") },
    PLATFORM_TOKEN_ENCRYPTION_KEY: { set: set("PLATFORM_TOKEN_ENCRYPTION_KEY"), looks_right: /^[A-Za-z0-9+/]{43}=$/.test(env.PLATFORM_TOKEN_ENCRYPTION_KEY || "") },
    WORKERS_AI: { set: !!(env.AI && typeof env.AI.run === "function") },
    note: "looks_right only checks the shape of the value, never shows it",
  });
}
const LOOPBACK = /^http:\/\/(?:127\.0\.0\.1|localhost):\d{2,5}(?:\/[\w\-./]*)?$/;

async function setupStart(env, origin, returnUrl) {
  if (returnUrl && !LOOPBACK.test(returnUrl)) return page("Cannot continue", "<p>The return address must be a program on this same PC.</p>", 400);
  const state = randomString(24, "abcdef0123456789");
  await kvPut(env, "state:" + state, { kind: "setup", ret: returnUrl || "" }, 600);
  return Response.redirect(
    authorizeUrl(env, origin + "/setup/callback", "bot identify", state, { permissions: "268436513" }), 302);
}

const backToApp = (ret, params) => Response.redirect(ret + (ret.includes("?") ? "&" : "?") + new URLSearchParams(params), 302);

async function setupCallback(env, origin, url) {
  const state = url.searchParams.get("state"), code = url.searchParams.get("code");
  const st = state && (await kvGet(env, "state:" + state));
  if (!st || st.kind !== "setup") return page("Link expired", "<p>Start again from the app's Discord page.</p>", 400);
  await env.KV.delete("state:" + state);
  if (!code) {                                                           // the person pressed Cancel on Discord's screen
    return st.ret ? backToApp(st.ret, { ok: "0", error: url.searchParams.get("error") || "cancelled" })
                  : page("Cancelled", "<p>The bot was not added.</p>", 400);
  }
  let tok;
  try { tok = await exchange(env, code, origin + "/setup/callback"); }
  catch (e) { return st.ret ? backToApp(st.ret, { ok: "0", error: String(e.message).slice(0, 120) }) : loginProblem(e); }
  if (!tok.guild) {
    return st.ret ? backToApp(st.ret, { ok: "0", error: "No server was selected" })
                  : page("No server selected", "<p>Pick a server on the Discord screen and try again.</p>", 400);
  }
  const guildId = tok.guild.id;
  const old = await kvGet(env, "guild:" + guildId);
  if (old) await env.KV.delete("token:" + old.token);
  const token = newToken();
  await kvPut(env, "guild:" + guildId, { token, guildName: tok.guild.name, config: old ? old.config : {} });
  await kvPut(env, "token:" + token, guildId);
  cache.delete("g:" + guildId);
  if (old) cache.delete("t:" + old.token);
  if (st.ret) return backToApp(st.ret, { ok: "1", token, guild: tok.guild.name, gid: guildId });      // the app receives the key by itself
  return page("Bot added to " + tok.guild.name,
    `<p>Copy this <b>server key</b> into CHATDOOM (Discord page). Keep it private:</p><code>${esc(token)}</code>
     <p>You can now close this page.</p>`);
}

async function linkStart(env, origin, guildId) {
  if (!(await kvGet(env, "guild:" + guildId))) return page("Unknown server", "<p>This link is not set up.</p>", 404);
  const state = randomString(24, "abcdef0123456789");
  await kvPut(env, "state:" + state, { kind: "link", guildId }, 600);
  return Response.redirect(authorizeUrl(env, origin + "/link/callback", "identify", state), 302);
}

async function linkCallback(env, origin, url) {
  const state = url.searchParams.get("state"), code = url.searchParams.get("code");
  const st = state && (await kvGet(env, "state:" + state));
  if (!st || st.kind !== "link" || !code) return page("Link expired", "<p>Open the link from the streamer again.</p>", 400);
  await env.KV.delete("state:" + state);
  let tok;
  try { tok = await exchange(env, code, origin + "/link/callback"); }
  catch (e) { return loginProblem(e); }
  const me = await (await fetch(API + "/users/@me", { headers: { Authorization: "Bearer " + tok.access_token } })).json();
  const member = await bot(env, "GET", `/guilds/${st.guildId}/members/${me.id}`);
  if (member.status !== 200)
    return page("Join the server first", "<p>You are not in the streamer's Discord server yet. Join it, then open this link again.</p>", 403);
  const linkCode = newCode();
  await kvPut(env, "code:" + linkCode, { guildId: st.guildId, discordId: me.id, name: me.global_name || me.username }, 900);
  return page("Almost done, " + (me.global_name || me.username),
    `<p>Type this in the streamer's live chat within 15 minutes:</p><div class="big">!link ${esc(linkCode)}</div>
     <p>It links your chat name to your Discord account. You can close this page.</p>`);
}

// ---------------- payment webhook (called by the streamer's gateway) ----------------
const GATEWAYS = ["razorpay", "stripe", "cashfree", "generic"];

async function paymentHook(request, env, gateway, hookId) {
  const guildId = await cached("h:" + hookId, () => kvGet(env, "hook:" + hookId));
  const guild = guildId && (await cached("g:" + guildId, () => kvGet(env, "guild:" + guildId)));
  const secret = guild && guild.config && guild.config[gateway + "Secret"];
  if (!secret) return json({ error: "unknown hook" }, 404);
  const raw = await request.text();
  const h = (n) => request.headers.get(n) || "";
  let body;
  try { body = JSON.parse(raw); } catch (_) { body = null; }

  let verified = false, result;
  if (gateway === "razorpay") {
    const sig = h("X-Razorpay-Signature").toLowerCase();
    verified = !!sig && safeEqual(hex(await hmacRaw(secret, raw)), sig);
  } else if (gateway === "stripe") {
    const parts = h("Stripe-Signature").split(",").map((x) => x.trim().split("="));
    const t = (parts.find((x) => x[0] === "t") || [])[1];
    const sigs = parts.filter((x) => x[0] === "v1").map((x) => x[1]);
    if (t && Math.abs(Date.now() / 1000 - Number(t)) <= 300) {
      const want = hex(await hmacRaw(secret, t + "." + raw));
      verified = sigs.some((x) => safeEqual(want, String(x).toLowerCase()));
    }
  } else if (gateway === "cashfree") {
    const ts = h("x-webhook-timestamp"), sig = h("x-webhook-signature");
    verified = !!ts && !!sig && safeEqual(b64(await hmacRaw(secret, ts + raw)), sig);
  } else {
    verified = safeEqual(h("X-ChatVoice-Secret"), secret) || (!!body && typeof body.secret === "string" && safeEqual(body.secret, secret));
  }
  if (!verified) return json({ error: "bad signature" }, 400);
  if (!body) return json({ error: "bad json" }, 400);

  if (gateway === "razorpay") {
    if (body.event !== "payment.captured") return json({ ok: true, ignored: body.event || "unknown" });
    const pay = body.payload && body.payload.payment && body.payload.payment.entity;
    if (!pay || !pay.id) return json({ ok: true, ignored: "no payment" });
    result = { tip: parseRazorpay(pay) };
  } else if (gateway === "stripe") result = parseStripe(body);
  else if (gateway === "cashfree") result = parseCashfree(body);
  else result = parseGeneric(body);
  if (!result.tip) return json({ ok: true, ignored: result.ignored });

  const t = result.tip;
  const d = await db(env);
  await d.prepare("INSERT OR IGNORE INTO tips (guild, pay_id, ts, name, message, amount, currency, display) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
    .bind(guildId, t.id, Math.floor(Date.now() / 1000), t.name, t.message, t.value, t.currency, t.display).run();
  await d.prepare("DELETE FROM tips WHERE ts < ?").bind(Math.floor(Date.now() / 1000) - 3 * 86400).run();
  return json({ ok: true });
}

// ---------------- API (desktop app) ----------------
async function api(request, env, url) {
  const auth = request.headers.get("Authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  const guildId = token && (await cached("t:" + token, () => kvGet(env, "token:" + token)));
  if (!guildId) return json({ error: "bad server key" }, 401);
  const guild = await cached("g:" + guildId, () => kvGet(env, "guild:" + guildId));
  const route = request.method + " " + url.pathname;
  const body = request.method === "GET" ? {} : await request.json().catch(() => ({}));

  const publicConfig = () => {
    const { razorpaySecret, stripeSecret, cashfreeSecret, genericSecret, hookId, ...rest } = guild.config || {};
    const hookUrls = {};
    for (const g of GATEWAYS) hookUrls[g] = hookId ? url.origin + "/hook/" + g + "/" + hookId : "";
    return { ...rest, hasRazorpaySecret: !!razorpaySecret, hasStripeSecret: !!stripeSecret, hasCashfreeSecret: !!cashfreeSecret,
      hasGenericSecret: !!genericSecret, hookUrl: hookUrls.razorpay, hookUrls };
  };

  if (route === "POST /api/translate") {
    if (!env.AI || typeof env.AI.run !== "function")
      return json({ error: "Translation is not enabled on this Cloudflare Worker. Add the Workers AI binding and deploy again." }, 503);
    const text = typeof body.text === "string" ? body.text.trim() : "";
    const sourceLang = typeof body.source_lang === "string" ? body.source_lang.toLowerCase() : "";
    if (!text || text.length > 500 || !TRANSLATION_LANGUAGES.has(sourceLang))
      return json({ error: "Translation needs a message of 1-500 characters and a supported source language." }, 400);
    if (sourceLang === "en") return json({ translation: text, unchanged: true });

    const day = new Date().toISOString().slice(0, 10);
    const quotaKey = "translate:usage:" + day;
    const used = parseInt(await env.KV.get(quotaKey) || "0", 10) || 0;
    if (used >= DAILY_TRANSLATION_LIMIT)
      return json({ error: "The shared daily translation limit has been reached. It resets at midnight UTC." }, 429);
    await env.KV.put(quotaKey, String(used + 1), { expirationTtl: 172800 });

    const result = await env.AI.run("@cf/meta/m2m100-1.2b", {
      text, source_lang: sourceLang, target_lang: "en",
    });
    const translated = typeof result?.translation === "string" ? result.translation.trim() : "";
    if (!translated) return json({ error: "Cloudflare AI did not return a translation." }, 502);
    return json({ translation: translated });
  }

  if (route === "GET /api/config") return json({ guildId, guildName: guild.guildName, config: publicConfig() });

  if (route === "PUT /api/config") {
    const roleOk = (v) => v === "" || v == null || /^\d{5,25}$/.test(String(v));
    const prev = guild.config || {};
    const pick = (k) => (body[k] === undefined ? prev[k] || "" : body[k] || "");   // fields that are not sent keep their old value
    const c = {
      verifiedRole: pick("verifiedRole"), regularRole: pick("regularRole"), supporterRole: pick("supporterRole"),
      regularMsgs: Math.min(100000, Math.max(1, parseInt(body.regularMsgs === undefined ? prev.regularMsgs : body.regularMsgs, 10) || 50)),
    };
    if (![c.verifiedRole, c.regularRole, c.supporterRole].every(roleOk)) return json({ error: "bad role id" }, 400);
    guild.config = { ...(guild.config || {}), ...c };
    if (body.inviteRules !== undefined) {
      const rules = [];
      for (const r of (Array.isArray(body.inviteRules) ? body.inviteRules : []).slice(0, 6)) {
        const code = inviteCode(r && r.code);
        if (!code || !/^\d{5,25}$/.test(String((r && r.role) || ""))) return json({ error: "bad invite rule: check the invite link and the role" }, 400);
        rules.push({ code, role: String(r.role), label: clean((r && r.label) || "Invite", 20) });
      }
      guild.config.inviteRules = rules;
      const idx = (await kvGet(env, "idx:invites")) || [];
      const has = idx.includes(guildId);
      if (rules.length && !has) await kvPut(env, "idx:invites", [...idx, guildId]);
      if (!rules.length && has) await kvPut(env, "idx:invites", idx.filter((x) => x !== guildId));
    }
    for (const g of GATEWAYS) {
      const v = body[g + "Secret"];
      if (typeof v === "string" && v.trim()) guild.config[g + "Secret"] = v.trim().slice(0, 200);
    }
    if (body.clearRazorpay) delete guild.config.razorpaySecret;
    if (GATEWAYS.includes(body.clearGateway)) delete guild.config[body.clearGateway + "Secret"];
    if (GATEWAYS.some((g) => guild.config[g + "Secret"]) && !guild.config.hookId) {
      guild.config.hookId = newToken().slice(0, 24);
      await kvPut(env, "hook:" + guild.config.hookId, guildId);
    }
    await kvPut(env, "guild:" + guildId, guild);
    cache.set("g:" + guildId, { exp: Date.now() + 30000, val: guild });
    return json({ ok: true, config: publicConfig() });
  }

  if (route === "GET /api/roles") {
    const r = await bot(env, "GET", `/guilds/${guildId}/roles`);
    if (!r.ok) return json({ error: "could not read roles (is the bot still in the server?)" }, 502);
    const roles = (await r.json()).filter((x) => !x.managed && x.name !== "@everyone")
      .sort((a, b) => b.position - a.position).map((x) => ({ id: x.id, name: x.name }));
    return json({ roles });
  }

  if (route === "POST /api/discord/setup") {
    const r = await discordSetup(env, guildId, guild, body);
    return json(r.data, r.status);
  }

  if (route === "POST /api/invites/check") return json(await checkInvites(env, guildId, guild));

  if (route === "GET /api/links") {
    const links = (await kvGet(env, "links:" + guildId)) || {};
    return json({ keys: Object.keys(links) });
  }

  if (route === "POST /api/claim") {
    const { code, platform, uid, name } = body;
    if (!PLATFORMS.includes(platform) || !uid || String(uid).length > 64) return json({ error: "bad request" }, 400);
    const rec = await kvGet(env, "code:" + String(code || "").toUpperCase());
    if (!rec || rec.guildId !== guildId) return json({ error: "code not found or expired" }, 404);
    await env.KV.delete("code:" + String(code).toUpperCase());
    const links = (await kvGet(env, "links:" + guildId)) || {};
    const key = platform + ":" + uid;
    links[key] = rec.discordId;
    await kvPut(env, "links:" + guildId, links);
    const g = await grantRole(env, guildId, rec.discordId, guild.config.verifiedRole);
    return json({ ok: true, key, discordName: rec.name, roleGranted: g.ok, roleStatus: g.status });
  }

  // The desktop app counts messages itself and only calls this when a viewer reaches a role threshold
  if (route === "POST /api/grant") {
    const { platform, uid, role } = body;
    if (!PLATFORMS.includes(platform) || !uid || !["regular", "supporter"].includes(role)) return json({ error: "bad request" }, 400);
    const links = (await kvGet(env, "links:" + guildId)) || {};
    const discordId = links[platform + ":" + uid];
    if (!discordId) return json({ ok: false, error: "viewer is not linked" }, 404);
    const roleId = role === "regular" ? guild.config.regularRole : guild.config.supporterRole;
    const g = await grantRole(env, guildId, discordId, roleId);
    return json({ ok: g.ok, role, status: g.status, skipped: !!g.skipped });
  }

  // Payment alerts waiting for the app. after=-1 just returns the newest number (so old tips are not replayed)
  if (route === "GET /api/events") {
    const d = await db(env);
    const after = parseInt(url.searchParams.get("after") || "0", 10);
    if (after < 0) {
      const row = await d.prepare("SELECT MAX(seq) AS m FROM tips WHERE guild = ?").bind(guildId).first();
      return json({ events: [], latest: (row && row.m) || 0 });
    }
    const rs = await d.prepare("SELECT seq, pay_id, ts, name, message, amount, currency, display FROM tips WHERE guild = ? AND seq > ? ORDER BY seq LIMIT 20").bind(guildId, after).all();
    const events = (rs.results || []).map((r) => ({ seq: r.seq, id: r.pay_id, ts: r.ts, name: r.name, message: r.message, value: r.amount, currency: r.currency, display: r.display }));
    return json({ events, latest: events.length ? events[events.length - 1].seq : after });
  }

  return json({ error: "not found" }, 404);
}

async function route(request, env, url) {
  const origin = url.origin, p = url.pathname;
  const publicPage = handlePublicPage(request, url);
  if (publicPage) return publicPage;
  if (p.startsWith("/platform-auth/")) {
    const result = await handlePlatformAuth(request, env, url);
    if (result) return result;
  }
  if (p === "/health") return health(env);
  const missing = missingConfig(env);
  if (missing.length)
    return p.startsWith("/api/")
      ? json({ error: "cloud not set up: missing " + missing.join(", ") }, 500)
      : page("Cloud setup incomplete", "<p>These settings are missing on the cloud server:</p><code>" + esc(missing.join(", ")) +
          "</code><p>Add them with <code>npx wrangler secret put NAME</code>, then run <code>npx wrangler deploy</code>.</p>", 500);
  if (request.method === "POST" && p.startsWith("/hook/")) {
    const [, , gw, id] = p.split("/");
    if (GATEWAYS.includes(gw) && id) return paymentHook(request, env, gw, id);
  }
  if (p === "/setup") return setupStart(env, origin, url.searchParams.get("return"));
  if (p === "/setup/callback") return setupCallback(env, origin, url);
  if (p === "/link/callback") return linkCallback(env, origin, url);
  if (p.startsWith("/link/")) return linkStart(env, origin, p.slice(6));
  if (p.startsWith("/api/")) return api(request, env, url);
  return new Response("Not found", { status: 404 });
}

export default {
  async scheduled(event, env, ctx) {
    const p = runScheduled(env);
    if (ctx && ctx.waitUntil) ctx.waitUntil(p);
    return p;
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      return await route(request, env, url);   // 'await' is what makes the catch below work
    } catch (e) {
      const msg = String((e && e.message) || e);
      return url.pathname.startsWith("/api/") || url.pathname.startsWith("/platform-auth/")
        ? json({ error: msg }, 500)
        : page("Something went wrong", "<p>" + esc(msg) + "</p>", 500);
    }
  },
};
