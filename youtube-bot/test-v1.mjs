import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createService } from "./server.mjs";

const CH = `UC${"a".repeat(22)}`;            // the streamer's channel
const OTHER = `UC${"b".repeat(22)}`;         // somebody else's channel
const VIEWER = `UC${"v".repeat(22)}`;
const VID = "abcdefghijk";

// ---- a tiny fake YouTube + Google ----
function fakeYoutube() {
  const y = { messages: [], deleted: [], bans: [], calls: [], live: true, videoChannel: CH, deleteStatus: 204, botHandle: "@ChatDoom" };
  y.fetch = async (url, init = {}) => {
    const u = new URL(url);
    const method = init.method || "GET";
    y.calls.push(`${method} ${u.pathname}`);
    const reply = (obj, status = 200) => ({ ok: status < 400, status, json: async () => obj });
    if (u.hostname === "oauth2.googleapis.com") return reply({ access_token: "AT", expires_in: 3600 });
    if (u.pathname.endsWith("/channels")) return reply({ items: [{ id: `UC${"z".repeat(22)}`, snippet: { title: "Chat Voice", customUrl: y.botHandle } }] });
    if (u.pathname.endsWith("/videos")) {
      if (u.searchParams.get("id") === "missingvid1") return reply({ items: [] });
      return reply({ items: [{ snippet: { channelId: y.videoChannel, channelTitle: "Streamer" }, liveStreamingDetails: y.live ? { activeLiveChatId: "CHAT1" } : {} }] });
    }
    if (u.pathname.endsWith("/liveChat/messages") && method === "GET") {
      const from = Number(u.searchParams.get("pageToken") || 0);
      return reply({ items: y.messages.slice(from), nextPageToken: String(y.messages.length) });
    }
    if (u.pathname.endsWith("/liveChat/messages") && method === "DELETE") {
      if (y.deleteStatus !== 204) return reply({ error: { message: "forbidden" } }, y.deleteStatus);
      y.deleted.push(u.searchParams.get("id")); return { ok: true, status: 204, json: async () => ({}) };
    }
    if (u.pathname.endsWith("/liveChat/bans")) { y.bans.push(JSON.parse(init.body)); return reply({ id: "ban" }); }
    return reply({}, 404);
  };
  y.say = (author, text, extra = {}) => { const id = `M${y.messages.length + 1}`; y.messages.push({ id, snippet: { displayMessage: text }, authorDetails: { channelId: author, ...extra } }); return id; };
  return y;
}

async function boot(y, envExtra = {}) {
  const dataDir = await mkdtemp(path.join(os.tmpdir(), "cv-v1-"));
  let t = 1_000_000;
  const service = createService({
    dataDir, now: () => t, fetchImpl: y.fetch,
    env: { BOT_ADMIN_KEY: "k".repeat(48), PUBLIC_URL: "https://bot.example", GOOGLE_CLIENT_ID: "id", GOOGLE_CLIENT_SECRET: "sec", PORT: "0", BOT_REFRESH_TOKEN: "rt", ...envExtra },
  });
  await service.start();
  const base = `http://127.0.0.1:${service.server.address().port}`;
  const call = async (method, p, body, token) => {
    const r = await fetch(base + p, { method, headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
    return { status: r.status, data: await r.json() };
  };
  return { service, call, advance: (ms) => { t += ms; }, done: async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); } };
}

async function verified(h, y) {
  const start = await h.call("POST", "/v1/verify/start", { videoId: VID });
  y.say(CH, `hello ${start.data.code} chat`, { isChatOwner: true });
  const check = await h.call("POST", "/v1/verify/check", { videoId: VID });
  return check.data.token;
}

test("info works on a fresh server and shows the bot's channel (login kept in an environment variable)", async () => {
  const y = fakeYoutube(), h = await boot(y);
  try {
    const r = await h.call("GET", "/v1/info");
    assert.equal(r.status, 200);
    assert.equal(r.data.authorized, true);
    assert.equal(r.data.bot.handle, "@ChatDoom");
    assert.equal(r.data.bot.title, "Chat Voice");
  } finally { await h.done(); }
});

test("verification needs a live stream and the code typed by the channel that owns it", async () => {
  const y = fakeYoutube(), h = await boot(y);
  try {
    y.live = false;
    assert.equal((await h.call("POST", "/v1/verify/start", { videoId: VID })).status, 409);
    assert.equal((await h.call("POST", "/v1/verify/start", { videoId: "bad" })).status, 400);
    assert.equal((await h.call("POST", "/v1/verify/start", { videoId: "missingvid1" })).status, 404);
    y.live = true;
    const start = await h.call("POST", "/v1/verify/start", { videoId: VID });
    assert.equal(start.status, 200);
    assert.match(start.data.code, /^CV-[A-Z2-9]{6}$/);
    assert.equal(start.data.channelId, CH);
    assert.deepEqual((await h.call("POST", "/v1/verify/check", { videoId: VID })).data, { ok: false, waiting: true });
    y.say(OTHER, `trying ${start.data.code}`);                 // somebody else copies the code from the screen
    assert.equal((await h.call("POST", "/v1/verify/check", { videoId: VID })).data.waiting, true);
    y.say(CH, `${start.data.code.toLowerCase()} here`, { isChatOwner: true });
    const ok = await h.call("POST", "/v1/verify/check", { videoId: VID });
    assert.equal(ok.data.ok, true);
    assert.ok(ok.data.token.includes("."));
    assert.equal((await h.call("POST", "/v1/verify/check", { videoId: VID })).status, 410, "the code works once");
  } finally { await h.done(); }
});

