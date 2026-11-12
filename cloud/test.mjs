// Offline test of the worker with a fake KV and a fake Discord. Run: node test.mjs
import worker from "./src/index.js";
import { createHash } from "node:crypto";

const store = new Map();
const KV = { async get(k) { return store.has(k) ? store.get(k) : null; }, async put(k, v) { store.set(k, v); }, async delete(k) { store.delete(k); } };
const env = { KV, DISCORD_CLIENT_ID: "CID", DISCORD_CLIENT_SECRET: "SEC", DISCORD_BOT_TOKEN: "BOT" };
const translatedInputs = [];
env.AI = { async run(model, input) {
  translatedInputs.push({ model, input });
  return { translated_text: "Hello from the stream!" };
} };
const puts = [];
const platformCalls = [];
const eventSubCalls = [];
let youtubeSubscribers = [];
let memberOk = true, roleStatus = 204;
const baseRoles = () => [{ id: "1", name: "@everyone", position: 0 }, { id: "100001", name: "Verified", position: 3 }, { id: "100002", name: "Regular", position: 2 }, { id: "100003", name: "Supporter", position: 4 }, { id: "9", name: "BotRole", managed: true, position: 5 }];
let rolesNow = baseRoles(), roleCreateStatus = 200, systemChannel = "C1", inviteSeq = 0; const createdRoles = [], createdInvites = [];
let invitesNow = [], membersNow = [], invitesStatus = 200, membersStatus = 200, memberCalls = 0;
const putsFull = [];
const kickTokenCalls = [], kickRevokeCalls = [];

const modCalls = [];
const VIEWER_CHANNEL = "UCviewerviewerviewerviewe";
let twitchLive = true, twitchDenies = false, kickNoChannelScope = false;
globalThis.fetch = async (url, init = {}) => {
  const u = new URL(url), p = u.pathname.replace("/api/v10", ""), m = init.method || "GET";
  const j = (o, s = 200) => new Response(JSON.stringify(o), { status: s });
  const verb = init.method || "GET";
  if (u.hostname === "www.youtube.com") return new Response(null, { status: p === "/shorts/verticalid1" ? 200 : 303 });
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/videos") return Response.json({ items: [{ player: { embedWidth: 480, embedHeight: 270 } }] });
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/liveChat/bans") {
    modCalls.push({ verb, path: p, query: u.search, body: init.body && JSON.parse(init.body) });
    return verb === "DELETE" ? new Response(null, { status: 204 }) : Response.json({ id: "BAN-1" });
  }
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/liveChat/moderators") {
    modCalls.push({ verb, path: p, body: JSON.parse(init.body) });
    return Response.json({ id: "MOD-1" });
  }
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/liveChat/messages/transition") {
    modCalls.push({ verb, path: p, query: u.search });
    return Response.json({ id: "POLL-1" });
  }
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/liveChat/messages" && verb === "GET") {
    return Response.json({ items: [{ id: "LCC.1", snippet: { displayMessage: "bad words" }, authorDetails: { channelId: VIEWER_CHANNEL } }] });
  }
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/liveChat/messages" && verb === "DELETE") {
    modCalls.push({ verb, path: p, query: u.search });
    return new Response(null, { status: 204 });
  }
  if (u.hostname === "api.twitch.tv" && p === "/helix/streams") {
    return Response.json({ data: twitchLive ? [{ id: "TW-STREAM", title: "Ranked grind" }] : [] });
  }
  if (u.hostname === "api.twitch.tv" && (p.startsWith("/helix/moderation/") || p === "/helix/chat/settings" || p === "/helix/chat/shoutouts" || p === "/helix/chat/announcements" || (p === "/helix/polls" && verb === "PATCH"))) {
    modCalls.push({ verb, path: p, query: u.search, body: init.body && JSON.parse(init.body) });
    if (twitchDenies) return Response.json({ message: "Missing scope" }, { status: 401 });
    return Response.json({ data: [] });
  }
  if (u.hostname === "api.kick.com" && p === "/public/v1/channels") {
    if (kickNoChannelScope) return Response.json({ message: "Forbidden" }, { status: 403 });
    return Response.json({ data: [{ slug: "test-kick", broadcaster_user_id: 4242, stream_title: "Kick live", stream: { is_live: true } }] });
  }
  if (u.hostname === "api.kick.com" && (p === "/public/v1/moderation/bans" || (p.startsWith("/public/v1/chat/") && verb === "DELETE"))) {
    modCalls.push({ verb, path: p, body: init.body && JSON.parse(init.body) });
    return verb === "DELETE" && p !== "/public/v1/moderation/bans" ? new Response(null, { status: 204 }) : Response.json({ data: {} });
  }
  if (u.hostname === "oauth2.googleapis.com" && p === "/token") {
    const body = new URLSearchParams(init.body);
    return j({ access_token: body.get("grant_type") === "refresh_token" ? "YT_ACCESS_2" : "YT_ACCESS",
      refresh_token: "YT_REFRESH", expires_in: 3600 });
  }
  if (u.hostname === "id.kick.com" && p === "/oauth/token") {
    const body = new URLSearchParams(init.body);
    kickTokenCalls.push(body);
    return j({ access_token: "KICK_ACCESS", refresh_token: "KICK_REFRESH", expires_in: 3600 });
  }
  if (u.hostname === "id.kick.com" && p === "/oauth/revoke") {
    kickRevokeCalls.push(u);
    return new Response("OK", { status: 200 });
  }
  if (u.hostname === "api.kick.com" && p === "/public/v1/users") {
    return j({ data: [{ user_id: 4242, name: "Test Kick", email: "x@example.com" }], message: "OK" });
  }
  if (u.hostname === "api.kick.com" && p === "/public/v1/chat") {
    platformCalls.push({ platform: "kick", path: p, body: JSON.parse(init.body), headers: init.headers });
    return j({ data: { is_sent: true, message_id: "KICK_ACTION" }, message: "OK" });
  }
  if ((u.hostname === "oauth2.googleapis.com" || u.hostname === "id.twitch.tv") && p === "/revoke") return new Response(null, { status: 200 });
  if (u.hostname === "id.twitch.tv" && p === "/oauth2/token") {
    return j({ access_token: "TW_ACCESS", refresh_token: "TW_REFRESH", expires_in: 3600 });
  }
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/channels") {
    return j({ items: [{ id: "UC" + "a".repeat(22), snippet: { title: "Test YouTube Channel" } }] });
  }
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/subscriptions") {
    platformCalls.push({ platform: "youtube", path: p, url: u.toString() });
    return j({ items: youtubeSubscribers });
  }
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/liveBroadcasts") {
    if (u.searchParams.has("mine") === u.searchParams.has("broadcastStatus"))   // Google allows exactly one filter
      return j({ error: { code: 400, message: "Incompatible parameters specified in the request" } }, 400);
    if (globalThis.youtubeLookupFails) return j({ error: { code: 400, message: "Google said no" } }, 400);
    if (u.searchParams.get("broadcastStatus") === "upcoming") return j({ items: [
      { id: "oldstream01", snippet: { title: "Old default", scheduledStartTime: "2020-01-01T00:00:00Z" }, status: { privacyStatus: "public" } },
      { id: "scheduled01", snippet: { title: "Friday stream", scheduledStartTime: new Date(Date.now() + 3600000).toISOString() }, status: { privacyStatus: "unlisted" } },
    ] });
    return j({ items: [{ id: "abcdefghijk", snippet: { liveChatId: "CHAT_ID" } }] });
  }
  if (u.hostname === "www.googleapis.com" && p === "/youtube/v3/liveChat/messages") {
    platformCalls.push({ platform: "youtube", method: m, body: init.body && JSON.parse(init.body) });
    return j({ id: "YT_ACTION" });
  }
  if (u.hostname === "api.twitch.tv" && p === "/helix/users") {
    return j({ data: [{ id: "TWITCH_USER", login: "testtwitch", display_name: "Test Twitch" }] });
  }
  if (u.hostname === "api.twitch.tv" && p === "/helix/eventsub/subscriptions") {
    const body = JSON.parse(init.body);
    eventSubCalls.push({ body, headers: init.headers });
    return j({ data: [{ type: body.type }] }, 202);
  }
  if (u.hostname === "api.twitch.tv" && (p === "/helix/chat/messages" || p === "/helix/polls")) {
    platformCalls.push({ platform: "twitch", path: p, body: init.body && JSON.parse(init.body) });
    return j({ data: [{ id: "TW_ACTION", message_id: "TW_ACTION", is_sent: true }] });
  }
  if (p === "/oauth2/token") {
    const body = new URLSearchParams(init.body);
    if (body.get("client_secret") === "BAD") return j({ error: "invalid_client" }, 401);
    return body.get("redirect_uri").includes("/setup/") ? j({ access_token: "AT", guild: { id: "G1", name: "Test Server" } }) : j({ access_token: "AT2" });
  }
  if (p === "/users/@me") return j({ id: "U1", username: "rahul", global_name: "Rahul" });
  if (p === "/guilds/G1/members/U1" && m === "GET") return memberOk ? j({ user: { id: "U1" } }) : j({}, 404);
  if (p === "/guilds/G1/roles" && m === "GET") return j(rolesNow);
  if (p === "/guilds/G1/roles" && m === "POST") { if (roleCreateStatus !== 200) return j({}, roleCreateStatus); const r = { id: String(900000 + rolesNow.length), name: JSON.parse(init.body).name }; rolesNow.push(r); createdRoles.push(r.name); return j(r); }
  if (p === "/guilds/G1" && m === "GET") return j(systemChannel ? { system_channel_id: systemChannel } : {});
  if (p === "/guilds/G1/channels") return j([{ id: "C9", type: 2, position: 0 }, { id: "C2", type: 0, position: 1, name: "general" }]);
  if (/^\/channels\/\w+\/invites$/.test(p) && m === "POST") { const code = "NEW" + (++inviteSeq); invitesNow.push({ code, uses: 0 }); createdInvites.push(p.split("/")[2]); return j({ code }); }
  if (m === "PUT" && /^\/guilds\/G1\/members\/\w+\/roles\/\w+$/.test(p)) { const [, , , , u, , r] = p.split("/"); puts.push(r); putsFull.push(u + ":" + r); return new Response(null, { status: roleStatus }); }
  if (p === "/guilds/G1/invites") return invitesStatus === 200 ? j(invitesNow) : j({}, invitesStatus);
  if (p === "/guilds/G1/members") { memberCalls++; return membersStatus === 200 ? j(membersNow) : j({}, membersStatus); }
  return j({}, 404);
};

