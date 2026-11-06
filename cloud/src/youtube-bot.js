// The CHATDOOM YouTube moderator bot, running on this Worker (free, never sleeps) instead of a separate Node host.
// Same /v1 API and the same signed tokens as youtube-bot/v1.mjs, so streamers who verified before keep working
// as long as YT_BOT_KEY has the old BOT_ADMIN_KEY value.
//
// Secrets (npx wrangler secret put NAME):
//   YT_BOT_KEY            long random private value; signs the streamers' tokens and unlocks /v1/admin
//   YT_BOT_CLIENT_ID      Google OAuth client of the bot's Google Cloud project
//   YT_BOT_CLIENT_SECRET
//   YT_BOT_REFRESH_TOKEN  the bot account's login (copy it from Render, or get a new one at /v1/admin)
// Optional plain vars: YT_BOT_HANDLE, YT_BOT_TITLE (shown before YouTube can be asked)
//
// Storage: KV holds the 15-minute verification codes, the per-channel daily counters and the cached access token.

const API = "https://www.googleapis.com/youtube/v3";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl";
const CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
const TOKEN_DAYS = 90;
const MAX_ITEMS = 20;
const MAX_DAILY_ACTIONS = 150;
// What viewers are told. A fixed list, so the bot never posts text the app sent it.
const REASONS = { "blocked word": "it had a blocked word", link: "links are not allowed here",
                  spam: "it looked like spam", repeat: "it repeated the same message" };
const reasonLine = (name, reason) => `@${name} your message was removed because ${REASONS[reason] || "it broke the chat rules"}.`;
const timeoutLine = (name, secs) => `@${name} you are timed out for ${secs >= 120 ? Math.round(secs / 60) + " minutes" : secs + " seconds"} for breaking the chat rules repeatedly.`;
const chatName = (m) => String(m?.name || "").replace(/^@+/, "").slice(0, 40);

const enc = new TextEncoder();
const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
const fail = (status, message, extra = {}) => json({ ok: false, error: message, ...extra }, status);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const page = (title, body, status = 200) => new Response(
  `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(title)}</title>` +
  `<body style="font:16px system-ui,sans-serif;background:#10101c;color:#eee;max-width:640px;margin:40px auto;padding:0 16px">` +
  `<h2>${esc(title)}</h2>${body}</body>`, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
const validVideo = (v) => /^[\w-]{11}$/.test(String(v || ""));
const pacificDate = (t) => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles" }).format(new Date(t));

export const normalizeText = (text) =>
  String(text || "")
    .replace(/:[A-Za-z_][^:\s]{0,60}:/g, "")
    .replace(/[\u{1F000}-\u{1FAFF}←-⇿⌀-⏿■-◿☀-➿⤀-⥿⬀-⯿️‍⃣]/gu, "")
    .replace(/\s+/g, "")
    .toLocaleLowerCase();

function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function unb64url(text) {
  const s = atob(String(text).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}
const hmacKey = (raw) => crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);

// Same derivation as Node's createHmac("sha256", key).update("chatvoice-session-v1")
async function sessionKey(env) {
  const derived = await crypto.subtle.sign("HMAC", await hmacKey(enc.encode(env.YT_BOT_KEY || "")), enc.encode("chatvoice-session-v1"));
  return hmacKey(derived);
}

export async function makeToken(env, channelId, now = Date.now()) {
  const body = b64url(enc.encode(JSON.stringify({ ch: channelId, exp: now + TOKEN_DAYS * 86_400_000, v: 1 })));
  return `${body}.${b64url(await crypto.subtle.sign("HMAC", await sessionKey(env), enc.encode(body)))}`;
}

export async function readToken(env, raw, now = Date.now()) {
  const [body, sig] = String(raw || "").split(".");
  if (!body || !sig) return null;
  try {
    if (!(await crypto.subtle.verify("HMAC", await sessionKey(env), unb64url(sig), enc.encode(body)))) return null;   // constant time
    const p = JSON.parse(new TextDecoder().decode(unb64url(body)));
    return p.exp > now && /^UC[\w-]{20,30}$/.test(p.ch || "") ? p : null;
  } catch { return null; }
}

// Kept per Worker instance: losing them only costs an extra YouTube lookup.
const videos = new Map();       // videoId -> { at, channelId, channelTitle, chatId }
const buffers = new Map();      // chatId -> { items, pageToken, at, done:Set }
const rates = new Map();        // key -> { n, reset }
let botInfo = null;

function limited(key, max, windowMs = 60_000) {
  const t = Date.now();
  const r = rates.get(key);
  if (!r || r.reset < t) { rates.set(key, { n: 1, reset: t + windowMs }); return false; }
  r.n += 1;
  if (rates.size > 2000) for (const [k, v] of rates) if (v.reset < t) rates.delete(k);
  return r.n > max;
}

export function missingBotConfig(env) {
  return ["YT_BOT_KEY", "YT_BOT_CLIENT_ID", "YT_BOT_CLIENT_SECRET", "YT_BOT_REFRESH_TOKEN"].filter((k) => !env[k]).concat(env.KV ? [] : ["KV"]);
}

async function accessToken(env) {
  const cached = await env.KV.get("ytbot:access");
  if (cached) return cached;
  const r = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: env.YT_BOT_CLIENT_ID, client_secret: env.YT_BOT_CLIENT_SECRET,
                                refresh_token: env.YT_BOT_REFRESH_TOKEN, grant_type: "refresh_token" }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d.access_token) throw new Error(d.error_description || "Google token refresh failed");
  await env.KV.put("ytbot:access", d.access_token, { expirationTtl: Math.max(60, Number(d.expires_in || 3600) - 120) });
  return d.access_token;
}