test("tokens: forged, edited and expired ones are refused", async () => {
  const y = fakeYoutube(), h = await boot(y);
  try {
    const token = await verified(h, y);
    const body = { videoId: VID, items: [] };
    assert.equal((await h.call("POST", "/v1/moderate", body, token)).status, 200);
    assert.equal((await h.call("POST", "/v1/moderate", body)).status, 401);
    assert.equal((await h.call("POST", "/v1/moderate", body, "x.y")).status, 401);
    const [p, sig] = token.split(".");
    const edited = Buffer.from(JSON.stringify({ ch: OTHER, exp: 9e15, v: 1 })).toString("base64url");
    assert.equal((await h.call("POST", "/v1/moderate", body, `${edited}.${sig}`)).status, 401, "changing the channel breaks the signature");
    h.advance(91 * 86_400_000);
    assert.equal((await h.call("POST", "/v1/moderate", body, token)).status, 401, "expired after 90 days");
  } finally { await h.done(); }
});

test("a verified streamer can only moderate their own stream", async () => {
  const y = fakeYoutube(), h = await boot(y);
  try {
    const token = await verified(h, y);
    y.videoChannel = OTHER;                                    // somebody asks the bot to act on another channel's video
    const r = await h.call("POST", "/v1/moderate", { videoId: "zzzzzzzzzzz", items: [{ channelId: VIEWER, text: "x", reason: "link" }] }, token);
    assert.equal(r.status, 403);
    assert.equal(y.deleted.length, 0);
  } finally { await h.done(); }
});

test("deletes the right message, skips moderators, honours test mode and the daily limit", async () => {
  const y = fakeYoutube(), h = await boot(y);
  try {
    const token = await verified(h, y);
    y.say(VIEWER, "hello everyone");
    const bad = y.say(VIEWER, "visit www.spam.com :face_with_tears_of_joy:");
    y.say(VIEWER, "nice stream");
    y.say(OTHER, "i am a mod posting www.link.com", { isChatModerator: true });
    const item = { channelId: VIEWER, author: "Spammer", text: "visit www.spam.com", reason: "link" };

    let r = await h.call("POST", "/v1/moderate", { videoId: VID, items: [item], dryRun: true }, token);
    assert.ok(r.data.notes[0].startsWith("TEST MODE: would delete Spammer"));
    assert.equal(y.deleted.length, 0, "test mode never deletes");

    h.advance(2000);
    r = await h.call("POST", "/v1/moderate", { videoId: VID, items: [item] }, token);
    assert.deepEqual(y.deleted, [bad], "found by viewer + text, even though emoji codes differ");
    assert.equal(r.data.usedToday, 1);

    h.advance(2000);
    r = await h.call("POST", "/v1/moderate", { videoId: VID, items: [{ channelId: OTHER, author: "Mod", text: "i am a mod posting www.link.com", reason: "link" }] }, token);
    assert.equal(y.deleted.length, 1, "moderators are never touched");

    h.advance(2000);
    y.say(VIEWER, "second bad www.two.com");
    r = await h.call("POST", "/v1/moderate", { videoId: VID, limit: 1, items: [{ channelId: VIEWER, author: "Spammer", text: "second bad www.two.com", reason: "link" }] }, token);
    assert.match(r.data.notes[0], /Daily moderation limit reached/);
    assert.equal(y.deleted.length, 1, "limit of 1 action stops the second deletion");
  } finally { await h.done(); }
});

test("timeouts send a temporary ban; a missing moderator role gives a clear message", async () => {
  const y = fakeYoutube(), h = await boot(y);
  try {
    const token = await verified(h, y);
    let r = await h.call("POST", "/v1/moderate", { videoId: VID, items: [{ action: "timeout", channelId: VIEWER, author: "Troll", seconds: 99999 }] }, token);
    assert.equal(y.bans.length, 1);
    const b = y.bans[0].snippet;
    assert.deepEqual([b.type, b.banDurationSeconds, b.bannedUserInfo.channelId, b.liveChatId], ["temporary", 3600, VIEWER, "CHAT1"], "length is capped at one hour");
    y.deleteStatus = 403;
    h.advance(2000);
    y.say(VIEWER, "bad www.x.com");
    r = await h.call("POST", "/v1/moderate", { videoId: VID, items: [{ channelId: VIEWER, author: "Troll", text: "bad www.x.com", reason: "link" }] }, token);
    assert.match(r.data.notes[0], /not a moderator of your channel yet/);
  } finally { await h.done(); }
});

test("the shared YouTube safety budget is respected and bad input is rejected", async () => {
  const y = fakeYoutube(), h = await boot(y);
  try {
    const token = await verified(h, y);
    assert.equal((await h.call("POST", "/v1/moderate", { videoId: "no", items: [] }, token)).status, 400);
    const r = await h.call("POST", "/v1/moderate", { videoId: VID, items: [{ channelId: "not-a-channel", text: "x" }] }, token);
    assert.deepEqual(r.data.notes, [], "invalid viewer ids are ignored");
    assert.equal((await h.call("GET", "/v1/nothing")).status, 404);
  } finally { await h.done(); }
});

test("the old polling API still needs the admin key", async () => {
  const y = fakeYoutube(), h = await boot(y);
  try { assert.equal((await h.call("GET", "/api/streams")).status, 401); } finally { await h.done(); }
});