let fails = 0;
const ok = (c, msg) => { console.log((c ? "PASS " : "FAIL ") + msg); if (!c) fails++; };
const call = (path, opts) => worker.fetch(new Request("https://cv.example" + path, opts), env);
const stateFrom = (res) => new URL(res.headers.get("location")).searchParams.get("state");

// Public pages moved to the ZunimiLabs website; the cloud redirects there without needing service secrets.
for (const [path, to] of [["/", "/chatdoom/"], ["/privacy", "/chatdoom/privacy/"], ["/terms", "/chatdoom/terms/"]]) {
  const publicPage = await worker.fetch(new Request("https://cv.example" + path), {});
  ok(publicPage.status === 301 && publicPage.headers.get("location") === "https://zunimilabs.online" + to, path + " redirects to the website");
}

// 1. bot setup
let r = await call("/setup");
ok(r.status === 302 && r.headers.get("location").includes("permissions=268436513"), "setup redirects to Discord with Manage Roles");
r = await call("/setup/callback?code=abc&state=" + stateFrom(r));
let html = await r.text();
const token = html.match(/<code>([a-z0-9]{40})<\/code>/)?.[1];
ok(r.status === 200 && token, "setup callback shows a server key");
r = await call("/setup/callback?code=abc&state=bogus"); ok(r.status === 400, "bad state rejected");

// 2. auth + config + roles
const H = { Authorization: "Bearer " + token, "content-type": "application/json" };
let res;
r = await call("/api/config", { headers: { Authorization: "Bearer nope" } }); ok(r.status === 401, "wrong key -> 401");
r = await call("/api/roles", { headers: H }); const roles = (await r.json()).roles;
ok(roles.length === 3 && roles[0].name === "Supporter", "roles listed (no @everyone / bot roles), highest first");
r = await call("/api/translate", { method: "POST", headers: H, body: JSON.stringify({ text: "こんにちは", source_lang: "ja" }) });
res = await r.json();
ok(r.status === 200 && res.translation === "Hello from the stream!"
  && translatedInputs.at(-1).model === "@cf/meta/m2m100-1.2b"
  && translatedInputs.at(-1).input.source_lang === "ja"
  && translatedInputs.at(-1).input.target_lang === "en",
  "authenticated translation converts supported-language chat into English");
r = await call("/api/translate", { method: "POST", headers: H, body: JSON.stringify({ text: "안녕", source_lang: "ko", target_lang: "hi" }) });
ok(r.status === 200 && translatedInputs.at(-1).input.target_lang === "hi", "translation can go into a chosen language");
r = await call("/api/translate", { method: "POST", headers: H, body: JSON.stringify({ text: "hi", source_lang: "ko", target_lang: "xx" }) });
ok(r.status === 400, "an unknown target language is refused");
r = await call("/api/translate", { method: "POST", headers: H, body: JSON.stringify({ text: "x".repeat(501), source_lang: "ja" }) });
ok(r.status === 400, "translation input is length-limited");
r = await worker.fetch(new Request("https://cv.example/api/translate", {
  method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ text: "こんにちは", source_lang: "ja" }),
}), { ...env, KV, AI: env.AI });
ok(r.status === 401, "translation endpoint rejects requests without an app server key");
r = await worker.fetch(new Request("https://cv.example/api/translate", {
  method: "POST", headers: H,
  body: JSON.stringify({ text: "こんにちは", source_lang: "ja" }),
}), { ...env, AI: undefined });
ok(r.status === 503, "translation reports a missing Workers AI binding explicitly");
store.set("translate:usage:" + new Date().toISOString().slice(0, 10), "300");
r = await call("/api/translate", { method: "POST", headers: H, body: JSON.stringify({ text: "こんにちは", source_lang: "ja" }) });
ok(r.status === 429, "translation stops at the shared daily quota");
r = await call("/api/config", { method: "PUT", headers: H, body: JSON.stringify({ verifiedRole: "100001", regularRole: "100002", supporterRole: "100003", regularMsgs: 3 }) });
ok((await r.json()).ok, "config saved");
r = await call("/api/config", { method: "PUT", headers: H, body: JSON.stringify({ verifiedRole: "evil" }) }); ok(r.status === 400, "bad role id rejected");

// 3. viewer link flow
r = await call("/link/G1"); ok(r.status === 302, "link page redirects to Discord login");
const lstate = stateFrom(r);
memberOk = false;
let rr = await call("/link/callback?code=x&state=" + lstate); ok(rr.status === 403, "not in server -> asked to join first");
memberOk = true;
r = await call("/link/G1"); r = await call("/link/callback?code=x&state=" + stateFrom(r));
html = await r.text(); const code = html.match(/!link ([A-Z0-9]{4}-[A-Z0-9]{4})/)?.[1];
ok(code, "viewer gets a code: " + code);

