// Offline test of the YouTube moderator bot inside the worker, with a fake KV and a fake YouTube. Run: node test-youtube-bot.mjs
import worker from "./src/index.js";
import { makeToken, readToken } from "./src/youtube-bot.js";
import { createV1 } from "../youtube-bot/v1.mjs";

let fails = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };
const store = new Map(), ttls = new Map();
const KV = {
  async get(k) { return store.has(k) ? store.get(k) : null; },
  async put(k, v, o = {}) { store.set(k, v); ttls.set(k, o.expirationTtl); },
  async delete(k) { store.delete(k); },
};
const env = { KV, YT_BOT_KEY: "same-key-as-render-BOT_ADMIN_KEY-0123456789", YT_BOT_CLIENT_ID: "BOTCID", YT_BOT_CLIENT_SECRET: "BOTSEC",
              YT_BOT_REFRESH_TOKEN: "BOT_REFRESH", YT_BOT_TITLE: "CHATDOOM" };
const STREAMER = "UC" + "s".repeat(22), VIEWER = "UC" + "v".repeat(22), VIDEO = "LIVEVIDEO01";
const Y = { refreshes: 0, chat: [], deleted: [], bans: [], deleteStatus: 204, deleteReason: "" };

globalThis.fetch = async (url, init = {}) => {
  const u = new URL(url), m = init.method || "GET";
  const j = (o, s = 200) => new Response(JSON.stringify(o), { status: s });
  if (u.hostname === "oauth2.googleapis.com") {
    const body = new URLSearchParams(init.body);
    if (body.get("grant_type") === "refresh_token") {
      Y.refreshes++;
      return body.get("refresh_token") === "BOT_REFRESH" && body.get("client_id") === "BOTCID" ? j({ access_token: "ACC", expires_in: 3600 }) : j({ error: "invalid_grant" }, 400);
    }
    return j({ access_token: "ACC", refresh_token: "NEW_REFRESH" });
  }
  if ((init.headers || {}).authorization !== "Bearer ACC") return j({ error: { message: "bad auth" } }, 401);
  if (u.pathname.endsWith("/channels")) return j({ items: [{ id: "UCbot" + "b".repeat(19), snippet: { title: "CHATDOOM", customUrl: "@chatvoice-v1" } }] });
  if (u.pathname.endsWith("/videos")) {
    const id = u.searchParams.get("id");
    if (id === VIDEO) return j({ items: [{ snippet: { channelId: STREAMER, channelTitle: "Streamer" }, liveStreamingDetails: { activeLiveChatId: "CHAT1" } }] });
    if (id === "OTHERVIDEO1") return j({ items: [{ snippet: { channelId: "UC" + "o".repeat(22) }, liveStreamingDetails: { activeLiveChatId: "CHAT2" } }] });
    return j({ items: [] });
  }
  if (u.pathname.endsWith("/liveChat/messages") && m === "GET") return j({ items: Y.chat });
  if (u.pathname.endsWith("/liveChat/messages") && m === "DELETE") {
    if (Y.deleteStatus !== 204) return j({ error: { message: "nope", errors: [{ reason: Y.deleteReason }] } }, Y.deleteStatus);
    Y.deleted.push(u.searchParams.get("id")); return new Response(null, { status: 204 });
  }
  if (u.pathname.endsWith("/liveChat/messages") && m === "POST") {
    if (Y.postStatus) return j({ error: { message: "cannot post" } }, Y.postStatus);
    Y.posted.push(JSON.parse(init.body)); return j({ id: "POSTED" });
  }
  if (u.pathname.endsWith("/liveChat/bans")) { Y.bans.push(JSON.parse(init.body)); return j({}); }
  return j({ error: { message: "unexpected " + u.pathname } }, 404);
};

const call = async (path, init = {}, e = env) => {
  const r = await worker.fetch(new Request("https://cloud.example" + path, init), e);
  const text = await r.text();
  let data = null; try { data = JSON.parse(text); } catch { data = text; }
  return { status: r.status, data };
};
const post = (path, body, headers = {}) => call(path, { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body) });
const msg = (id, channelId, text, mod = false) => ({ id, snippet: { displayMessage: text }, authorDetails: { channelId, isChatModerator: mod, isChatOwner: false } });

// ---- tokens are the same as the Node bot's ----
const node = createV1({ env: { BOT_ADMIN_KEY: env.YT_BOT_KEY }, now: Date.now, api: null, accessToken: null, readBody: null, json: null, actions: null });
const oldToken = node._test.makeToken(STREAMER);
ok((await readToken(env, oldToken))?.ch === STREAMER, "a token made by the old Render bot is accepted (no streamer has to verify again)");
const newToken = await makeToken(env, STREAMER);
ok(node._test.readToken(newToken)?.ch === STREAMER, "tokens made on Cloudflare are valid for the Node bot too");
ok(await readToken(env, oldToken.slice(0, -2) + "xx") === null && await readToken({ ...env, YT_BOT_KEY: "different" }, oldToken) === null
   && await readToken(env, await makeToken(env, STREAMER, Date.now() - 91 * 86_400_000)) === null,
   "tampered, wrong-key and expired tokens are refused");

