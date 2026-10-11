import { createServer as createHttpServer } from "node:http";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createV1 } from "./v1.mjs";

const API = "https://www.googleapis.com/youtube/v3";
const AUTH = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl";
const MAX_BODY = 64 * 1024;
const DAILY_QUOTA_BUDGET = 8000;

const json = (res, status, data) => {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(data));
};

const html = (res, status, body) => {
  res.writeHead(status, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
  res.end(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>CHATDOOM YouTube Moderator</title><style>body{font:16px system-ui;max-width:680px;margin:50px auto;padding:0 20px;background:#10131b;color:#eee}
main{padding:24px;background:#191e29;border-radius:14px}input,button{font:inherit;padding:10px;margin:5px 0}input{width:min(95%,460px)}a{color:#9cf}</style><main>${body}</main>`);
};

function authorized(req, secret) {
  const given = req.headers.authorization || "";
  const expected = `Bearer ${secret}`;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

function normalize(text) {
  return String(text || "").toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

function pacificDate(timestamp) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(timestamp));
  return `${parts.find((part) => part.type === "year").value}-${parts.find((part) => part.type === "month").value}-${parts.find((part) => part.type === "day").value}`;
}

export function matchRules(message, config, recentByAuthor) {
  const text = String(message.snippet?.displayMessage || "");
  const author = message.authorDetails?.channelId;
  if (!author || message.authorDetails?.isChatModerator || message.authorDetails?.isChatOwner) return null;
  if (config.blockedWords?.some((word) => word && normalize(text).includes(normalize(word)))) return "blocked word";
  if (config.deleteLinks && /(?:https?:\/\/|www\.|(?:discord\.gg|t\.me)\/)\S+/i.test(text)) return "link";
  const previous = recentByAuthor.get(author) || [];
  const key = normalize(text);
  if (config.deleteSpam && key && previous.some((entry) => entry.text === key && Date.now() - entry.at < 30_000)) return "spam";
  previous.push({ text: key, at: Date.now() });
  while (previous.length > 10) previous.shift();
  recentByAuthor.set(author, previous);
  return null;
}

function sanitizeStream(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Stream configuration must be an object");
  const channelId = String(value.channelId || "");
  const videoId = String(value.videoId || "");
  if (!/^UC[\w-]{20,30}$/.test(channelId)) throw new Error("channelId must be a YouTube channel ID (UC...)");
  if (!/^[\w-]{11}$/.test(videoId)) throw new Error("videoId must be an 11-character YouTube video ID");
  const words = value.blockedWords ?? [];
  if (!Array.isArray(words) || words.length > 200 || words.some((word) => typeof word !== "string" || word.length > 100)) {
    throw new Error("blockedWords must be an array of at most 200 strings (100 characters each)");
  }
  const dailyLimit = value.dailyLimit === undefined ? 60 : Number(value.dailyLimit);
  if (!Number.isInteger(dailyLimit) || dailyLimit < 0 || dailyLimit > 190) {
    throw new Error("dailyLimit must be an integer between 0 and 190");
  }
  return {
    channelId,
    videoId,
    blockedWords: words.map((word) => word.trim()).filter(Boolean),
    deleteLinks: value.deleteLinks === true,
    deleteSpam: value.deleteSpam === true,
    dryRun: value.dryRun !== false,
    dailyLimit,
    enabled: value.enabled !== false,
  };
}

async function readJson(file, fallback) {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return fallback;
    throw error;
  }
}

async function saveJson(file, value) {
  await mkdir(path.dirname(file), { recursive: true });
  const temp = `${file}.${process.pid}.${randomBytes(4).toString("hex")}.tmp`;     // unique per write: two saves at once must not share a file
  await writeFile(temp, JSON.stringify(value, null, 2), { mode: 0o600 });
  await rename(temp, file);
}

export function createService({ env = process.env, fetchImpl = fetch, dataDir = env.DATA_DIR || "./data", now = Date.now } = {}) {
  const configFile = path.join(dataDir, "streams.json");
  const tokenFile = path.join(dataDir, "oauth.json");
  const quotaFile = path.join(dataDir, "quota.json");
  const publicUrl = String(env.PUBLIC_URL || "").replace(/\/+$/, "");
  const adminKey = env.BOT_ADMIN_KEY || "";
  const streams = new Map();
  const states = new Map();
  let oauthState = null;
  let token = null;
  let tokenExpiresAt = 0;
  let quota = { day: pacificDate(now()), used: 0, streams: {} };
  let initialized = false;
  let stopping = false;

  async function init() {
    if (initialized) return;
    if (!adminKey || adminKey.length < 32) throw new Error("Set BOT_ADMIN_KEY to a random secret of at least 32 characters");
    if (!publicUrl || !/^https:\/\/[^/]+$/.test(publicUrl)) throw new Error("Set PUBLIC_URL to the Railway HTTPS domain, with no path");
    if (!env.GOOGLE_CLIENT_ID || !env.GOOGLE_CLIENT_SECRET) throw new Error("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET");
    const savedStreams = await readJson(configFile, []);
    if (!Array.isArray(savedStreams)) throw new Error("Stored stream configuration is invalid");
    for (const item of savedStreams) {
      const stream = sanitizeStream(item);
      streams.set(stream.channelId, { config: stream, chatId: null, pageToken: null, pollAfter: 0, day: "", actions: 0 });
    }
    const savedToken = await readJson(tokenFile, null);
    if (savedToken?.refresh_token) token = savedToken;
    else if (env.BOT_REFRESH_TOKEN) token = { refresh_token: env.BOT_REFRESH_TOKEN };   // free hosts: no disk, so keep it in an env variable
    const savedQuota = await readJson(quotaFile, null);
    if (savedQuota && savedQuota.day === pacificDate(now()) && Number.isInteger(savedQuota.used)) {
      quota = { day: savedQuota.day, used: savedQuota.used, streams: savedQuota.streams || {} };
    }
    for (const stream of streams.values()) {
      const usage = quota.streams[stream.config.channelId] || {};
      stream.day = quota.day;
      stream.actions = usage.day === quota.day ? Number(usage.actions) || 0 : 0;
    }
    initialized = true;
  }

  async function persistStreams() {
    await saveJson(configFile, [...streams.values()].map((stream) => stream.config));
  }

  async function persistQuota() {
    try {
      await saveJson(quotaFile, quota);
    } catch (error) {                       // never fail a request because the counter could not be saved
      console.error(JSON.stringify({ event: "quota_save_failed", message: error.message }));
    }
  }

  async function reserveQuota(cost) {
    const today = pacificDate(now());
    if (quota.day !== today) quota = { day: today, used: 0, streams: {} };
    if (quota.used + cost > DAILY_QUOTA_BUDGET) {
      const error = new Error(`Shared YouTube API safety budget reached (${DAILY_QUOTA_BUDGET} units per Pacific Time day)`);
      error.status = 429;
      throw error;
    }
    quota.used += cost;
    await persistQuota();
  }

  async function accessToken() {
    if (!token?.refresh_token) throw new Error("Authorize the bot Google account at /admin first");
    if (token.access_token && tokenExpiresAt > now() + 60_000) return token.access_token;
    const response = await fetchImpl(TOKEN, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: env.GOOGLE_CLIENT_ID,
        client_secret: env.GOOGLE_CLIENT_SECRET,
        refresh_token: token.refresh_token,
        grant_type: "refresh_token",
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.access_token) throw new Error(data.error_description || "Google token refresh failed");
    token = { ...token, access_token: data.access_token };
    tokenExpiresAt = now() + Number(data.expires_in || 3600) * 1000;
    await saveJson(tokenFile, token);
    return token.access_token;
  }

  async function api(url, access, options, cost) {
    await reserveQuota(cost);
    const response = await fetchImpl(url, {
      ...options,
      headers: { authorization: `Bearer ${access}`, ...(options?.headers || {}) },
    });
    const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error?.message || `YouTube API returned ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  // per-channel daily action counter (shared by the polling mode and the app-driven /v1 mode)
  const actions = {
    get(channelId) {
      const usage = quota.streams[channelId];
      return usage && usage.day === pacificDate(now()) ? Number(usage.actions) || 0 : 0;
    },
    add(channelId) {
      const today = pacificDate(now());
      if (quota.day !== today) quota = { day: today, used: 0, streams: {} };
      quota.streams[channelId] = { day: today, actions: actions.get(channelId) + 1 };
      persistQuota().catch(() => {});
    },
  };
  const v1 = createV1({
    env, now, api, accessToken, json, actions,
    readBody: async (req) => { try { return await parseBody(req); } catch (error) { error.status = 400; throw error; } },
  });

  async function moderate(stream, item) {
    const config = stream.config;
    const details = item.authorDetails || {};
    if (!details.channelId || details.isChatModerator || details.isChatOwner) return;
    const scopedRecent = stream.recent || (stream.recent = new Map());
    const matched = matchRules(item, config, scopedRecent);
    if (!matched) return;
    const day = pacificDate(now());
    if (stream.day !== day) {
      stream.day = day;
      stream.actions = 0;
    }
    if (config.dryRun) {
      console.log(JSON.stringify({ event: "dry_run", channelId: config.channelId, reason: matched }));
      return;
    }
    if (stream.actions >= config.dailyLimit) {
      console.warn(JSON.stringify({ event: "daily_limit", channelId: config.channelId }));
      return;
    }
    await api(`${API}/liveChat/messages?id=${encodeURIComponent(item.id)}`, await accessToken(), { method: "DELETE" }, 50);
    stream.actions += 1;
    quota.streams[config.channelId] = { day: quota.day, actions: stream.actions };
    await persistQuota();
    console.log(JSON.stringify({ event: "deleted", channelId: config.channelId, reason: matched }));
  }

  async function poll(stream) {
    if (!stream.config.enabled) return;
    const access = await accessToken();
    if (!stream.chatId) {
      const video = await api(`${API}/videos?part=liveStreamingDetails&id=${encodeURIComponent(stream.config.videoId)}`, access, undefined, 1);
      stream.chatId = video.items?.[0]?.liveStreamingDetails?.activeLiveChatId || null;
      stream.pageToken = null;
      if (!stream.chatId) return;
    }
    const query = new URLSearchParams({ liveChatId: stream.chatId, part: "snippet,authorDetails", maxResults: "200" });
    if (stream.pageToken) query.set("pageToken", stream.pageToken);
    const data = await api(`${API}/liveChat/messages?${query}`, access, undefined, 1);
    for (const item of data.items || []) {
      try {
        await moderate(stream, item);
      } catch (error) {
        console.error(JSON.stringify({ event: "moderation_error", channelId: stream.config.channelId, message: error.message }));
        if (error.status === 404 || error.status === 403) stream.chatId = null;
      }
    }
    stream.pageToken = data.nextPageToken || stream.pageToken;
    stream.pollAfter = now() + Math.max(5_000, Number(data.pollingIntervalMillis || 5000));
  }

  async function route(req, res) {
    await init();
    const url = new URL(req.url, publicUrl);
    if (req.method === "GET" && url.pathname === "/health") {
      return json(res, 200, { ok: true, authorized: Boolean(token?.refresh_token), streams: streams.size });
    }
    if (req.method === "GET" && url.pathname === "/") {
      return html(res, 200, '<h1>CHATDOOM YouTube Moderator</h1><p>Service is running.</p><p><a href="/admin">Open admin setup</a></p><p>Health: <a href="/health">/health</a></p>');
    }
    if (v1.handled(url)) return v1.handle(req, res, url);
    if (url.pathname.startsWith("/api/") && !authorized(req, adminKey)) {
      return json(res, 401, { error: "Unauthorized" });
    }
    if (req.method === "GET" && url.pathname === "/admin") {
      return html(res, 200, `<h1>CHATDOOM moderator setup</h1><p>Enter your private Railway BOT_ADMIN_KEY. This page stores it only in this browser tab.</p>
<input id="key" type="password" autocomplete="off" placeholder="BOT_ADMIN_KEY"><button id="auth">Authorize bot Google account</button>
<p id="result"></p><hr><h2>Register a live stream</h2><p>For now, add one stream while it is live. Use the streamer's channel ID and the current live video ID. Test mode is always on initially.</p>
<textarea id="cfg" rows="14" cols="75">{\n  "channelId": "UC...",\n  "videoId": "VIDEO_ID",\n  "blockedWords": [],\n  "deleteLinks": true,\n  "deleteSpam": false,\n  "dryRun": true,\n  "dailyLimit": 60\n}</textarea><br><button id="save">Save stream configuration</button><pre id="status"></pre>
<script>
const key=document.querySelector("#key"), result=document.querySelector("#result"), status=document.querySelector("#status");
document.querySelector("#auth").onclick=async()=>{const r=await fetch("/api/oauth/start",{method:"POST",headers:{authorization:"Bearer "+key.value}});const d=await r.json();if(!r.ok){result.textContent=d.error;return}location.href=d.url};
document.querySelector("#save").onclick=async()=>{try{const cfg=JSON.parse(document.querySelector("#cfg").value);const r=await fetch("/api/streams",{method:"POST",headers:{authorization:"Bearer "+key.value,"content-type":"application/json"},body:JSON.stringify(cfg)});status.textContent=JSON.stringify(await r.json(),null,2)}catch(e){status.textContent=e.message}};
</script>`);
    }
    if (req.method === "POST" && url.pathname === "/api/oauth/start") {
      oauthState = randomBytes(32).toString("hex");
      const params = new URLSearchParams({
        client_id: env.GOOGLE_CLIENT_ID,
        redirect_uri: `${publicUrl}/oauth/callback`,
        response_type: "code",
        scope: SCOPE,
        access_type: "offline",
        prompt: "consent",
        state: oauthState,
      });
      return json(res, 200, { url: `${AUTH}?${params}` });
    }
    if (req.method === "GET" && url.pathname === "/oauth/callback") {
      if (!oauthState || url.searchParams.get("state") !== oauthState || !url.searchParams.get("code")) {
        return html(res, 400, "<h1>Authorization failed</h1><p>Invalid state or missing authorization code. Restart from /admin.</p>");
      }
      oauthState = null;
      const response = await fetchImpl(TOKEN, {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          code: url.searchParams.get("code"),
          client_id: env.GOOGLE_CLIENT_ID,
          client_secret: env.GOOGLE_CLIENT_SECRET,
          redirect_uri: `${publicUrl}/oauth/callback`,
          grant_type: "authorization_code",
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.refresh_token) {
        console.error(JSON.stringify({ event: "oauth_exchange_failed", error: data.error || "invalid_response" }));
        return html(res, 400, "<h1>Google authorization failed</h1><p>Check Railway logs for a redacted error, then retry from /admin.</p>");
      }
      token = { refresh_token: data.refresh_token };
      tokenExpiresAt = 0;
      await saveJson(tokenFile, token);
      if (env.SHOW_REFRESH_TOKEN === "1") {
        return html(res, 200, `<h1>Bot account authorized</h1><p>This host has no permanent disk, so keep the login in an environment variable. In your hosting dashboard create
<b>BOT_REFRESH_TOKEN</b> with the value below, then <b>delete SHOW_REFRESH_TOKEN</b> and redeploy. Treat the value like a password and close this tab afterwards.</p>
<pre style="white-space:pre-wrap;word-break:break-all;background:#0c0f16;padding:12px;border-radius:8px">${data.refresh_token}</pre>`);
      }
      return html(res, 200, "<h1>Bot account authorized</h1><p>The refresh token was saved to the service data volume. You can close this tab.</p>");
    }
    if (req.method === "GET" && url.pathname === "/api/streams") {
      return json(res, 200, { streams: [...streams.values()].map((stream) => ({ ...stream.config })) });
    }
    if (req.method === "POST" && url.pathname === "/api/streams") {
      const body = await parseBody(req);
      const config = sanitizeStream(body);
      const prior = streams.get(config.channelId);
      streams.set(config.channelId, {
        config, chatId: null, pageToken: null, pollAfter: 0,
        day: prior?.day || quota.day, actions: prior?.actions || 0, recent: prior?.recent,
      });
      await persistStreams();
      return json(res, 201, { ok: true, config });
    }
    if (req.method === "DELETE" && url.pathname.startsWith("/api/streams/")) {
      const id = decodeURIComponent(url.pathname.slice("/api/streams/".length));
      if (!streams.delete(id)) return json(res, 404, { error: "Stream not found" });
      delete quota.streams[id];
      await persistQuota();
      await persistStreams();
      return json(res, 200, { ok: true });
    }
    return json(res, 404, { error: "Not found" });
  }

  const server = createHttpServer((req, res) => {
    Promise.resolve(route(req, res)).catch((error) => {
      console.error(JSON.stringify({ event: "request_error", message: error.message }));
      if (!res.headersSent) json(res, 500, { error: "Request failed; check service logs" });
      else res.destroy();
    });
  });

  async function parseBody(req) {
    let raw = "";
    for await (const part of req) {
      raw += part;
      if (Buffer.byteLength(raw) > MAX_BODY) throw new Error("Request body is too large");
    }
    try {
      return JSON.parse(raw || "{}");
    } catch {
      throw new Error("Request body must be valid JSON");
    }
  }

  let timer;
  async function tick() {
    if (stopping) return;
    const nowMs = now();
    for (const stream of streams.values()) {
      if (!stream.config.enabled || (stream.pollAfter && stream.pollAfter > nowMs)) continue;
      try {
        await poll(stream);
      } catch (error) {
        console.error(JSON.stringify({ event: "poll_error", channelId: stream.config.channelId, message: error.message }));
        stream.pollAfter = nowMs + (error.status === 429 ? 60 * 60_000 : error.status === 403 ? 60_000 : 15_000);
        if (error.status === 404) {
          stream.chatId = null;
          stream.pageToken = null;
        }
      }
    }
    timer = setTimeout(tick, 1000);
    timer.unref();
  }

  return {
    server,
    async start() {
      await init();
      await new Promise((resolve, reject) => {
        const onError = (error) => reject(error);
        server.once("error", onError);
        server.listen(Number(env.PORT || 3000), "0.0.0.0", () => {
          server.off("error", onError);
          resolve();
        });
      });
      tick();
    },
    async close() {
      stopping = true;
      clearTimeout(timer);
      if (server.listening) {
        server.close();
        server.closeAllConnections();
      }
    },
    tick,
  };
}

const currentFile = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === currentFile) {
  const service = createService();
  process.on("SIGTERM", () => service.close().finally(() => process.exit(0)));
  process.on("SIGINT", () => service.close().finally(() => process.exit(0)));
  service.start().catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