// 4. app claims the code from chat
r = await call("/api/claim", { method: "POST", headers: H, body: JSON.stringify({ code: "ZZZZ-ZZZZ", platform: "youtube", uid: "UC1" }) }); ok(r.status === 404, "unknown code rejected");
r = await call("/api/claim", { method: "POST", headers: H, body: JSON.stringify({ code, platform: "youtube", uid: "UC1" }) });
res = await r.json(); ok(res.ok && res.roleGranted && res.discordName === "Rahul", "claim links the account and grants Verified");
ok(puts.includes("100001"), "Discord got Verified role request");
r = await call("/api/claim", { method: "POST", headers: H, body: JSON.stringify({ code, platform: "youtube", uid: "UC2" }) }); ok(r.status === 404, "code is single-use");
r = await call("/api/links", { headers: H }); ok((await r.json()).keys[0] === "youtube:UC1", "links list returned to the app");
// a Twitch viewer links too, since only non-YouTube viewers can earn roles
r = await call("/link/G1"); r = await call("/link/callback?code=x&state=" + stateFrom(r));
const twitchCode = (await r.text()).match(/!link ([A-Z0-9]{4}-[A-Z0-9]{4})/)?.[1];
r = await call("/api/claim", { method: "POST", headers: H, body: JSON.stringify({ code: twitchCode, platform: "twitch", uid: "UC1" }) });
ok((await r.json()).ok, "Twitch viewer linked");

// 5. app reports a threshold -> role is granted (counting happens in the app, so the cloud writes almost nothing)
const grant = (role, uid = "UC1", platform = "twitch") => call("/api/grant", { method: "POST", headers: H, body: JSON.stringify({ platform, uid, role }) });
puts.length = 0; roleStatus = 204;
r = await grant("regular", "UC1", "youtube"); res = await r.json();
ok(r.status === 403 && res.error.includes("YouTube rules") && puts.length === 0, "YouTube viewer is refused a role (YouTube rules)");
r = await grant("regular"); res = await r.json(); ok(res.ok && puts.includes("100002"), "regular role granted through /api/grant");
r = await grant("supporter"); res = await r.json(); ok(res.ok && puts.includes("100003"), "supporter role granted through /api/grant");
r = await grant("regular", "nobody"); ok(r.status === 404, "unlinked viewer cannot be granted a role");
r = await grant("admin"); ok(r.status === 400, "unknown role name rejected");

// 6. failure reporting (bot role too low)
roleStatus = 403;
r = await grant("regular"); res = await r.json(); ok(!res.ok && res.status === 403, "403 from Discord is reported to the app");
roleStatus = 204;

// 7. the failures that used to show Cloudflare's "Error 1101"
const badEnv = { ...env, DISCORD_CLIENT_SECRET: "BAD" };
let st = await worker.fetch(new Request("https://cv.example/setup"), badEnv); const bst = stateFrom(st);
r = await worker.fetch(new Request("https://cv.example/setup/callback?code=x&state=" + bst), badEnv);
html = await r.text(); ok(r.status === 400 && html.includes("invalid_client") && html.includes("Client Secret"), "wrong secret -> readable page, not error 1101");
r = await worker.fetch(new Request("https://cv.example/setup"), { KV });
html = await r.text(); ok(r.status === 500 && html.includes("DISCORD_CLIENT_ID"), "missing secrets -> page that names them");
r = await worker.fetch(new Request("https://cv.example/health"), { KV, DISCORD_CLIENT_ID: "12345678901234567890", DISCORD_CLIENT_SECRET: "x", DISCORD_BOT_TOKEN: "" });
const h = await r.json(); ok(h.DISCORD_CLIENT_ID.looks_right && !h.DISCORD_CLIENT_SECRET.looks_right && !h.DISCORD_BOT_TOKEN.set, "/health reports which settings are missing or look wrong");
ok(!h.GOOGLE_OAUTH_CLIENT_ID.set && !h.PLATFORM_TOKEN_ENCRYPTION_KEY.set && !h.WORKERS_AI.set, "/health reports missing platform OAuth and optional AI setup without revealing values");
r = await call("/platform-auth/start?" + new URLSearchParams({ platform: "youtube", return: "http://127.0.0.1:5599/done" }));
ok(r.status === 503 && (await r.json()).error.includes("GOOGLE_OAUTH_CLIENT_ID"), "platform login fails with an explicit setup instruction when OAuth is not configured");
const broken = { ...env, KV: { async get() { return null; }, async put() { throw new Error("storage down"); }, async delete() {} } };
r = await worker.fetch(new Request("https://cv.example/setup"), broken); ok(r.status === 500 && (await r.text()).includes("storage down"), "unexpected crash -> readable page");


// 8. payments: Razorpay webhook -> D1 queue -> app
class FakeDB {
  constructor() { this.rows = []; this.accounts = []; this.quota = new Map(); this.subscriberQuota = new Map(); this.seq = 0; this.accountSeq = 0; }
  prepare(sql) {
    const self = this;
    return { args: [], bind(...a) { this.args = a; return this; },
      async run() {
        if (sql.startsWith("INSERT OR IGNORE INTO platform_api_quota")) {
          const [day] = this.args;
          if (!self.quota.has(day)) self.quota.set(day, 0);
        }
        if (sql.startsWith("UPDATE platform_api_quota")) {
          const [cost, day, extraCost, limit] = this.args;
          const used = self.quota.get(day) || 0;
          if (used + extraCost <= limit) {
            self.quota.set(day, used + cost);
            return { meta: { changes: 1 } };
          }
          return { meta: { changes: 0 } };
        }
        if (sql.startsWith("INSERT OR IGNORE INTO platform_subscriber_quota")) {
          const [day] = this.args;
          if (!self.subscriberQuota.has(day)) self.subscriberQuota.set(day, 0);
        }
        if (sql.startsWith("UPDATE platform_subscriber_quota")) {
          const [cost, day, extraCost, limit] = this.args;
          const used = self.subscriberQuota.get(day) || 0;
          if (used + extraCost <= limit) {
            self.subscriberQuota.set(day, used + cost);
            return { meta: { changes: 1 } };
          }
          return { meta: { changes: 0 } };
        }
        if (sql.startsWith("INSERT INTO platform_accounts")) {
          const [session_hash, platform, provider_user_id, display_name, access_token, refresh_token, expires_at] = this.args;
          let row = self.accounts.find((x) => x.session_hash === session_hash);
          if (!row) { row = { id: ++self.accountSeq }; self.accounts.push(row); }
          Object.assign(row, { session_hash, platform, provider_user_id, display_name, access_token, refresh_token, expires_at });
        }
        if (sql.startsWith("UPDATE platform_accounts")) {
          if (sql.includes("SET provider_user_id")) {
            const [provider_user_id, id] = this.args;
            const row = self.accounts.find((x) => x.id === id);
            if (row) row.provider_user_id = provider_user_id;
          } else {
            const [access_token, refresh_token, expires_at, id] = this.args;
            const row = self.accounts.find((x) => x.id === id);
            if (row) Object.assign(row, { access_token, refresh_token, expires_at });
          }
        }
        if (sql.startsWith("DELETE FROM platform_accounts")) {
          const previous = self.accounts.length;
          self.accounts = self.accounts.filter((x) => x.session_hash !== this.args[0]);
          return { meta: { changes: previous - self.accounts.length } };
        }
        if (sql.startsWith("INSERT OR IGNORE INTO tips")) {
          const [guild, pay_id, ts, name, message, amount, currency, display] = this.args;
          if (!self.rows.some((x) => x.guild === guild && x.pay_id === pay_id)) self.rows.push({ seq: ++self.seq, guild, pay_id, ts, name, message, amount, currency, display });
        }
        if (sql.startsWith("DELETE")) self.rows = self.rows.filter((x) => x.ts >= this.args[0]);
        return {};
      },
      async first() {
        if (sql.startsWith("SELECT * FROM platform_accounts")) return self.accounts.find((x) => x.session_hash === this.args[0]) || null;
        const m = self.rows.filter((x) => x.guild === this.args[0]).reduce((a, x) => Math.max(a, x.seq), 0);
        return { m };
      },
      async all() { return { results: self.rows.filter((x) => x.guild === this.args[0] && x.seq > this.args[1]).slice(0, 20) }; } };
  }
}
env.DB = new FakeDB();
Object.assign(env, {
  GOOGLE_OAUTH_CLIENT_ID: "GOOGLE_CLIENT_ID",
  GOOGLE_OAUTH_CLIENT_SECRET: "GOOGLE_CLIENT_SECRET",
  TWITCH_CLIENT_ID: "TWITCH_CLIENT_ID",
  TWITCH_CLIENT_SECRET: "TWITCH_CLIENT_SECRET",
  KICK_CLIENT_ID: "KICK_CLIENT_ID",
  KICK_CLIENT_SECRET: "KICK_CLIENT_SECRET",
  PLATFORM_TOKEN_ENCRYPTION_KEY: Buffer.alloc(32, 7).toString("base64"),
});
const localReturn = "http://127.0.0.1:5599/done";
const beginPlatformLogin = async (platform) => {
  const started = await call("/platform-auth/start?" + new URLSearchParams({ platform, return: localReturn }));
  const auth = await started.json();
  const authorize = new URL(auth.authorizeUrl);
  const callback = await call("/platform-auth/" + platform + "/callback?" + new URLSearchParams({
    state: authorize.searchParams.get("state"), code: "provider-code",
  }));
  return { started, authorize, callback };
};
let ytLogin = await beginPlatformLogin("youtube");
let ytReturn = new URL(ytLogin.callback.headers.get("location"));
ok(ytLogin.started.status === 200 && ytLogin.authorize.searchParams.get("scope").includes("youtube.force-ssl")
  && ytReturn.origin + ytReturn.pathname === localReturn && ytReturn.searchParams.get("ok") === "1"
  && !!ytReturn.searchParams.get("ticket") && !ytReturn.search.includes("YT_ACCESS"),
"YouTube OAuth uses required scope and returns only a short-lived one-time ticket");
let redeemed = await call("/platform-auth/redeem", { method: "POST", body: JSON.stringify({ ticket: ytReturn.searchParams.get("ticket") }) });
let ytAccount = await redeemed.json();
let ytHeaders = { Authorization: "Bearer " + ytAccount.session, "content-type": "application/json" };
ok(redeemed.status === 200 && ytAccount.platform === "youtube" && ytAccount.displayName === "Test YouTube Channel",
  "YouTube OAuth ticket redeems into an app session and account identity");