// For the status page: can the bot still sign in to Google? Uses no YouTube API quota.
export async function botSignedIn(env) {
  if (missingBotConfig(env).length) return false;
  const token = await accessToken(env);
  const r = await fetch(`https://oauth2.googleapis.com/tokeninfo?access_token=${encodeURIComponent(token)}`);
  return r.ok;
}

async function api(env, url, options = {}) {
  const r = await fetch(url, { ...options, headers: { authorization: `Bearer ${await accessToken(env)}`, ...(options.headers || {}) } });
  const d = r.status === 204 ? {} : await r.json().catch(() => ({}));
  if (!r.ok) {
    const reason = d.error?.errors?.[0]?.reason || "";
    const e = new Error(d.error?.message || `YouTube API returned ${r.status}`);
    e.status = /quotaExceeded|dailyLimitExceeded|rateLimitExceeded/.test(reason) ? 429 : r.status;
    throw e;
  }
  return d;
}

async function videoMeta(env, videoId, fresh = false) {
  const cached = videos.get(videoId);
  if (cached && !fresh && Date.now() - cached.at < 600_000) return cached;
  const d = await api(env, `${API}/videos?part=snippet,liveStreamingDetails&id=${encodeURIComponent(videoId)}`);
  const item = d.items?.[0];
  if (!item) { const e = new Error("Video not found"); e.status = 404; throw e; }
  const meta = { at: Date.now(), channelId: item.snippet?.channelId, channelTitle: item.snippet?.channelTitle || "",
                 chatId: item.liveStreamingDetails?.activeLiveChatId || null };
  videos.set(videoId, meta);
  if (videos.size > 300) videos.clear();
  return meta;
}

async function bot(env) {
  if (botInfo) return botInfo;
  const d = await api(env, `${API}/channels?part=snippet&mine=true`);
  const c = d.items?.[0];
  botInfo = c ? { channelId: c.id, title: c.snippet?.title || "", handle: c.snippet?.customUrl || "" } : null;
  return botInfo;
}

