const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

const clean = (value, max) => String(value || "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
const providers = {
  youtube: {
    clientId: "GOOGLE_OAUTH_CLIENT_ID",
    clientSecret: "GOOGLE_OAUTH_CLIENT_SECRET",
    callback: "/platform-auth/youtube/callback",
  },
  twitch: {
    clientId: "TWITCH_CLIENT_ID",
    clientSecret: "TWITCH_CLIENT_SECRET",
    callback: "/platform-auth/twitch/callback",
  },
};
let dbReady;
const YOUTUBE_ACTION_QUOTA_BUDGET = 8000;
const YOUTUBE_SUBSCRIBER_QUOTA_BUDGET = 2000;

function randomString(length) {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function hash(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function toBase64(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)));
}

function fromBase64(value) {
  return Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
}

async function encryptionKey(env) {
  if (!env.PLATFORM_TOKEN_ENCRYPTION_KEY) throw new Error("PLATFORM_TOKEN_ENCRYPTION_KEY is not configured");
  const raw = fromBase64(env.PLATFORM_TOKEN_ENCRYPTION_KEY);
  if (raw.length !== 32) throw new Error("PLATFORM_TOKEN_ENCRYPTION_KEY must be a base64-encoded 32-byte key");
  return crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

async function encrypt(env, value) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await encryptionKey(env), new TextEncoder().encode(value));
  return toBase64(new Uint8Array([...iv, ...new Uint8Array(cipher)]));
}

async function decrypt(env, value) {
  const data = fromBase64(value);
  if (data.length < 29) throw new Error("Stored platform credential is invalid");
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: data.slice(0, 12) }, await encryptionKey(env), data.slice(12));
  return new TextDecoder().decode(plain);
}

async function database(env) {
  if (!env.DB) throw new Error("Platform account storage is unavailable; configure the Cloudflare D1 database");
  if (!dbReady) {
    dbReady = Promise.all([
      env.DB.prepare("CREATE TABLE IF NOT EXISTS platform_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, session_hash TEXT NOT NULL UNIQUE, platform TEXT NOT NULL, provider_user_id TEXT NOT NULL, display_name TEXT NOT NULL, access_token TEXT NOT NULL, refresh_token TEXT NOT NULL, expires_at INTEGER NOT NULL)").run(),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS platform_api_quota (day TEXT PRIMARY KEY, used INTEGER NOT NULL)").run(),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS platform_subscriber_quota (day TEXT PRIMARY KEY, used INTEGER NOT NULL)").run(),
    ])
      .catch((error) => { dbReady = null; throw error; });
  }
  await dbReady;
  return env.DB;
}

function pacificDay() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  return `${parts.find((part) => part.type === "year").value}-${parts.find((part) => part.type === "month").value}-${parts.find((part) => part.type === "day").value}`;
}

async function reserveYouTubeQuota(env, cost) {
  const d = await database(env);
  const day = pacificDay();
  await d.prepare("INSERT OR IGNORE INTO platform_api_quota (day, used) VALUES (?, 0)").bind(day).run();
  const result = await d.prepare("UPDATE platform_api_quota SET used = used + ? WHERE day = ? AND used + ? <= ?")
    .bind(cost, day, cost, YOUTUBE_ACTION_QUOTA_BUDGET).run();
  if (!result.meta || result.meta.changes !== 1) {
    const error = new Error("CHATDOOM's shared YouTube action budget is used up for today (resets at midnight Pacific Time)");
    error.status = 429;
    throw error;
  }
}

async function reserveYouTubeSubscriberQuota(env, cost) {
  const d = await database(env);
  const day = pacificDay();
  await d.prepare("INSERT OR IGNORE INTO platform_subscriber_quota (day, used) VALUES (?, 0)").bind(day).run();
  const result = await d.prepare("UPDATE platform_subscriber_quota SET used = used + ? WHERE day = ? AND used + ? <= ?")
    .bind(cost, day, cost, YOUTUBE_SUBSCRIBER_QUOTA_BUDGET).run();
  if (!result.meta || result.meta.changes !== 1) {
    const error = new Error("The shared YouTube public-subscriber alert quota is used up for today");
    error.status = 429;
    throw error;
  }
}