r = await call("/platform-auth/redeem", { method: "POST", body: JSON.stringify({ ticket: ytReturn.searchParams.get("ticket") }) });
ok(r.status === 400, "OAuth ticket can only be redeemed once");
r = await call("/platform-auth/account", { headers: ytHeaders });
ok((await r.json()).displayName === "Test YouTube Channel", "YouTube account session is recognized");
const ytRow = env.DB.accounts.find((x) => x.platform === "youtube");
ytRow.expires_at = Math.floor(Date.now() / 1000) - 1;
r = await call("/platform-auth/account", { headers: ytHeaders });
ok(r.status === 200 && ytRow.expires_at > Math.floor(Date.now() / 1000) && !ytRow.access_token.includes("YT_ACCESS_2"),
  "expired YouTube access tokens refresh and remain encrypted in D1");
globalThis.youtubeLookupFails = true;
r = await call("/platform-auth/message", { method: "POST", headers: ytHeaders, body: JSON.stringify({ platform: "youtube", videoId: "abcdefghijk", text: "Hello chat" }) });
res = await r.json();
ok(res.error.includes("Google said no") && !res.error.includes("[object Object]"), "Google's error text reaches the streamer");
globalThis.youtubeLookupFails = false;
r = await call("/platform-auth/youtube-broadcasts", { headers: ytHeaders });
res = await r.json();
ok(r.status === 200 && res.broadcasts.map((b) => b.id).join() === "abcdefghijk,scheduled01,oldstream01"
  && res.broadcasts[0].live && res.broadcasts[1].privacy === "unlisted" && !res.broadcasts[1].stale && res.broadcasts[2].stale,
  "sign-in finds live, then scheduled (unlisted included), then old entries");
r = await call("/platform-auth/message", { method: "POST", headers: ytHeaders, body: JSON.stringify({ platform: "youtube", videoId: "abcdefghijk", text: "Hello chat" }) });
ok(r.status === 200 && platformCalls.some((x) => x.platform === "youtube" && x.body.snippet.textMessageDetails.messageText === "Hello chat"),
  "YouTube message is sent to the signed-in channel's active live chat");
r = await call("/platform-auth/poll", { method: "POST", headers: ytHeaders, body: JSON.stringify({ platform: "youtube", videoId: "abcdefghijk", question: "Next game?", options: ["A", "B"] }) });
ok(r.status === 200 && platformCalls.some((x) => x.platform === "youtube" && x.body.snippet.type === "pollEvent" && x.body.snippet.pollDetails.metadata.options.length === 2),
  "YouTube live poll is created with valid choices");
const moderate = (headers, body) => call("/platform-auth/moderate", { method: "POST", headers, body: JSON.stringify(body) });
r = await call("/platform-auth/live-streams", { headers: ytHeaders });
res = await r.json();
ok(r.status === 200 && res.account === "Test YouTube Channel" && res.streams.length === 1 && res.streams[0].id === "abcdefghijk" && res.streams[0].format === "long",
  "live-streams names the account and only lists what is live now");
const formatCalls = platformCalls.length;
await call("/platform-auth/live-streams", { headers: ytHeaders });
ok(store.get("yt-format:abcdefghijk") === "long" && platformCalls.length === formatCalls, "a stream's format is remembered, so polling costs no extra lookups");
r = await moderate(ytHeaders, { platform: "youtube", action: "timeout", videoId: "abcdefghijk", userId: VIEWER_CHANNEL, seconds: 600 });
res = await r.json();
let modCall = modCalls.at(-1);
ok(r.status === 200 && res.banId === "BAN-1" && modCall.body.snippet.type === "temporary" && modCall.body.snippet.banDurationSeconds === 600
  && modCall.body.snippet.bannedUserDetails.channelId === VIEWER_CHANNEL, "a YouTube time-out uses the fields Google documents and returns the ban id");