// ---- info ----
let r = await call("/v1/info");
ok(r.status === 200 && r.data.authorized === true && r.data.bot.title === "CHATDOOM" && r.data.host === "cloudflare", "/v1/info is answered at once and shows the bot is signed in");
ok(store.get("ytbot:access") === "ACC" && ttls.get("ytbot:access") >= 60, "the Google access token is cached in KV");
r = await call("/v1/info", {}, { KV });
ok(r.status === 200 && r.data.authorized === false && r.data.bot.title === "", "without the bot secrets /v1/info still answers (not set up)");
r = await post("/v1/verify/start", { videoId: VIDEO }, {}, { KV });
r = await call("/v1/verify/start", { method: "POST", body: "{}" }, { KV });
ok(r.status === 503 && r.data.error.includes("YT_BOT_KEY"), "without the bot secrets the API explains what is missing");

// ---- verify ----
r = await post("/v1/verify/start", { videoId: "bad" });
ok(r.status === 400, "a bad video ID is refused");
r = await post("/v1/verify/start", { videoId: VIDEO });
const code = r.data.code;
ok(r.status === 200 && /^CV-[A-Z2-9]{6}$/.test(code) && r.data.channelId === STREAMER && ttls.get("ytbot:code:" + VIDEO) === 900,
   "verify/start gives a code and remembers it in KV for 15 minutes (survives restarts)");
Y.chat = [msg("m0", VIEWER, code)];
r = await post("/v1/verify/check", { videoId: VIDEO });
ok(r.status === 200 && r.data.ok === false && r.data.waiting, "the code typed by someone else does not count");
Y.chat = [msg("m1", STREAMER, "my code " + code.toLowerCase())];
r = await post("/v1/verify/check", { videoId: VIDEO });
ok(r.status === 200 && r.data.ok && (await readToken(env, r.data.token))?.ch === STREAMER && !store.has("ytbot:code:" + VIDEO),
   "the streamer typing the code proves the channel and gets a token");
const token = r.data.token, H = { authorization: "Bearer " + token };
r = await post("/v1/verify/check", { videoId: VIDEO });
ok(r.status === 410, "a used code cannot be used again");

// ---- moderate ----
r = await post("/v1/moderate", { videoId: VIDEO, items: [] }, { authorization: "Bearer junk" });
ok(r.status === 401, "moderation without a valid token is refused");
r = await post("/v1/moderate", { videoId: "OTHERVIDEO1", items: [] }, H);
ok(r.status === 403, "a streamer cannot moderate someone else's stream");
Y.chat = [msg("a1", VIEWER, "buy followers www.spam.com 😀"), msg("a2", "UC" + "m".repeat(22), "mod link", true)];
r = await post("/v1/moderate", { videoId: VIDEO, dryRun: true, items: [{ channelId: VIEWER, author: "Spammer", text: "buy followers www.spam.com", reason: "link" }] }, H);
ok(r.status === 200 && r.data.notes[0].startsWith("TEST MODE") && Y.deleted.length === 0, "test mode only reports what it would do");
r = await post("/v1/moderate", { videoId: VIDEO, items: [{ channelId: VIEWER, author: "Spammer", text: "buy followers www.spam.com", reason: "link" },
                                                         { channelId: "UC" + "m".repeat(22), author: "Mod", text: "mod link", reason: "link" }] }, H);
ok(Y.deleted.join() === "a1" && r.data.usedToday === 1 && r.data.notes.length === 1, "the spam message is deleted (emoji ignored when matching) and moderators are never touched");
ok([...store.keys()].some((k) => k.startsWith("ytbot:act:" + STREAMER)), "the daily action count is kept in KV");
r = await post("/v1/moderate", { videoId: VIDEO, items: [{ channelId: VIEWER, author: "Spammer", action: "timeout", seconds: 99999 }] }, H);
ok(Y.bans[0].snippet.banDurationSeconds === 3600 && r.data.usedToday === 2, "timeouts are capped at one hour");
r = await post("/v1/moderate", { videoId: VIDEO, limit: 2, items: [{ channelId: VIEWER, author: "S", action: "timeout" }] }, H);
ok(r.data.notes[0].includes("Daily moderation limit") && Y.bans.length === 1, "the streamer's daily limit stops further actions");
Y.chat.push(msg("a3", VIEWER, "again spam"));
await new Promise((done) => setTimeout(done, 1600));       // the bot re-reads chat at most every 1.5 s
Y.deleteStatus = 403; Y.deleteReason = "quotaExceeded";
r = await post("/v1/moderate", { videoId: VIDEO, items: [{ channelId: VIEWER, author: "S", text: "again spam" }] }, H);
ok(r.data.notes[0].includes("budget for today"), "YouTube's quota error is explained as the daily budget, not as a missing moderator");
Y.deleteReason = "forbidden";
await new Promise((done) => setTimeout(done, 1600));
r = await post("/v1/moderate", { videoId: VIDEO, items: [{ channelId: VIEWER, author: "S", text: "again spam" }] }, H);
ok(r.data.notes[0].includes("not a moderator"), "a real permission error tells the streamer to add the bot as moderator");