async function pull(env, chatId) {
  let b = buffers.get(chatId);
  if (!b) { b = { items: [], pageToken: null, at: 0, done: new Set() }; buffers.set(chatId, b); }
  if (b.at && Date.now() - b.at < 1500) return b;
  for (let i = 0; i < 3; i++) {
    const q = new URLSearchParams({ liveChatId: chatId, part: "snippet,authorDetails", maxResults: "200" });
    if (b.pageToken) q.set("pageToken", b.pageToken);
    const d = await api(env, `${API}/liveChat/messages?${q}`);
    for (const m of d.items || []) {
      b.items.push({ id: m.id, channelId: m.authorDetails?.channelId, name: m.authorDetails?.displayName || "", text: m.snippet?.displayMessage || "",
                     mod: Boolean(m.authorDetails?.isChatModerator || m.authorDetails?.isChatOwner) });
    }
    b.pageToken = d.nextPageToken || b.pageToken;
    if ((d.items || []).length < 200) break;
  }
  if (b.items.length > 400) b.items = b.items.slice(-400);
  b.at = Date.now();
  if (buffers.size > 100) buffers.clear();
  return b;
}

function findMessage(b, item) {
  const mine = b.items.filter((m) => m.channelId === item.channelId && !b.done.has(m.id));
  const want = normalizeText(item.text);
  for (let i = mine.length - 1; i >= 0; i--) if (normalizeText(mine[i].text) === want) return mine[i];
  return mine.length === 1 ? mine[0] : null;      // only one recent message from that viewer: it must be it
}

const actionKey = (ch) => `ytbot:act:${ch}:${pacificDate(Date.now())}`;
const actionsUsed = async (env, ch) => Number(await env.KV.get(actionKey(ch))) || 0;
async function addAction(env, ch) {
  const n = (await actionsUsed(env, ch)) + 1;
  await env.KV.put(actionKey(ch), String(n), { expirationTtl: 172_800 });
  return n;
}

async function readBody(request) {
  try { return await request.json(); } catch { const e = new Error("Send a JSON body."); e.status = 400; throw e; }
}

// ---------- routes ----------
async function info(env) {
  let authorized = false, b = null;
  if (!missingBotConfig(env).length) { try { b = await bot(env); authorized = Boolean(b); } catch { authorized = false; } }
  return json({ ok: true, version: 1, authorized, host: "cloudflare",
    bot: b ? { title: b.title, handle: b.handle, channelId: b.channelId } : { title: env.YT_BOT_TITLE || "", handle: env.YT_BOT_HANDLE || "", channelId: "" },
    dailyMax: MAX_DAILY_ACTIONS });
}

async function verifyStart(request, env, ip) {
  const { videoId } = await readBody(request);
  if (!validVideo(videoId)) return fail(400, "Send the 11-character video ID of your live stream.");
  if (limited(`vs:${ip}`, 12)) return fail(429, "Too many tries. Wait a minute.");
  const meta = await videoMeta(env, videoId, true);
  if (!meta.chatId) return fail(409, "That video is not live right now. Start your stream first.");
  let code = "CV-";
  const random = crypto.getRandomValues(new Uint32Array(6));
  for (const n of random) code += CODE_ALPHABET[n % CODE_ALPHABET.length];
  await env.KV.put(`ytbot:code:${videoId}`, JSON.stringify({ code, channelId: meta.channelId, chatId: meta.chatId, title: meta.channelTitle }),
                   { expirationTtl: 900 });
  return json({ ok: true, code, channelId: meta.channelId, channelTitle: meta.channelTitle, expiresIn: 900 });
}