async function kvGet(env, key) {
  const value = await env.KV.get(key);
  return value ? JSON.parse(value) : null;
}

async function kvPut(env, key, value, ttl) {
  await env.KV.put(key, JSON.stringify(value), { expirationTtl: ttl });
}

function returnAddress(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname) &&
      /^\d{2,5}$/.test(url.port) && url.pathname === "/done" && !url.search && !url.hash;
  } catch (_) {
    return false;
  }
}

async function tokenResponse(response, provider, stage) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = clean(data.error_description || data.message || data.error || "", 100);
    const error = new Error(`${provider} ${stage} failed (${response.status})${detail ? ": " + detail : ""}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function providerConfig(env, platform) {
  const config = providers[platform];
  if (!config) throw new Error("Unsupported platform");
  if (!env[config.clientId] || !env[config.clientSecret]) throw new Error(`${config.clientId} and ${config.clientSecret} must be configured`);
  return config;
}

async function start(env, origin, url) {
  const platform = url.searchParams.get("platform");
  if (!providers[platform]) return json({ error: "Unsupported platform" }, 400);
  if (url.protocol !== "https:") return json({ error: "Platform sign-in requires HTTPS" }, 400);
  let config;
  try {
    config = providerConfig(env, platform);
    await encryptionKey(env);
    await database(env);
  } catch (error) {
    return json({ error: clean(error.message, 180) }, 503);
  }
  const returnUrl = url.searchParams.get("return") || "";
  if (!returnAddress(returnUrl)) return json({ error: "The return address must be the app's local /done callback" }, 400);
  const state = randomString(24);
  await kvPut(env, `platform-oauth-state:${state}`, { platform, returnUrl }, 600);
  const redirectUri = origin + config.callback;
  const authUrl = new URL(platform === "youtube"
    ? "https://accounts.google.com/o/oauth2/v2/auth"
    : "https://id.twitch.tv/oauth2/authorize");
  authUrl.searchParams.set("client_id", env[config.clientId]);
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("state", state);
  if (platform === "youtube") {
    authUrl.searchParams.set("scope", "openid profile https://www.googleapis.com/auth/youtube.force-ssl");
    authUrl.searchParams.set("access_type", "offline");
    authUrl.searchParams.set("prompt", "consent");
  } else {
    authUrl.searchParams.set("scope", "user:write:chat channel:manage:polls moderator:read:followers channel:read:subscriptions");
  }
  return json({ authorizeUrl: authUrl.toString() });
}

async function exchangeCode(env, platform, config, code, redirectUri) {
  const body = new URLSearchParams({
    client_id: env[config.clientId],
    client_secret: env[config.clientSecret],
    code,
    grant_type: "authorization_code",
    redirect_uri: redirectUri,
  });
  const endpoint = platform === "youtube" ? "https://oauth2.googleapis.com/token" : "https://id.twitch.tv/oauth2/token";
  return tokenResponse(await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  }), platform, "token exchange");
}

async function profile(env, platform, accessToken) {
  if (platform === "youtube") {
    await reserveYouTubeSubscriberQuota(env, 1);
    const url = new URL("https://www.googleapis.com/youtube/v3/channels");
    url.search = new URLSearchParams({ part: "id,snippet", mine: "true" });
    const response = await fetch(url, {
      headers: { Authorization: "Bearer " + accessToken },
    });
    const data = await tokenResponse(response, "YouTube", "channel lookup");
    const channel = data.items && data.items[0];
    if (!channel || !channel.id) throw new Error("YouTube did not return a channel for this account");
    return { id: channel.id, name: channel.snippet && channel.snippet.title || channel.id };
  }
  const response = await fetch("https://api.twitch.tv/helix/users", {
    headers: { Authorization: "Bearer " + accessToken, "Client-Id": env.TWITCH_CLIENT_ID },
  });
  const data = await tokenResponse(response, "Twitch", "account lookup");
  const user = data.data && data.data[0];
  if (!user) throw new Error("Twitch did not return the signed-in account");
  return { id: user.id, name: user.display_name || user.login };
}

async function callback(env, origin, url, platform) {
  const config = providerConfig(env, platform);
  const state = url.searchParams.get("state") || "";
  const saved = state && await kvGet(env, `platform-oauth-state:${state}`);
  if (!saved || saved.platform !== platform) return json({ error: "Login expired or state did not match. Start again in CHATDOOM." }, 400);
  await env.KV.delete(`platform-oauth-state:${state}`);
  if (url.searchParams.has("error") || !url.searchParams.get("code")) {
    const error = clean(url.searchParams.get("error_description") || url.searchParams.get("error") || "login cancelled", 100);
    return Response.redirect(saved.returnUrl + "?ok=0&error=" + encodeURIComponent(error), 302);
  }

  let token, identity;
  try {
    token = await exchangeCode(env, platform, config, url.searchParams.get("code"), origin + config.callback);
    if (!token.refresh_token) throw new Error("The provider did not issue a refresh token; revoke CHATDOOM access and try login again");
    identity = await profile(env, platform, token.access_token);
  } catch (error) {
    return Response.redirect(saved.returnUrl + "?ok=0&error=" + encodeURIComponent(clean(error.message, 140)), 302);
  }

  const session = randomString(32);
  const expiresAt = Math.floor(Date.now() / 1000) + Math.max(60, Number(token.expires_in) || 3600);
  const encryptedAccess = await encrypt(env, token.access_token);
  const encryptedRefresh = await encrypt(env, token.refresh_token);
  const d = await database(env);
  await d.prepare("INSERT INTO platform_accounts (session_hash, platform, provider_user_id, display_name, access_token, refresh_token, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(session_hash) DO UPDATE SET platform=excluded.platform, provider_user_id=excluded.provider_user_id, display_name=excluded.display_name, access_token=excluded.access_token, refresh_token=excluded.refresh_token, expires_at=excluded.expires_at")
    .bind(await hash(session), platform, identity.id, clean(identity.name, 100), encryptedAccess, encryptedRefresh, expiresAt).run();
  const ticket = randomString(24);
  await kvPut(env, "platform-oauth-ticket:" + ticket, {
    session, platform, userId: identity.id, displayName: clean(identity.name, 100),
  }, 120);
  return Response.redirect(saved.returnUrl + "?ok=1&ticket=" + ticket, 302);
}

async function accountFor(request, env) {
  const authorization = request.headers.get("Authorization") || "";
  const session = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!/^[0-9a-f]{64}$/.test(session)) return null;
  const d = await database(env);
  const row = await d.prepare("SELECT * FROM platform_accounts WHERE session_hash = ?").bind(await hash(session)).first();
  if (!row) return null;
  const account = { ...row, accessToken: await decrypt(env, row.access_token), refreshToken: await decrypt(env, row.refresh_token) };
  if (account.expires_at > Math.floor(Date.now() / 1000) + 60) return account;

  const config = providerConfig(env, account.platform);
  const response = await fetch(account.platform === "youtube"
    ? "https://oauth2.googleapis.com/token" : "https://id.twitch.tv/oauth2/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env[config.clientId],
      client_secret: env[config.clientSecret],
      grant_type: "refresh_token",
      refresh_token: account.refreshToken,
    }),
  });
  let refreshed;
  try {
    refreshed = await tokenResponse(response, account.platform, "token refresh");
  } catch (error) {
    if (error.status === 400 || error.status === 401) {
      await d.prepare("DELETE FROM platform_accounts WHERE id = ?").bind(account.id).run();
      error.status = 401;
    }
    throw error;
  }
  account.accessToken = refreshed.access_token;
  if (refreshed.refresh_token) account.refreshToken = refreshed.refresh_token;
  account.expires_at = Math.floor(Date.now() / 1000) + Math.max(60, Number(refreshed.expires_in) || 3600);
  await d.prepare("UPDATE platform_accounts SET access_token = ?, refresh_token = ?, expires_at = ? WHERE id = ?")
    .bind(await encrypt(env, account.accessToken), await encrypt(env, account.refreshToken), account.expires_at, account.id).run();
  return account;
}

async function redeem(request, env) {
  const body = await request.json().catch(() => ({}));
  const ticket = String(body.ticket || "");
  if (!/^[0-9a-f]{48}$/.test(ticket)) return json({ error: "Login ticket is invalid or expired" }, 400);
  const key = "platform-oauth-ticket:" + ticket;
  const value = await kvGet(env, key);
  if (!value) return json({ error: "Login ticket is invalid or expired" }, 400);
  await env.KV.delete(key);
  return json({ ok: true, session: value.session, platform: value.platform, userId: value.userId, displayName: value.displayName });
}

async function accountInfo(request, env) {
  let account;
  try { account = await accountFor(request, env); }
  catch (error) { return json({ error: clean(error.message, 140) }, error.status === 400 || error.status === 401 ? 401 : 502); }
  if (!account) return json({ error: "Platform login expired or disconnected. Sign in again." }, 401);
  return json({ platform: account.platform, userId: account.provider_user_id, displayName: account.display_name });
}

async function twitchEventSub(request, env) {
  let account;
  try { account = await accountFor(request, env); }
  catch (error) { return json({ error: clean(error.message, 140) }, error.status === 400 || error.status === 401 ? 401 : 502); }
  if (!account) return json({ error: "Platform login expired or disconnected. Sign in again." }, 401);
  if (account.platform !== "twitch") return json({ error: "Sign in to Twitch to receive Twitch alerts" }, 400);
  const body = await request.json().catch(() => ({}));
  const sessionId = String(body.sessionId || "");
  if (!/^[\w-]{8,256}$/.test(sessionId)) return json({ error: "Twitch EventSub WebSocket session is invalid" }, 400);

  const definitions = [
    { type: "channel.follow", version: "2", condition: {
      broadcaster_user_id: account.provider_user_id, moderator_user_id: account.provider_user_id,
    } },
    { type: "channel.subscribe", version: "1", condition: { broadcaster_user_id: account.provider_user_id } },
    { type: "channel.subscription.message", version: "1", condition: { broadcaster_user_id: account.provider_user_id } },
    { type: "channel.subscription.gift", version: "1", condition: { broadcaster_user_id: account.provider_user_id } },
    { type: "channel.raid", version: "1", condition: { to_broadcaster_user_id: account.provider_user_id } },
  ];
  const subscribed = [], failed = [];
  try {
    for (const definition of definitions) {
      const response = await fetch("https://api.twitch.tv/helix/eventsub/subscriptions", {
        method: "POST",
        headers: { Authorization: "Bearer " + account.accessToken, "Client-Id": env.TWITCH_CLIENT_ID, "content-type": "application/json" },
        body: JSON.stringify({ ...definition, transport: { method: "websocket", session_id: sessionId } }),
      });
      if (response.ok) subscribed.push(definition.type);
      else {
        const data = await response.json().catch(() => ({}));
        failed.push({
          type: definition.type,
          status: response.status,
          error: clean(data.message || data.error || "Twitch rejected the event subscription", 120),
        });
      }
    }
  } catch (error) {
    return json({ error: clean(error.message || "Could not reach Twitch EventSub", 140) }, 502);
  }
  return json({ ok: subscribed.length > 0, subscribed, failed });
}

async function youtubeSubscribers(request, env) {
  let account;
  try { account = await accountFor(request, env); }
  catch (error) { return json({ error: clean(error.message, 140) }, error.status === 400 || error.status === 401 ? 401 : 502); }
  if (!account) return json({ error: "Platform login expired or disconnected. Sign in again." }, 401);
  if (account.platform !== "youtube") return json({ error: "Sign in to YouTube to check public subscribers" }, 400);
  const body = await request.json().catch(() => ({}));
  const since = Math.max(0, Number(body.since) || 0);
  const through = Date.now();
  try {
    let channelId = account.provider_user_id;
    if (!/^UC[\w-]{22}$/.test(channelId)) {
      await reserveYouTubeSubscriberQuota(env, 1);
      const channelsUrl = new URL("https://www.googleapis.com/youtube/v3/channels");
      channelsUrl.search = new URLSearchParams({ part: "id", mine: "true" });
      const channelResponse = await fetch(channelsUrl, { headers: { Authorization: "Bearer " + account.accessToken } });
      const channelData = await tokenResponse(channelResponse, "YouTube", "channel lookup");
      channelId = channelData.items && channelData.items[0] && channelData.items[0].id || "";
      if (!channelId) throw new Error("YouTube did not return a channel for this account");
      await env.DB.prepare("UPDATE platform_accounts SET provider_user_id = ? WHERE id = ?").bind(channelId, account.id).run();
    }

    const subscribers = [];
    let pageToken = "";
    let reachedCursor = false;
    for (let page = 0; page < 10 && !reachedCursor; page++) {
      await reserveYouTubeSubscriberQuota(env, 1);
      const url = new URL("https://www.googleapis.com/youtube/v3/subscriptions");
      url.search = new URLSearchParams({
        part: "id,snippet,subscriberSnippet",
        mySubscribers: "true",
        forChannelId: channelId,
        maxResults: "50",
        ...(pageToken ? { pageToken } : {}),
      });
      const response = await fetch(url, { headers: { Authorization: "Bearer " + account.accessToken } });
      const data = await tokenResponse(response, "YouTube", "subscriber lookup");
      for (const item of data.items || []) {
        const publishedAt = Date.parse(item.snippet && item.snippet.publishedAt || "");
        if (!Number.isFinite(publishedAt) || publishedAt <= since || publishedAt > through) {
          if (Number.isFinite(publishedAt) && publishedAt <= since) reachedCursor = true;
          continue;
        }
        const name = clean(item.subscriberSnippet && item.subscriberSnippet.title || "", 100);
        if (name) subscribers.push({ id: clean(item.id, 100), name, publishedAt });
      }
      pageToken = data.nextPageToken || "";
      if (!pageToken) break;
    }
    return json({ subscribers, cursor: through, publicSubscribersOnly: true });
  } catch (error) {
    return json({ error: clean(error.message || "Could not retrieve public YouTube subscribers", 160) },
      error.status === 429 ? 429 : error.status === 400 || error.status === 401 ? error.status : 502);
  }
}

async function youtubeChatId(env, account, videoId) {
  if (!/^[\w-]{11}$/.test(videoId)) throw new Error("Enter a valid YouTube live video ID");
  await reserveYouTubeQuota(env, 1);
  const url = new URL("https://www.googleapis.com/youtube/v3/liveBroadcasts");
  url.search = new URLSearchParams({ part: "id,snippet", broadcastStatus: "active", mine: "true" });
  const response = await fetch(url, { headers: { Authorization: "Bearer " + account.accessToken } });
  const data = await tokenResponse(response, "YouTube", "live stream lookup");
  const live = (data.items || []).find((item) => item.id === videoId && item.snippet && item.snippet.liveChatId);
  if (!live) throw new Error("That video is not an active live stream on the signed-in YouTube channel");
  return live.snippet.liveChatId;
}

async function action(request, env, kind) {
  let account;
  try { account = await accountFor(request, env); }
  catch (error) { return json({ error: clean(error.message, 140) }, error.status === 400 || error.status === 401 ? 401 : 502); }
  if (!account) return json({ error: "Platform login expired or disconnected. Sign in again." }, 401);
  const body = await request.json().catch(() => ({}));
  const platform = String(body.platform || "");
  if (platform !== account.platform) return json({ error: "Choose the platform account you signed in to" }, 400);

  try {
    if (platform === "youtube") {
      let snippet;
      if (kind === "message") {
        const text = clean(body.text, 200);
        if (!text) return json({ error: "Type a message first" }, 400);
        snippet = { type: "textMessageEvent", textMessageDetails: { messageText: text } };
      } else {
        const question = clean(body.question, 100);
        const options = Array.isArray(body.options) ? body.options.map((v) => clean(v, 50)).filter(Boolean).slice(0, 4) : [];
        if (!question || options.length < 2) return json({ error: "A poll needs a question and 2 to 4 options" }, 400);
        snippet = { type: "pollEvent", pollDetails: { metadata: { questionText: question, options: options.map((optionText) => ({ optionText })) } } };
      }
      const chatId = await youtubeChatId(env, account, String(body.videoId || ""));
      await reserveYouTubeQuota(env, 50);
      const response = await fetch("https://www.googleapis.com/youtube/v3/liveChatMessages?part=snippet", {
        method: "POST",
        headers: { Authorization: "Bearer " + account.accessToken, "content-type": "application/json" },
        body: JSON.stringify({ snippet: { liveChatId: chatId, ...snippet } }),
      });
      const data = await tokenResponse(response, "YouTube", kind === "message" ? "message send" : "poll creation");
      return json({ ok: true, id: data.id || "" });
    }

    if (kind === "message") {
      const text = clean(body.text, 500);
      if (!text) return json({ error: "Type a message first" }, 400);
      const url = new URL("https://api.twitch.tv/helix/chat/messages");
      url.search = new URLSearchParams({ broadcaster_id: account.provider_user_id, sender_id: account.provider_user_id });
      const response = await fetch(url, {
        method: "POST",
        headers: { Authorization: "Bearer " + account.accessToken, "Client-Id": env.TWITCH_CLIENT_ID, "content-type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await tokenResponse(response, "Twitch", "message send");
      if (data.data && data.data[0] && !data.data[0].is_sent) return json({ error: data.data[0].message || "Twitch did not send the message" }, 502);
      return json({ ok: true, id: data.data && data.data[0] && data.data[0].message_id || "" });
    }

    const title = clean(body.question, 60);
    const choices = Array.isArray(body.options) ? body.options.map((v) => clean(v, 25)).filter(Boolean).slice(0, 5) : [];
    const duration = Math.min(180, Math.max(15, Number(body.duration) || 60));
    if (!title || choices.length < 2) return json({ error: "A poll needs a question and 2 to 5 options" }, 400);
    const response = await fetch("https://api.twitch.tv/helix/polls", {
      method: "POST",
      headers: { Authorization: "Bearer " + account.accessToken, "Client-Id": env.TWITCH_CLIENT_ID, "content-type": "application/json" },
      body: JSON.stringify({ broadcaster_id: account.provider_user_id, title, choices: choices.map((title) => ({ title })), duration }),
    });
    const data = await tokenResponse(response, "Twitch", "poll creation");
    return json({ ok: true, id: data.data && data.data[0] && data.data[0].id || "" });
  } catch (error) {
    return json({ error: clean(error.message, 180) }, error.status || 502);
  }
}

async function disconnect(request, env) {
  const authorization = request.headers.get("Authorization") || "";
  const session = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!/^[0-9a-f]{64}$/.test(session)) return json({ error: "Platform login expired or disconnected" }, 401);
  let account;
  try { account = await accountFor(request, env); }
  catch (error) { return json({ error: clean(error.message, 140) }, error.status === 400 || error.status === 401 ? 401 : 502); }
  if (!account) return json({ error: "Platform login expired or disconnected" }, 401);
  const config = providerConfig(env, account.platform);
  const revokeUrl = account.platform === "youtube"
    ? "https://oauth2.googleapis.com/revoke"
    : "https://id.twitch.tv/oauth2/revoke";
  const revokeBody = account.platform === "youtube"
    ? { token: account.refreshToken }
    : { client_id: env[config.clientId], token: account.accessToken };
  const revoked = await fetch(revokeUrl, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(revokeBody),
  });
  if (!revoked.ok && revoked.status !== 400 && revoked.status !== 401)
    return json({ error: `${account.platform} did not revoke the app's authorization (${revoked.status})` }, 502);
  const d = await database(env);
  const result = await d.prepare("DELETE FROM platform_accounts WHERE session_hash = ?").bind(await hash(session)).run();
  if (!result.meta || result.meta.changes !== 1) return json({ error: "Platform login expired or disconnected" }, 401);
  return json({ ok: true });
}

export async function handlePlatformAuth(request, env, url) {
  const path = url.pathname;
  if (request.method === "GET" && path === "/platform-auth/start") return start(env, url.origin, url);
  if (request.method === "GET" && path === providers.youtube.callback) return callback(env, url.origin, url, "youtube");
  if (request.method === "GET" && path === providers.twitch.callback) return callback(env, url.origin, url, "twitch");
  if (request.method === "POST" && path === "/platform-auth/redeem") return redeem(request, env);
  if (request.method === "GET" && path === "/platform-auth/account") return accountInfo(request, env);
  if (request.method === "POST" && path === "/platform-auth/eventsub") return twitchEventSub(request, env);
  if (request.method === "POST" && path === "/platform-auth/youtube-subscribers") return youtubeSubscribers(request, env);
  if (request.method === "POST" && path === "/platform-auth/message") return action(request, env, "message");
  if (request.method === "POST" && path === "/platform-auth/poll") return action(request, env, "poll");
  if (request.method === "DELETE" && path === "/platform-auth/account") return disconnect(request, env);
  return null;
}