// ---- telling viewers why ----
Y.posted = Y.posted || [];
ok(Y.posted.length === 0, "nothing is posted in chat unless the streamer turned reasons on");
const named = (id, text) => { const c = msg(id, VIEWER, text); return { ...c, authorDetails: { ...c.authorDetails, displayName: "@Spam Guy" } }; };
Y.deleteStatus = 204; Y.chat.push(named("a4", "told www.x.com"));
await new Promise((done) => setTimeout(done, 1600));
let before = r.data.usedToday;
r = await post("/v1/moderate", { videoId: VIDEO, explain: true, limit: 100, items: [{ channelId: VIEWER, author: "made up name", text: "told www.x.com", reason: "link" }] }, H);
ok(Y.posted[0]?.snippet.textMessageDetails.messageText === "@Spam Guy your message was removed because links are not allowed here."
   && Y.posted[0].snippet.liveChatId === "CHAT1", "the viewer is told why, under the name YouTube reports");
ok(r.data.results[0].outcome === "done" && r.data.results[0].told === true && r.data.usedToday === before + 2, "the reason counts toward the daily limit and the app gets the result");
Y.chat.push(named("a5", "more www.y.com"));
await new Promise((done) => setTimeout(done, 1600));
r = await post("/v1/moderate", { videoId: VIDEO, explain: true, limit: 100, items: [{ channelId: VIEWER, author: "S", text: "more www.y.com", reason: "made up reason" }] }, H);
ok(Y.deleted.includes("a5") && Y.posted.length === 1 && r.data.results[0].told === false, "a viewer is told at most once a minute, but the message is still removed");
Y.postStatus = 403;
r = await post("/v1/moderate", { videoId: VIDEO, explain: true, limit: 100, items: [{ channelId: "UC" + "z".repeat(22), author: "S", action: "timeout", seconds: 300 }] }, H);
ok(r.data.results[0].outcome === "done", "a timeout of someone not in the recent chat still works");
Y.postStatus = 0;

// ---- admin login ----
r = await call("/v1/admin");
ok(r.status === 200 && r.data.includes("All settings are present") && r.data.includes("/v1/oauth/callback"), "the admin page shows the setup state and the redirect URI");
r = await call("/v1/admin/authorize", { method: "POST", body: new URLSearchParams({ key: "wrong" }) });
ok(r.status === 403, "the bot login needs YT_BOT_KEY");
const authorize = await worker.fetch(new Request("https://cloud.example/v1/admin/authorize", { method: "POST", body: new URLSearchParams({ key: env.YT_BOT_KEY }) }), env);
const google = new URL(authorize.headers.get("location"));
ok(authorize.status === 302 && google.hostname === "accounts.google.com" && google.searchParams.get("access_type") === "offline"
   && google.searchParams.get("redirect_uri") === "https://cloud.example/v1/oauth/callback", "the right key sends you to Google for an offline login");
r = await call("/v1/oauth/callback?code=C&state=" + google.searchParams.get("state"));
ok(r.status === 200 && r.data.includes("NEW_REFRESH") && r.data.includes("wrangler secret put YT_BOT_REFRESH_TOKEN"), "after Google, the refresh token is shown once with the command to save it");
r = await call("/v1/oauth/callback?code=C&state=" + google.searchParams.get("state"));
ok(r.status === 400, "the login link cannot be replayed");

// ---- the bot talks in chat ----
Y.posted = []; delete Y.postStatus;
r = await post("/v1/say", { videoId: VIDEO, text: "Join the Discord!", limit: 150 }, { authorization: "Bearer junk" });
ok(r.status === 401 && !Y.posted.length, "only a verified channel can make the bot talk");
r = await post("/v1/say", { videoId: "OTHERVIDEO1", text: "Hi", limit: 150 }, H);
ok(r.status === 403 && !Y.posted.length, "the bot never talks in someone else's stream");
r = await post("/v1/say", { videoId: VIDEO, text: "   ", limit: 150 }, H);
ok(r.status === 400 && !Y.posted.length, "an empty message is refused");
r = await post("/v1/say", { videoId: VIDEO, text: "Join the\nDiscord! " + "x".repeat(300), limit: 150 }, H);
const said = Y.posted[0]?.snippet?.textMessageDetails?.messageText || "";
ok(r.status === 200 && said.startsWith("Join the Discord! ") && said.length === 200, "a chat line is cleaned, shortened to YouTube's limit and posted");
const usedBefore = r.data.usedToday;
r = await post("/v1/say", { videoId: VIDEO, text: "Over the limit", limit: usedBefore }, H);
ok(r.status === 429 && Y.posted.length === 1, "the bot stops at the channel's daily limit");

console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