async function verifyCheck(request, env, ip) {
  const { videoId } = await readBody(request);
  if (!validVideo(videoId)) return fail(400, "Send the 11-character video ID of your live stream.");
  if (limited(`vc:${ip}`, 40)) return fail(429, "Too many tries. Wait a minute.");
  const p = JSON.parse((await env.KV.get(`ytbot:code:${videoId}`)) || "null");
  if (!p) return fail(410, "That code expired. Press verify again to get a new one.");
  const d = await api(env, `${API}/liveChat/messages?${new URLSearchParams({ liveChatId: p.chatId, part: "snippet,authorDetails", maxResults: "500" })}`);
  const found = (d.items || []).some((m) => String(m.snippet?.displayMessage || "").toUpperCase().includes(p.code) && m.authorDetails?.channelId === p.channelId);
  if (!found) return json({ ok: false, waiting: true });
  await env.KV.delete(`ytbot:code:${videoId}`);
  return json({ ok: true, token: await makeToken(env, p.channelId), channelId: p.channelId, channelTitle: p.title || "" });
}

async function moderate(request, env) {
  const tok = await readToken(env, (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, ""));
  if (!tok) return fail(401, "Your channel is not verified (or the verification expired). Verify it again in CHATDOOM.");
  if (limited(`mod:${tok.ch}`, 120)) return fail(429, "Slow down: too many moderation requests.");
  const body = await readBody(request);
  if (!validVideo(body.videoId)) return fail(400, "Missing live video ID.");
  const items = Array.isArray(body.items) ? body.items.slice(0, MAX_ITEMS) : [];
  const meta = await videoMeta(env, body.videoId);
  if (meta.channelId !== tok.ch) return fail(403, "That live stream belongs to a different channel than the one you verified.");
  if (!meta.chatId) return fail(409, "The stream is not live.");
  const limit = Math.min(MAX_DAILY_ACTIONS, Math.max(1, Math.floor(Number(body.limit) || 60)));
  const dry = body.dryRun === true;
  const explain = body.explain === true;
  const notes = [], results = [];
  let used = await actionsUsed(env, tok.ch);
  const b = await pull(env, meta.chatId);
  // Tells the viewer why, at most once a minute each. A failure here never undoes or stops the moderation itself.
  const tell = async (channelId, kind, name, messageText) => {
    if (!explain || !name || used >= limit || limited(`tell:${meta.chatId}:${channelId}:${kind}`, 1)) return false;
    try {
      await api(env, `${API}/liveChat/messages?part=snippet`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ snippet: { liveChatId: meta.chatId, type: "textMessageEvent", textMessageDetails: { messageText } } }),
      });
      used = await addAction(env, tok.ch);
      return true;
    } catch (error) {
      notes.push(`Could not post the reason in chat: ${String(error.message).slice(0, 80)}`);
      return false;
    }
  };
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    const who = String(it.author || "viewer").slice(0, 40);
    try {
      if (!/^UC[\w-]{20,30}$/.test(String(it.channelId || ""))) continue;
      if (it.action === "timeout") {
        const secs = Math.min(3600, Math.max(10, Math.floor(Number(it.seconds) || 300)));
        if (dry) { notes.push(`TEST MODE: would time out ${who} for ${secs} seconds`); results.push({ i, outcome: "test" }); continue; }
        if (used >= limit) { notes.push("Daily moderation limit reached - no more actions today"); results.push({ i, outcome: "limit" }); break; }
        await api(env, `${API}/liveChat/bans?part=snippet`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ snippet: { liveChatId: meta.chatId, type: "temporary", banDurationSeconds: secs, bannedUserDetails: { channelId: it.channelId } } }),
        });
        used = await addAction(env, tok.ch);
        notes.push(`Timed out ${who} for ${secs} seconds`);
        const name = chatName(b.items.findLast((m) => m.channelId === it.channelId));
        results.push({ i, outcome: "done", told: await tell(it.channelId, "timeout", name, timeoutLine(name, secs)) });
        continue;
      }
      const m = findMessage(b, it);
      if (!m) { notes.push(`Could not find ${who}'s message (it may be too old)`); results.push({ i, outcome: "missing" }); continue; }
      if (m.mod) { results.push({ i, outcome: "protected" }); continue; }      // never touch moderators or the streamer
      if (dry) { notes.push(`TEST MODE: would delete ${who}'s message (${String(it.reason || "rule").slice(0, 30)})`); results.push({ i, outcome: "test" }); continue; }
      if (used >= limit) { notes.push("Daily moderation limit reached - no more actions today"); results.push({ i, outcome: "limit" }); break; }
      await api(env, `${API}/liveChat/messages?id=${encodeURIComponent(m.id)}`, { method: "DELETE" });
      b.done.add(m.id);
      used = await addAction(env, tok.ch);
      notes.push(`Deleted ${who}'s message (${String(it.reason || "rule").slice(0, 30)})`);
      const name = chatName(m);
      results.push({ i, outcome: "done", told: await tell(it.channelId, "delete", name, reasonLine(name, it.reason)) });
    } catch (error) {
      results.push({ i, outcome: "failed", detail: String(error.message).slice(0, 80) });
      if (error.status === 429) { notes.push("The shared YouTube budget for today is used up. Moderation resumes tomorrow."); break; }
      if (error.status === 403) { notes.push("YouTube refused: the moderator bot is not a moderator of your channel yet. Add it in YouTube Studio."); break; }
      notes.push(`Could not act on ${who}'s message: ${String(error.message).slice(0, 80)}`);
    }
  }
  return json({ ok: true, notes, results, usedToday: used, limit });
}