r = await moderate(ytHeaders, { platform: "youtube", action: "ban", videoId: "abcdefghijk", userId: VIEWER_CHANNEL });
modCall = modCalls.at(-1);
ok(r.status === 200 && modCall.body.snippet.type === "permanent" && !("banDurationSeconds" in modCall.body.snippet), "a YouTube ban is permanent with no duration");
r = await moderate(ytHeaders, { platform: "youtube", action: "unban", banId: "BAN-1" });
ok(r.status === 200 && modCalls.at(-1).verb === "DELETE" && modCalls.at(-1).query.includes("BAN-1"), "a YouTube ban is undone by its id");
r = await moderate(ytHeaders, { platform: "youtube", action: "unban" });
ok(r.status === 400, "without a ban id YouTube cannot undo a ban, and the streamer is told");
r = await moderate(ytHeaders, { platform: "youtube", action: "delete", videoId: "abcdefghijk", userId: VIEWER_CHANNEL, text: "bad words" });
ok(r.status === 200 && modCalls.at(-1).verb === "DELETE" && modCalls.at(-1).query.includes("LCC.1"), "a YouTube message is found by viewer and text, then removed");
r = await moderate(ytHeaders, { platform: "youtube", action: "addMod", videoId: "abcdefghijk", userId: VIEWER_CHANNEL });
ok(r.status === 200 && modCalls.at(-1).body.snippet.moderatorDetails.channelId === VIEWER_CHANNEL, "a viewer can be made a moderator");
r = await moderate(ytHeaders, { platform: "youtube", action: "endPoll", pollId: "POLL-1" });
ok(r.status === 200 && modCalls.at(-1).query.includes("status=closed"), "a YouTube poll is ended with status closed");
r = await moderate(ytHeaders, { platform: "youtube", action: "timeout", videoId: "abcdefghijk", userId: "not-a-channel" });
ok(r.status === 400, "a bad viewer id never reaches YouTube");
r = await moderate(ytHeaders, { platform: "youtube", action: "chatMode", videoId: "abcdefghijk" });
ok(r.status === 400 && (await r.json()).error.includes("does not offer"), "YouTube chat modes are refused with a plain reason");
r = await moderate(ytHeaders, { platform: "twitch", action: "timeout", userId: "1" });
ok(r.status === 400, "a session only acts on its own platform");
r = await call("/platform-auth/moderate", { method: "POST", body: JSON.stringify({ platform: "youtube", action: "ban" }) });
ok(r.status === 401, "owner actions need a signed-in session");
youtubeSubscribers = [{
  id: "YT_SUB_1", snippet: { publishedAt: new Date(Date.now() - 10000).toISOString() },
  subscriberSnippet: { title: "Public new subscriber" },
}, {
  id: "YT_SUB_PRIVATE", snippet: { publishedAt: new Date(Date.now() - 5000).toISOString() },
}];
r = await call("/platform-auth/youtube-subscribers", {
  method: "POST", headers: ytHeaders, body: JSON.stringify({ since: Date.now() - 30000 }),
});
const subscriberResult = await r.json();
ok(r.status === 200 && subscriberResult.publicSubscribersOnly && subscriberResult.subscribers.length === 1
  && subscriberResult.subscribers[0].name === "Public new subscriber"
  && platformCalls.some((x) => x.path === "/youtube/v3/subscriptions" && x.url.includes("forChannelId=UC")),
  "YouTube alerts poll recent public subscribers and omit private subscriber identities");
const subscriberQuotaDay = [...env.DB.subscriberQuota.keys()][0];
env.DB.subscriberQuota.set(subscriberQuotaDay, 2000);
const callsBeforeSubscriberLimit = platformCalls.length;
r = await call("/platform-auth/youtube-subscribers", {
  method: "POST", headers: ytHeaders, body: JSON.stringify({ since: Date.now() - 30000 }),
});
ok(r.status === 429 && platformCalls.length === callsBeforeSubscriberLimit,
  "public-subscriber polling respects its separate shared daily quota");
const quotaDay = [...env.DB.quota.keys()][0], apiCallsBeforeQuotaLimit = platformCalls.length;
env.DB.quota.set(quotaDay, 8000);
r = await call("/platform-auth/message", { method: "POST", headers: ytHeaders, body: JSON.stringify({ platform: "youtube", videoId: "abcdefghijk", text: "Over quota" }) });
ok(r.status === 429 && (await r.json()).error.includes("shared YouTube action budget") && platformCalls.length === apiCallsBeforeQuotaLimit,
  "daily shared YouTube budget blocks actions before another API call");
ok(!JSON.stringify(env.DB.accounts).includes("YT_ACCESS") && !JSON.stringify(env.DB.accounts).includes("YT_REFRESH"),
  "platform OAuth access and refresh tokens are encrypted before D1 storage");

let twLogin = await beginPlatformLogin("twitch");
let twReturn = new URL(twLogin.callback.headers.get("location"));
let twRedeemed = await call("/platform-auth/redeem", { method: "POST", body: JSON.stringify({ ticket: twReturn.searchParams.get("ticket") }) });
let twAccount = await twRedeemed.json();
let twHeaders = { Authorization: "Bearer " + twAccount.session, "content-type": "application/json" };
ok(["moderator:manage:banned_users", "moderator:manage:chat_messages", "moderator:manage:chat_settings"].every((s) => twLogin.authorize.searchParams.get("scope").includes(s)),
  "Twitch login asks for the moderation permissions");
r = await call("/platform-auth/live-streams", { headers: twHeaders });
res = await r.json();
ok(r.status === 200 && res.streams.length === 1 && res.streams[0].title === "Ranked grind" && res.channel, "Twitch live-streams gives the channel and the live stream");
twitchLive = false;
r = await call("/platform-auth/live-streams", { headers: twHeaders });
ok((await r.json()).streams.length === 0, "an offline Twitch channel lists no streams");
r = await moderate(twHeaders, { platform: "twitch", action: "timeout", userId: "777", seconds: 300, reason: "spam" });
ok(r.status === 200 && modCalls.at(-1).path === "/helix/moderation/bans" && modCalls.at(-1).body.data.duration === 300 && modCalls.at(-1).body.data.user_id === "777", "a Twitch time-out is sent");
r = await moderate(twHeaders, { platform: "twitch", action: "ban", userId: "777" });
ok(r.status === 200 && !("duration" in modCalls.at(-1).body.data), "a Twitch ban has no duration");
r = await moderate(twHeaders, { platform: "twitch", action: "delete", messageId: "abc-1" });
ok(r.status === 200 && modCalls.at(-1).verb === "DELETE" && modCalls.at(-1).query.includes("message_id=abc-1"), "a Twitch message is removed by id");
r = await moderate(twHeaders, { platform: "twitch", action: "chatMode", settings: { slow_mode: true, slow_mode_wait_time: 30, nonsense: true } });
ok(r.status === 200 && modCalls.at(-1).body.slow_mode === true && modCalls.at(-1).body.slow_mode_wait_time === 30 && !("nonsense" in modCalls.at(-1).body), "Twitch slow mode is set and only known settings pass");
twitchDenies = true;
r = await moderate(twHeaders, { platform: "twitch", action: "clear" });
res = await r.json();
ok(r.status === 403 && res.error.includes("sign in again"), "an old Twitch sign-in is told to sign in again for moderation");
twitchDenies = false;
ok(twLogin.authorize.searchParams.get("scope").includes("user:write:chat")
  && twLogin.authorize.searchParams.get("scope").includes("channel:manage:polls")
  && twLogin.authorize.searchParams.get("scope").includes("moderator:read:followers")
  && twLogin.authorize.searchParams.get("scope").includes("channel:read:subscriptions")
  && twAccount.displayName === "Test Twitch", "Twitch login requests chat, poll, follow, and subscription permissions");
r = await call("/platform-auth/eventsub", {
  method: "POST", headers: twHeaders, body: JSON.stringify({ sessionId: "eventsub-session-123" }),
});
const eventSubResult = await r.json();
ok(r.status === 200 && eventSubResult.ok && eventSubResult.subscribed.length === 5
  && eventSubCalls.some((x) => x.body.type === "channel.follow" && x.body.version === "2"
    && x.body.transport.session_id === "eventsub-session-123")
  && eventSubCalls.some((x) => x.body.type === "channel.subscription.gift")
  && eventSubCalls.some((x) => x.body.type === "channel.raid"),
  "Twitch EventSub registers follow, subscribe, resub, gift, and raid notifications on the desktop socket");
r = await call("/platform-auth/message", { method: "POST", headers: twHeaders, body: JSON.stringify({ platform: "twitch", text: "Hello Twitch" }) });
ok(r.status === 200 && platformCalls.some((x) => x.path === "/helix/chat/messages" && x.body.message === "Hello Twitch"),
  "Twitch chat message is sent with the signed-in broadcaster account");
r = await call("/platform-auth/poll", { method: "POST", headers: twHeaders, body: JSON.stringify({ platform: "twitch", question: "Next game?", options: ["A", "B"], duration: 60 }) });
ok(r.status === 200 && platformCalls.some((x) => x.path === "/helix/polls" && x.body.choices.length === 2),
  "Twitch poll is created with the signed-in broadcaster account");

