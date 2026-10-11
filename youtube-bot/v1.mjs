// Streamer-facing API used by the CHATDOOM desktop app.
//
// How it works (no per-streamer Google sign-in, no polling by this server):
//   1. The streamer adds the bot's YouTube channel as a moderator (manual step in YouTube Studio).
//   2. The app asks /v1/verify/start for a short code and the streamer types it in their OWN live chat.
//      /v1/verify/check sees that message from the channel that owns the video -> proves ownership
//      -> returns a signed token (no server storage needed, so a sleeping free host loses nothing).
//   3. The app reads chat itself (free, no quota) and calls /v1/moderate with the messages to remove.
//      The bot (a moderator) finds the message and deletes it. Cost: 1 unit to look, 50 to delete.
import { createHmac, randomInt, timingSafeEqual } from "node:crypto";

const API = "https://www.googleapis.com/youtube/v3";
const CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
const TOKEN_DAYS = 90;
const MAX_ITEMS = 20;
const MAX_DAILY_ACTIONS = 150;

const normalizeText = (text) =>
  String(text || "")
    .replace(/:[A-Za-z_][^:\s]{0,60}:/g, "")                                   // :emoji_codes:
    .replace(/[\u{1F000}-\u{1FAFF}\u2190-\u21FF\u2300-\u23FF\u25A0-\u25FF\u2600-\u27BF\u2900-\u297F\u2B00-\u2BFF\uFE0F\u200D\u20E3]/gu, "")
    .replace(/\s+/g, "")
    .toLocaleLowerCase();