// The bot posts one line in the streamer's live chat: command replies, timers and welcomes, like Nightbot.
async function say(request, env) {
  const tok = await readToken(env, (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, ""));
  if (!tok) return fail(401, "Your channel is not verified (or the verification expired). Verify it again in CHATDOOM.");
  if (limited(`say:${tok.ch}`, 20)) return fail(429, "Slow down: too many chat messages.");
  const body = await readBody(request);
  if (!validVideo(body.videoId)) return fail(400, "Missing live video ID.");
  const messageText = String(body.text || "").replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, 200);
  if (!messageText) return fail(400, "Type a message first.");
  const meta = await videoMeta(env, body.videoId);
  if (meta.channelId !== tok.ch) return fail(403, "That live stream belongs to a different channel than the one you verified.");
  if (!meta.chatId) return fail(409, "The stream is not live.");
  const limit = Math.min(MAX_DAILY_ACTIONS, Math.max(1, Math.floor(Number(body.limit) || 60)));
  if (await actionsUsed(env, tok.ch) >= limit) return fail(429, "The bot's daily limit is used up for this channel.");
  await api(env, `${API}/liveChat/messages?part=snippet`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ snippet: { liveChatId: meta.chatId, type: "textMessageEvent", textMessageDetails: { messageText } } }),
  });
  return json({ ok: true, usedToday: await addAction(env, tok.ch), limit });
}

// ---------- one-time bot login (only needed if you do not have the refresh token from Render any more) ----------
async function sameKey(env, given) {
  const k = await hmacKey(enc.encode("ytbot-admin"));
  const [a, b] = await Promise.all([crypto.subtle.sign("HMAC", k, enc.encode(String(given || ""))), crypto.subtle.sign("HMAC", k, enc.encode(env.YT_BOT_KEY || ""))]);
  const x = new Uint8Array(a), y = new Uint8Array(b);
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return Boolean(env.YT_BOT_KEY) && diff === 0;
}