let kickLogin = await beginPlatformLogin("kick");
let kickReturn = new URL(kickLogin.callback.headers.get("location"));
let kickAccount = await (await call("/platform-auth/redeem", { method: "POST", body: JSON.stringify({ ticket: kickReturn.searchParams.get("ticket") }) })).json();
let kickHeaders = { Authorization: "Bearer " + kickAccount.session, "content-type": "application/json" };
const kickVerifier = kickTokenCalls[0]?.get("code_verifier") || "";
const kickChallenge = createHash("sha256").update(kickVerifier).digest("base64url");
ok(kickLogin.authorize.origin + kickLogin.authorize.pathname === "https://id.kick.com/oauth/authorize"
  && kickLogin.authorize.searchParams.get("scope") === "user:read channel:read chat:write moderation:ban moderation:chat_message:manage events:subscribe"
  && kickLogin.authorize.searchParams.get("code_challenge_method") === "S256"
  && kickVerifier.length >= 43 && kickLogin.authorize.searchParams.get("code_challenge") === kickChallenge
  && !kickLogin.authorize.toString().includes(kickVerifier),
  "Kick login sends an S256 challenge that matches the verifier kept on the server");
ok(kickReturn.searchParams.get("ok") === "1" && kickAccount.displayName === "Test Kick" && kickAccount.userId === "4242"
  && kickTokenCalls[0].get("grant_type") === "authorization_code" && kickTokenCalls[0].get("client_secret") === "KICK_CLIENT_SECRET",
  "Kick login exchanges the code and reads the signed-in account");
r = await call("/platform-auth/message", { method: "POST", headers: kickHeaders, body: JSON.stringify({ platform: "kick", text: "Hello Kick" }) });
const kickSent = platformCalls.find((x) => x.platform === "kick");
ok(r.status === 200 && kickSent && kickSent.body.content === "Hello Kick" && kickSent.body.type === "user"
  && kickSent.body.broadcaster_user_id === 4242 && kickSent.headers.Authorization === "Bearer KICK_ACCESS",
  "Kick chat message is sent with the signed-in broadcaster account");
r = await call("/platform-auth/message", { method: "POST", headers: kickHeaders, body: JSON.stringify({ platform: "kick", text: "Hi", replyTo: "uuid-1" }) });
ok(r.status === 200 && platformCalls.filter((x) => x.platform === "kick").at(-1).body.reply_to_message_id === "uuid-1", "a Kick reply carries the message id");
r = await call("/platform-auth/live-streams", { headers: kickHeaders });
res = await r.json();
ok(r.status === 200 && res.channel === "test-kick" && res.streams.length === 1 && res.streams[0].title === "Kick live", "Kick live-streams reads the channel and live state");
kickNoChannelScope = true;
r = await call("/platform-auth/live-streams", { headers: kickHeaders });
ok((await r.json()).needsLogin === true, "an old Kick sign-in is asked to sign in again, without an error");
kickNoChannelScope = false;
r = await moderate(kickHeaders, { platform: "kick", action: "timeout", userId: "55", seconds: 90 });
ok(r.status === 200 && modCalls.at(-1).body.duration === 2 && modCalls.at(-1).body.user_id === 55 && modCalls.at(-1).body.broadcaster_user_id === 4242, "a Kick time-out is sent in whole minutes");
r = await moderate(kickHeaders, { platform: "kick", action: "unban", userId: "55" });
ok(r.status === 200 && modCalls.at(-1).verb === "DELETE" && modCalls.at(-1).body.user_id === 55, "Kick unban sends the viewer in the body");
r = await moderate(kickHeaders, { platform: "kick", action: "delete", messageId: "uuid-1" });
ok(r.status === 200 && modCalls.at(-1).path === "/public/v1/chat/uuid-1", "a Kick message is removed by id");
const callsBeforeKickPoll = platformCalls.length;
r = await call("/platform-auth/poll", { method: "POST", headers: kickHeaders, body: JSON.stringify({ platform: "kick", question: "Next game?", options: ["A", "B"] }) });
ok(r.status === 400 && platformCalls.length === callsBeforeKickPoll, "Kick polls are refused and never reach Twitch");
r = await call("/platform-auth/account", { method: "DELETE", headers: kickHeaders });
ok(r.status === 200 && kickRevokeCalls.length === 1 && kickRevokeCalls[0].searchParams.get("token") === "KICK_REFRESH"
  && kickRevokeCalls[0].searchParams.get("token_hint_type") === "refresh_token", "Disconnect revokes the Kick token");
r = await call("/platform-auth/account", { headers: kickHeaders });
ok(r.status === 401, "a disconnected Kick session stops working");

r = await call("/platform-auth/account", { method: "DELETE", headers: ytHeaders });
ok(r.status === 200, "disconnect removes only the YouTube account session");
r = await call("/platform-auth/account", { headers: ytHeaders });
ok(r.status === 401, "disconnected platform session cannot be reused");

const { createHmac } = await import("node:crypto");
const SECRET = "whsec_test_123";
r = await call("/api/config", { method: "PUT", headers: H, body: JSON.stringify({ verifiedRole: "100001", regularRole: "100002", supporterRole: "100003", regularMsgs: 3, razorpaySecret: SECRET }) });
let cfgRes = await r.json();
ok(cfgRes.ok && cfgRes.config.hasRazorpaySecret && cfgRes.config.hookUrl.includes("/hook/razorpay/") && !JSON.stringify(cfgRes).includes(SECRET), "secret saved, hook URL created, secret never sent back");
const hookPath = new URL(cfgRes.config.hookUrl).pathname;
r = await call("/api/config", { headers: H }); const got = await r.json();
ok(got.config.verifiedRole === "100001" && got.config.hasRazorpaySecret, "role settings survive when payment settings are saved");

r = await call("/api/config", { method: "PUT", headers: H, body: JSON.stringify({ razorpaySecret: SECRET }) });
r = await call("/api/config", { headers: H }); const kept = (await r.json()).config;
ok(kept.supporterRole === "100003" && kept.regularMsgs === 3 && kept.hasRazorpaySecret, "saving only the payment secret does not wipe the role settings");

const payEvent = (id, notes, amount = 10000, currency = "INR", event = "payment.captured") =>
  JSON.stringify({ event, payload: { payment: { entity: { id, amount, currency, notes } } } });
const hook = (body, secret = SECRET) => call(hookPath, { method: "POST", body, headers: { "X-Razorpay-Signature": createHmac("sha256", secret).update(body).digest("hex") } });
const events = (after) => call("/api/events?after=" + after, { headers: H }).then((x) => x.json());

let ev = await events(-1); ok(ev.latest === 0 && ev.events.length === 0, "app starts at the newest tip (no replay of old ones)");
r = await call(hookPath, { method: "POST", body: payEvent("pay_1", {}), headers: { "X-Razorpay-Signature": "00" } }); ok(r.status === 400, "forged webhook rejected");
r = await hook(payEvent("pay_1", { name: "Rahul", message: "Great stream bhai!" })); ok(r.status === 200, "valid webhook accepted");
r = await hook(payEvent("pay_1", { name: "Rahul", message: "Great stream bhai!" })); ok(r.status === 200, "duplicate delivery accepted");
r = await hook(payEvent("pay_2", [], 50000)); ok(r.status === 200, "payment with empty notes (array) accepted");
r = await hook(payEvent("pay_3", { "Your Name": "Sam", "Your Message": "Hello from USA", email: "x@y.z" }, 500, "USD")); ok(r.status === 200, "international payment accepted");
r = await hook(payEvent("pay_4", {}, 100, "INR", "payment.failed")); res = await r.json(); ok(res.ignored === "payment.failed", "other events ignored");
ev = await events(0);
ok(ev.events.length === 3, "duplicates and ignored events are not queued (3 tips)");
ok(ev.events[0].name === "Rahul" && ev.events[0].message === "Great stream bhai!" && ev.events[0].display === "₹100", "tip 1: name, message and amount ₹100");
ok(ev.events[1].name === "Someone" && ev.events[1].display === "₹500", "tip 2: no name -> Someone, amount ₹500");
ok(ev.events[2].name === "Sam" && ev.events[2].message === "Hello from USA" && ev.events[2].display === "$5", "tip 3: fields found by label, $5");
const next = await events(ev.events[1].seq); ok(next.events.length === 1 && next.events[0].id === "pay_3", "cursor returns only newer tips");
r = await hook(payEvent("pay_5", { message: "wrong secret" }), "other_secret"); ok(r.status === 400, "signature made with a different secret rejected");
env.DB = undefined;
r = await call("/api/events?after=0", { headers: H }); ok(r.status === 500 && (await r.json()).error.includes("not set up"), "missing database -> clear message");