export function createV1({ env, now, api, accessToken, readBody, json, actions, patchQuotaDay }) {
  const secret = createHmac("sha256", env.BOT_ADMIN_KEY || "").update("chatvoice-session-v1").digest();
  const pending = new Map();      // videoId -> { code, channelId, chatId, exp }
  const videos = new Map();       // videoId -> { at, channelId, channelTitle, chatId }
  const buffers = new Map();      // chatId -> { items, pageToken, at, done:Set }
  const rates = new Map();        // key -> { n, reset }
  let botInfo = null;

  // ---------- signed tokens ----------
  function makeToken(channelId) {
    const body = Buffer.from(JSON.stringify({ ch: channelId, exp: now() + TOKEN_DAYS * 86_400_000, v: 1 })).toString("base64url");
    const sig = createHmac("sha256", secret).update(body).digest("base64url");
    return `${body}.${sig}`;
  }
  function readToken(raw) {
    const [body, sig] = String(raw || "").split(".");
    if (!body || !sig) return null;
    const want = createHmac("sha256", secret).update(body).digest("base64url");
    const a = Buffer.from(sig), b = Buffer.from(want);
    if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
    try {
      const p = JSON.parse(Buffer.from(body, "base64url").toString());
      return p.exp > now() && /^UC[\w-]{20,30}$/.test(p.ch || "") ? p : null;
    } catch { return null; }
  }

  function limited(key, max, windowMs = 60_000) {
    const t = now();
    const r = rates.get(key);
    if (!r || r.reset < t) { rates.set(key, { n: 1, reset: t + windowMs }); return false; }
    r.n += 1;
    if (rates.size > 2000) for (const [k, v] of rates) if (v.reset < t) rates.delete(k);
    return r.n > max;
  }

  const fail = (res, status, message, extra = {}) => json(res, status, { ok: false, error: message, ...extra });
  const validVideo = (v) => /^[\w-]{11}$/.test(String(v || ""));

  async function videoMeta(videoId, fresh = false) {
    const cached = videos.get(videoId);
    if (cached && !fresh && now() - cached.at < 600_000) return cached;
    const d = await api(`${API}/videos?part=snippet,liveStreamingDetails&id=${encodeURIComponent(videoId)}`, await accessToken(), undefined, 1);
    const item = d.items?.[0];
    if (!item) { const e = new Error("Video not found"); e.status = 404; throw e; }
    const meta = { at: now(), channelId: item.snippet?.channelId, channelTitle: item.snippet?.channelTitle || "",
                   chatId: item.liveStreamingDetails?.activeLiveChatId || null };
    videos.set(videoId, meta);
    if (videos.size > 300) videos.clear();
    return meta;
  }

  async function bot() {
    if (botInfo) return botInfo;
    const d = await api(`${API}/channels?part=snippet&mine=true`, await accessToken(), undefined, 1);
    const c = d.items?.[0];
    botInfo = c ? { channelId: c.id, title: c.snippet?.title || "", handle: c.snippet?.customUrl || "" } : null;
    return botInfo;
  }

  async function pull(chatId) {
    let b = buffers.get(chatId);
    if (!b) { b = { items: [], pageToken: null, at: 0, done: new Set() }; buffers.set(chatId, b); }
    if (b.at && now() - b.at < 1500) return b;
    const access = await accessToken();
    for (let i = 0; i < 3; i++) {
      const q = new URLSearchParams({ liveChatId: chatId, part: "snippet,authorDetails", maxResults: "200" });
      if (b.pageToken) q.set("pageToken", b.pageToken);
      const d = await api(`${API}/liveChat/messages?${q}`, access, undefined, 1);
      for (const m of d.items || []) {
        b.items.push({ id: m.id, channelId: m.authorDetails?.channelId, text: m.snippet?.displayMessage || "",
                       mod: Boolean(m.authorDetails?.isChatModerator || m.authorDetails?.isChatOwner) });
      }
      b.pageToken = d.nextPageToken || b.pageToken;
      if ((d.items || []).length < 200) break;
    }
    if (b.items.length > 400) b.items = b.items.slice(-400);
    b.at = now();
    if (buffers.size > 100) buffers.clear();
    return b;
  }

  function findMessage(b, item) {
    const mine = b.items.filter((m) => m.channelId === item.channelId && !b.done.has(m.id));
    const want = normalizeText(item.text);
    for (let i = mine.length - 1; i >= 0; i--) if (normalizeText(mine[i].text) === want) return mine[i];
    return mine.length === 1 ? mine[0] : null;      // only one recent message from that viewer: it must be it
  }

  // ---------- routes ----------
  async function info(req, res) {
    let authorized = false, b = null;
    try { b = await bot(); authorized = Boolean(b); } catch { authorized = false; }
    return json(res, 200, { ok: true, version: 1, authorized,
      bot: b ? { title: b.title, handle: b.handle, channelId: b.channelId } : { title: env.BOT_TITLE || "", handle: env.BOT_HANDLE || "", channelId: "" },
      dailyMax: MAX_DAILY_ACTIONS });
  }

  async function verifyStart(req, res, ip) {
    const { videoId } = await readBody(req);
    if (!validVideo(videoId)) return fail(res, 400, "Send the 11-character video ID of your live stream.");
    if (limited(`vs:${ip}`, 12)) return fail(res, 429, "Too many tries. Wait a minute.");
    const meta = await videoMeta(videoId, true);
    if (!meta.chatId) return fail(res, 409, "That video is not live right now. Start your stream first.");
    let code = "CV-";
    for (let i = 0; i < 6; i++) code += CODE_ALPHABET[randomInt(CODE_ALPHABET.length)];
    pending.set(videoId, { code, channelId: meta.channelId, chatId: meta.chatId, exp: now() + 15 * 60_000 });
    return json(res, 200, { ok: true, code, channelId: meta.channelId, channelTitle: meta.channelTitle, expiresIn: 900 });
  }

  async function verifyCheck(req, res, ip) {
    const { videoId } = await readBody(req);
    if (!validVideo(videoId)) return fail(res, 400, "Send the 11-character video ID of your live stream.");
    if (limited(`vc:${ip}`, 40)) return fail(res, 429, "Too many tries. Wait a minute.");
    const p = pending.get(videoId);
    if (!p || p.exp < now()) return fail(res, 410, "That code expired. Press verify again to get a new one.");
    const d = await api(`${API}/liveChat/messages?${new URLSearchParams({ liveChatId: p.chatId, part: "snippet,authorDetails", maxResults: "500" })}`,
      await accessToken(), undefined, 1);
    const found = (d.items || []).some((m) => String(m.snippet?.displayMessage || "").toUpperCase().includes(p.code) && m.authorDetails?.channelId === p.channelId);
    if (!found) return json(res, 200, { ok: false, waiting: true });
    pending.delete(videoId);
    const meta = videos.get(videoId) || {};
    return json(res, 200, { ok: true, token: makeToken(p.channelId), channelId: p.channelId, channelTitle: meta.channelTitle || "" });
  }

  async function moderate(req, res) {
    const auth = (req.headers.authorization || "").replace(/^Bearer\s+/i, "");
    const tok = readToken(auth);
    if (!tok) return fail(res, 401, "Your channel is not verified (or the verification expired). Verify it again in CHATDOOM.");
    if (limited(`mod:${tok.ch}`, 120)) return fail(res, 429, "Slow down: too many moderation requests.");
    const body = await readBody(req);
    if (!validVideo(body.videoId)) return fail(res, 400, "Missing live video ID.");
    const items = Array.isArray(body.items) ? body.items.slice(0, MAX_ITEMS) : [];
    const meta = await videoMeta(body.videoId);
    if (meta.channelId !== tok.ch) return fail(res, 403, "That live stream belongs to a different channel than the one you verified.");
    if (!meta.chatId) return fail(res, 409, "The stream is not live.");
    const limit = Math.min(MAX_DAILY_ACTIONS, Math.max(1, Math.floor(Number(body.limit) || 60)));
    const dry = body.dryRun === true;
    const notes = [];
    const b = await pull(meta.chatId);
    for (const it of items) {
      const who = String(it.author || "viewer").slice(0, 40);
      try {
        if (!/^UC[\w-]{20,30}$/.test(String(it.channelId || ""))) continue;
        if (it.action === "timeout") {
          const secs = Math.min(3600, Math.max(10, Math.floor(Number(it.seconds) || 300)));
          if (dry) { notes.push(`TEST MODE: would time out ${who} for ${secs} seconds`); continue; }
          if (actions.get(tok.ch) >= limit) { notes.push("Daily moderation limit reached - no more actions today"); break; }
          await api(`${API}/liveChat/bans?part=snippet`, await accessToken(), {
            method: "POST", headers: { "content-type": "application/json" },
            body: JSON.stringify({ snippet: { liveChatId: meta.chatId, type: "temporary", banDurationSeconds: secs, bannedUserInfo: { channelId: it.channelId } } }),
          }, 50);
          actions.add(tok.ch);
          notes.push(`Timed out ${who} for ${secs} seconds`);
          continue;
        }
        const m = findMessage(b, it);
        if (!m) { notes.push(`Could not find ${who}'s message (it may be too old)`); continue; }
        if (m.mod) continue;                                                     // never touch moderators or the streamer
        if (dry) { notes.push(`TEST MODE: would delete ${who}'s message (${String(it.reason || "rule").slice(0, 30)})`); continue; }
        if (actions.get(tok.ch) >= limit) { notes.push("Daily moderation limit reached - no more actions today"); break; }
        await api(`${API}/liveChat/messages?id=${encodeURIComponent(m.id)}`, await accessToken(), { method: "DELETE" }, 50);
        b.done.add(m.id);
        actions.add(tok.ch);
        notes.push(`Deleted ${who}'s message (${String(it.reason || "rule").slice(0, 30)})`);
      } catch (error) {
        if (error.status === 429) { notes.push("The shared YouTube budget for today is used up. Moderation resumes tomorrow."); break; }
        if (error.status === 403) { notes.push("YouTube refused: the moderator bot is not a moderator of your channel yet. Add it in YouTube Studio."); break; }
        notes.push(`Could not act on ${who}'s message: ${String(error.message).slice(0, 80)}`);
      }
    }
    return json(res, 200, { ok: true, notes, usedToday: actions.get(tok.ch), limit });
  }

  return {
    handled(url) { return url.pathname.startsWith("/v1/"); },
    async handle(req, res, url) {
      const ip = String(req.headers["x-forwarded-for"] || req.socket.remoteAddress || "").split(",")[0].trim();
      const key = `${req.method} ${url.pathname}`;
      try {
        if (key === "GET /v1/info") { if (limited(`info:${ip}`, 60)) return fail(res, 429, "Too many requests."); return await info(req, res); }
        if (key === "POST /v1/verify/start") return await verifyStart(req, res, ip);
        if (key === "POST /v1/verify/check") return await verifyCheck(req, res, ip);
        if (key === "POST /v1/moderate") return await moderate(req, res);
        return fail(res, 404, "Not found");
      } catch (error) {
        const status = [400, 403, 404, 409, 429].includes(error.status) ? error.status : 502;
        return fail(res, status, status === 502 ? "The YouTube bot could not reach YouTube. Try again in a moment." : error.message);
      }
    },
    _test: { makeToken, readToken, normalizeText },
  };
}