async function admin(request, env, url) {
  if (request.method === "GET" && url.pathname === "/v1/admin") {
    const missing = missingBotConfig(env);
    return page("CHATDOOM YouTube bot", (missing.length ? `<p>Missing settings: <code>${esc(missing.join(", "))}</code></p>` : "<p>All settings are present.</p>") +
      `<p>Sign the bot's Google account in again (only needed for a new refresh token):</p>
       <form method="post" action="/v1/admin/authorize"><input type="password" name="key" placeholder="YT_BOT_KEY" style="width:100%;padding:8px">
       <p><button style="padding:8px 16px">Authorize bot Google account</button></p></form>
       <p style="opacity:.7">Google Cloud &gt; your OAuth client needs this redirect URI: <code>${esc(url.origin)}/v1/oauth/callback</code></p>`);
  }
  if (request.method === "POST" && url.pathname === "/v1/admin/authorize") {
    const form = await request.formData().catch(() => null);
    if (!form || !(await sameKey(env, form.get("key")))) return page("Wrong key", "<p>That is not YT_BOT_KEY.</p>", 403);
    if (!env.YT_BOT_CLIENT_ID) return page("Missing setting", "<p>Set YT_BOT_CLIENT_ID and YT_BOT_CLIENT_SECRET first.</p>", 500);
    const state = b64url(crypto.getRandomValues(new Uint8Array(24)));
    await env.KV.put(`ytbot:state:${state}`, "1", { expirationTtl: 600 });
    const q = new URLSearchParams({ client_id: env.YT_BOT_CLIENT_ID, redirect_uri: `${url.origin}/v1/oauth/callback`, response_type: "code",
                                    scope: SCOPE, access_type: "offline", prompt: "consent", state });
    return Response.redirect(`https://accounts.google.com/o/oauth2/v2/auth?${q}`, 302);
  }
  if (request.method === "GET" && url.pathname === "/v1/oauth/callback") {
    const state = url.searchParams.get("state") || "";
    if (!state || !(await env.KV.get(`ytbot:state:${state}`))) return page("Login expired", "<p>Start again from /v1/admin.</p>", 400);
    await env.KV.delete(`ytbot:state:${state}`);
    if (url.searchParams.get("error")) return page("Login cancelled", `<p>${esc(url.searchParams.get("error"))}</p>`, 400);
    const r = await fetch(TOKEN_URL, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: env.YT_BOT_CLIENT_ID, client_secret: env.YT_BOT_CLIENT_SECRET, code: url.searchParams.get("code") || "",
                                  grant_type: "authorization_code", redirect_uri: `${url.origin}/v1/oauth/callback` }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.refresh_token) return page("Login failed", `<p>${esc(d.error_description || d.error || "Google did not return a refresh token.")}</p>`, 502);
    await env.KV.delete("ytbot:access");
    botInfo = null;
    return page("Bot signed in", `<p>Copy this refresh token now (it is shown only once), then run <code>npx wrangler secret put YT_BOT_REFRESH_TOKEN</code> in the cloud folder and paste it:</p>
      <textarea readonly style="width:100%;height:110px">${esc(d.refresh_token)}</textarea><p>Treat it like a password.</p>`);
  }
  return null;
}

export async function handleYoutubeBot(request, env, url) {
  if (!url.pathname.startsWith("/v1/")) return null;
  const ip = request.headers.get("cf-connecting-ip") || "";
  const key = `${request.method} ${url.pathname}`;
  try {
    const adminPage = await admin(request, env, url);
    if (adminPage) return adminPage;
    if (key === "GET /v1/info") { if (limited(`info:${ip}`, 60)) return fail(429, "Too many requests."); return await info(env); }
    const missing = missingBotConfig(env);
    if (missing.length) return fail(503, "The YouTube bot is not set up on the cloud yet (missing " + missing.join(", ") + ").");
    if (key === "POST /v1/verify/start") return await verifyStart(request, env, ip);
    if (key === "POST /v1/verify/check") return await verifyCheck(request, env, ip);
    if (key === "POST /v1/moderate") return await moderate(request, env);
    if (key === "POST /v1/say") return await say(request, env);
    return fail(404, "Not found");
  } catch (error) {
    const status = [400, 403, 404, 409, 429].includes(error.status) ? error.status : 502;
    return fail(status, status === 502 ? "The YouTube bot could not reach YouTube. Try again in a moment." : error.message);
  }
}