// 9. invite roles: normal discord.gg invites decide who gets which role (no login page needed)
const minutesAgo = (n) => new Date(Date.now() - n * 60000).toISOString();
const member = (id, joined = 1, bot = false) => ({ user: { id, bot }, joined_at: minutesAgo(joined) });
const runCron = async () => { let p; await worker.scheduled({}, env, { waitUntil: (x) => (p = x) }); await p; };
r = await call("/api/config", { method: "PUT", headers: H, body: JSON.stringify({ inviteRules: [{ code: "https://discord.gg/YTinvite1", role: "100001", label: "YouTube" }, { code: "TWinvite2", role: "100002", label: "Twitch" }] }) });
cfgRes = await r.json();
ok(cfgRes.ok && cfgRes.config.inviteRules.length === 2 && cfgRes.config.inviteRules[0].code === "YTinvite1", "invite roles saved; a full discord.gg link is reduced to its code");
r = await call("/api/config", { method: "PUT", headers: H, body: JSON.stringify({ inviteRules: [{ code: "https://evil.example/abc", role: "100001" }] }) }); ok(r.status === 400, "invite rule with a non-Discord link rejected");
r = await call("/api/config", { headers: H }); ok((await r.json()).config.hasRazorpaySecret, "payment settings still intact after saving invite roles");

invitesNow = [{ code: "YTinvite1", uses: 5 }, { code: "TWinvite2", uses: 2 }, { code: "other", uses: 9 }];
r = await call("/api/invites/check", { method: "POST", headers: H, body: "{}" }); res = await r.json();
ok(!res.error && res.rules[0].found && res.rules[0].uses === 5 && res.notes[0].includes("Now watching"), "first check: invites found and use counts shown, nothing granted");
puts.length = 0; putsFull.length = 0; memberCalls = 0;
await runCron(); ok(memberCalls === 0 && putsFull.length === 0, "no joins: members are not even looked up");

invitesNow = [{ code: "YTinvite1", uses: 6 }, { code: "TWinvite2", uses: 2 }, { code: "other", uses: 9 }];
membersNow = [member("U100", 600), member("U200", 1), member("BOT1", 1, true)];
await runCron();
ok(putsFull.join() === "U200:100001", "one join through the YouTube invite -> that member gets the YouTube role (old members and bots ignored)");
putsFull.length = 0; await runCron(); ok(putsFull.length === 0, "same join is not processed twice");

invitesNow = [{ code: "YTinvite1", uses: 7 }, { code: "TWinvite2", uses: 3 }, { code: "other", uses: 9 }];
membersNow = [member("U200", 3), member("U300", 1), member("U400", 1)];
await runCron(); ok(putsFull.length === 0, "two different invites used at once -> no guessing, no roles");
r = await call("/api/invites/check", { method: "POST", headers: H, body: "{}" }); res = await r.json();
ok(res.assigned.length === 0 && !res.error, "check endpoint still works afterwards");

invitesNow = [{ code: "YTinvite1", uses: 7 }, { code: "TWinvite2", uses: 4 }, { code: "other", uses: 9 }];
membersNow = [member("U500", 1)];
await runCron(); ok(putsFull.join() === "U500:100002", "a join through the Twitch invite gets the Twitch role");

putsFull.length = 0; invitesNow = [{ code: "YTinvite1", uses: 8 }, { code: "TWinvite2", uses: 4 }, { code: "other", uses: 9 }];
membersNow = [member("U600", 1)]; membersStatus = 403;
r = await call("/api/invites/check", { method: "POST", headers: H, body: "{}" }); res = await r.json();
ok(res.error && res.error.includes("Server Members Intent"), "members intent off -> clear instruction");
membersStatus = 200; invitesStatus = 403;
r = await call("/api/invites/check", { method: "POST", headers: H, body: "{}" }); res = await r.json();
ok(res.error && res.error.includes("Manage Server"), "bot without Manage Server -> clear instruction");
invitesStatus = 200;
r = await call("/api/config", { method: "PUT", headers: H, body: JSON.stringify({ inviteRules: [] }) });
puts.length = 0; await runCron(); ok(puts.length === 0, "with no invite roles the scheduled check does nothing");


// 10. more gateways: Stripe, Cashfree, and a universal webhook for any other tool
env.DB = new FakeDB();
r = await call("/api/config", { method: "PUT", headers: H, body: JSON.stringify({ stripeSecret: "whsec_stripe", cashfreeSecret: "cf_secret", genericSecret: "my_generic_secret" }) });
cfgRes = await r.json();
ok(cfgRes.config.hasStripeSecret && cfgRes.config.hasCashfreeSecret && cfgRes.config.hasGenericSecret && ["razorpay", "stripe", "cashfree", "generic"].every((g) => cfgRes.config.hookUrls[g].includes("/hook/" + g + "/")), "one address per gateway is created");
ok(!/whsec_stripe|cf_secret|my_generic_secret/.test(JSON.stringify(cfgRes)), "no gateway secret is ever sent back");
const hp = (g) => new URL(cfgRes.config.hookUrls[g]).pathname;
const base = (await events(-1)).latest;

// Stripe
const stripeEv = (id, over = {}) => JSON.stringify({ id: "evt_" + id, type: "checkout.session.completed", data: { object: { id, payment_status: "paid", amount_total: 500, currency: "usd",
  customer_details: { name: "Card Holder" }, custom_fields: [{ key: "message", label: { custom: "Your message", type: "custom" }, type: "text", text: { value: "Hi from Stripe" } }, { key: "name", label: { custom: "Name", type: "custom" }, type: "text", text: { value: "Anna" } }], ...over } } });
const stripeHdr = (body, t = Math.floor(Date.now() / 1000), secret = "whsec_stripe", extra = "") => ({ "Stripe-Signature": `t=${t},${extra}v1=${createHmac("sha256", secret).update(t + "." + body).digest("hex")}` });
let body = stripeEv("cs_1");
r = await call(hp("stripe"), { method: "POST", body, headers: stripeHdr(body) }); ok(r.status === 200, "Stripe: valid signature accepted");
r = await call(hp("stripe"), { method: "POST", body, headers: stripeHdr(body, Math.floor(Date.now() / 1000) - 900) }); ok(r.status === 400, "Stripe: old timestamp rejected (replay protection)");
r = await call(hp("stripe"), { method: "POST", body, headers: stripeHdr(body, undefined, "wrong") }); ok(r.status === 400, "Stripe: wrong secret rejected");
body = stripeEv("cs_2");
r = await call(hp("stripe"), { method: "POST", body, headers: stripeHdr(body, undefined, "whsec_stripe", "v1=deadbeef,") }); ok(r.status === 200, "Stripe: accepted when one of several v1 signatures matches");
body = stripeEv("cs_3", { payment_status: "unpaid" });
r = await call(hp("stripe"), { method: "POST", body, headers: stripeHdr(body) }); res = await r.json(); ok(res.ignored === "not paid yet", "Stripe: unpaid sessions are ignored");
body = stripeEv("cs_4", { amount_total: 500, currency: "jpy", custom_fields: [] });
r = await call(hp("stripe"), { method: "POST", body, headers: stripeHdr(body) }); ok(r.status === 200, "Stripe: payment without custom fields accepted");
body = JSON.stringify({ type: "charge.refunded", data: { object: {} } });
r = await call(hp("stripe"), { method: "POST", body, headers: stripeHdr(body) }); res = await r.json(); ok(res.ignored === "charge.refunded", "Stripe: other events ignored");

// Cashfree (signature = base64 of HMAC(timestamp + body))
const cfBody = (id, over = {}) => JSON.stringify({ type: "PAYMENT_SUCCESS_WEBHOOK", data: { order: { order_id: id, order_amount: 100.0, order_currency: "INR", order_note: "Nice stream" }, payment: { cf_payment_id: 555 }, customer_details: { customer_name: "Sam" } }, ...over });
const cfHdr = (body, secret = "cf_secret", ts = String(Date.now())) => ({ "x-webhook-timestamp": ts, "x-webhook-signature": createHmac("sha256", secret).update(ts + body).digest("base64") });
body = cfBody("order_1");
r = await call(hp("cashfree"), { method: "POST", body, headers: cfHdr(body) }); ok(r.status === 200, "Cashfree: valid signature accepted");
r = await call(hp("cashfree"), { method: "POST", body, headers: cfHdr(body, "bad") }); ok(r.status === 400, "Cashfree: wrong secret rejected");
body = cfBody("order_2", { type: "PAYMENT_FAILED_WEBHOOK" });
r = await call(hp("cashfree"), { method: "POST", body, headers: cfHdr(body) }); res = await r.json(); ok(res.ignored === "payment_failed_webhook", "Cashfree: failed payments ignored");

// universal webhook
const gen = (obj, hdr = {}) => call(hp("generic"), { method: "POST", body: JSON.stringify(obj), headers: hdr });
r = await gen({ id: "g1", name: "Zed", message: "via any tool", amount: 75, currency: "INR" }, { "X-ChatVoice-Secret": "my_generic_secret" }); ok(r.status === 200, "Universal: secret in header accepted");
r = await gen({ id: "g2", name: "Yo", message: "secret in body", amount: 10.5, secret: "my_generic_secret" }); ok(r.status === 200, "Universal: secret in body accepted");
r = await gen({ id: "g3", name: "Nope", amount: 10 }, { "X-ChatVoice-Secret": "wrong" }); ok(r.status === 400, "Universal: wrong secret rejected");
r = await gen({ id: "g4", name: "NoAmount", secret: "my_generic_secret" }); res = await r.json(); ok(res.ignored === "no amount", "Universal: missing amount ignored");
r = await gen({ id: "g1", name: "Zed", message: "via any tool", amount: 75, currency: "INR" }, { "X-ChatVoice-Secret": "my_generic_secret" }); ok(r.status === 200, "Universal: duplicate id accepted but not queued twice");

// the queue
ev = await events(base);
const by = (id) => ev.events.find((e) => e.id === id);
ok(ev.events.length === 6, "all valid payments queued exactly once (6)");
ok(by("cs_1").name === "Anna" && by("cs_1").message === "Hi from Stripe" && by("cs_1").display === "$5", "Stripe: name and message from custom fields, $5");
ok(by("cs_4").name === "Card Holder" && by("cs_4").display === "JPY 500", "Stripe: falls back to card holder name; yen has no cents");
ok(by("order_1") === undefined && ev.events.some((e) => e.id === "555" && e.name === "Sam" && e.message === "Nice stream" && e.display === "₹100"), "Cashfree: name, note and ₹100 found");
ok(by("g1").display === "₹75" && by("g2").display === "₹10.50" && by("g2").message === "secret in body", "Universal: amounts and messages read correctly");


// 11. simple setup: the app is sent back by the browser, and one click makes roles + invite links
const CBK = "http://127.0.0.1:5599/done";
r = await call("/setup?return=" + encodeURIComponent("http://evil.example/steal")); ok(r.status === 400, "return address must be a program on this PC");
r = await call("/setup?return=" + encodeURIComponent("http://127.0.0.1:5599/done")); ok(r.status === 302 && r.headers.get("location").includes("discord.com/oauth2/authorize"), "setup with a local return address goes to Discord");
let st2 = stateFrom(r);
r = await call("/setup/callback?code=abc&state=" + st2);
const back = new URL(r.headers.get("location"));
ok(r.status === 302 && back.origin + back.pathname === CBK && back.searchParams.get("ok") === "1" && back.searchParams.get("guild") === "Test Server", "after Authorize, the browser sends the key straight back to the app");
const newKey = back.searchParams.get("token");
r = await call("/api/config", { headers: { Authorization: "Bearer " + newKey } }); ok(r.status === 200, "the key delivered to the app works (no copy and paste)");
H.Authorization = "Bearer " + newKey;
r = await call("/setup?return=" + encodeURIComponent(CBK)); st2 = stateFrom(r);
r = await call("/setup/callback?error=access_denied&state=" + st2); const cancelled = new URL(r.headers.get("location"));
ok(cancelled.searchParams.get("ok") === "0" && cancelled.searchParams.get("error") === "access_denied", "pressing Cancel on Discord returns to the app with a clear result");

rolesNow = baseRoles(); invitesNow = []; createdRoles.length = 0; createdInvites.length = 0; puts.length = 0;
const setup = (b = {}) => call("/api/discord/setup", { method: "POST", headers: H, body: JSON.stringify(b) }).then(async (x) => ({ status: x.status, data: await x.json() }));
let sr = await setup({ sources: ["youtube", "twitch"] });
ok(sr.status === 200 && sr.data.sources.length === 2 && sr.data.sources[0].invite.startsWith("https://discord.gg/NEW"), "one click returns an invite link for each platform");
ok(createdRoles.join() === "YouTube Viewer,Twitch Viewer" && sr.data.sources.every((x) => x.roleCreated), "the roles were created by the bot");
ok(createdInvites.join() === "C1,C1", "invites were made in the server's welcome channel");
r = await call("/api/config", { headers: H }); const cfgNow = (await r.json()).config;
ok(cfgNow.inviteRules.length === 2 && cfgNow.inviteRules[0].label === "YouTube", "invite rules are saved automatically");
sr = await setup({ sources: ["youtube", "twitch"] }); ok(sr.data.sources.every((x) => x.reused && !x.roleCreated) && createdInvites.length === 2, "running it again reuses the same invites (no duplicates)");
sr = await setup({ sources: ["kick"] }); r = await call("/api/config", { headers: H });
ok(sr.status === 200 && (await r.json()).config.inviteRules.length === 3, "adding another platform keeps the others");
rolesNow = baseRoles(); rolesNow.push({ id: "555555", name: "Kick Viewer" }); invitesNow = []; createdRoles.length = 0;
sr = await setup({ sources: ["kick"] }); ok(sr.data.sources[0].roleId === "555555" && !sr.data.sources[0].roleCreated, "an existing role with the same name is reused");
systemChannel = ""; createdInvites.length = 0; invitesNow = [];
sr = await setup({ sources: ["youtube"] }); ok(sr.status === 200 && createdInvites[0] === "C2" && sr.data.channelName === "general", "no welcome channel -> the first text channel is used");
roleCreateStatus = 403; rolesNow = baseRoles(); invitesNow = [];
sr = await setup({ sources: ["twitch"] }); ok(sr.status === 403 && sr.data.error.includes("Manage Roles"), "missing permission -> plain instruction");
roleCreateStatus = 200; systemChannel = "C1";
sr = await setup({ sources: ["myspace"] }); ok(sr.status === 400, "unknown platform rejected");
console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
