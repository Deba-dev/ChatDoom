// Offline test of Kick chat through Kick's official webhooks: signature checks, duplicates, subscribe/unsubscribe, the app's poll.
// A real SQLite database, a fake KV and a fake Kick that signs like the real one (RSA SHA-256). Run: node test-kick.mjs
import worker from "./src/index.js";
import { fakeEnv } from "./test-studio.mjs";

let fails = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };

const env = Object.assign(fakeEnv(), {
  DISCORD_CLIENT_ID: "d", DISCORD_CLIENT_SECRET: "d", DISCORD_BOT_TOKEN: "d",
  KICK_CLIENT_ID: "KICK_CLIENT_ID", KICK_CLIENT_SECRET: "KICK_CLIENT_SECRET",
  PLATFORM_TOKEN_ENCRYPTION_KEY: Buffer.alloc(32, 7).toString("base64"),
});

// Kick's signing key, and a second one for a forged sender
const keyPair = () => crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
const kickKeys = await keyPair(), forgedKeys = await keyPair();
const spki = Buffer.from(await crypto.subtle.exportKey("spki", kickKeys.publicKey)).toString("base64");
const PEM = "-----BEGIN PUBLIC KEY-----\n" + spki.match(/.{1,64}/g).join("\n") + "\n-----END PUBLIC KEY-----\n";

// Fake Kick
const kick = { subs: [], calls: [], subscribeStatus: 200, nextSub: 1, keyFetches: 0 };
globalThis.fetch = async (u, o = {}) => {
  const url = new URL(String(u)), method = o.method || "GET";
  const reply = (data, status = 200) => new Response(data === null ? null : JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
  kick.calls.push({ method, path: url.pathname, query: url.search, body: o.body ? String(o.body) : "" });
  if (url.hostname === "id.kick.com" && url.pathname === "/oauth/token") return reply({ access_token: "KICK_AT", refresh_token: "KICK_RT", expires_in: 3600 });
  if (url.pathname === "/public/v1/users") return reply({ data: [{ user_id: 4242, name: "Test Kick" }] });
  if (url.pathname === "/public/v1/channels") return reply({ data: [{ slug: "test-kick", broadcaster_user_id: 4242 }] });
  if (url.pathname === "/public/v1/public-key") { kick.keyFetches++; return reply({ data: { public_key: PEM }, message: "OK" }); }
  if (url.pathname === "/public/v1/events/subscriptions") {
    if (kick.subscribeStatus !== 200) return reply({ message: "Forbidden" }, kick.subscribeStatus);
    if (method === "GET") return reply({ data: kick.subs });
    if (method === "POST") {
      const body = JSON.parse(o.body);
      const made = body.events.map((e) => ({ name: e.name, version: e.version, subscription_id: "SUB" + kick.nextSub, error: "" }));
      for (const e of body.events) kick.subs.push({ id: "SUB" + kick.nextSub++, event: e.name, version: e.version, broadcaster_user_id: 4242, method: "webhook" });
      return reply({ data: made, message: "OK" });
    }
    if (method === "DELETE") {
      const ids = url.searchParams.getAll("id");
      kick.subs = kick.subs.filter((s) => !ids.includes(s.id));
      return reply(null, 204);
    }
  }
  return reply({ message: "unexpected " + url.pathname }, 404);
};

const BASE = "https://cloud.example";
const call = async (method, path, { headers = {}, body, raw } = {}) => {
  const res = await worker.fetch(new Request(BASE + path, { method, headers, body: raw ?? (body === undefined ? undefined : JSON.stringify(body)) }), env);
  const type = res.headers.get("content-type") || "";
  return { status: res.status, data: type.includes("json") ? await res.json() : await res.text(), location: res.headers.get("location") };
};

// sign in to Kick the normal way to get an app session
let r = await call("GET", "/platform-auth/start?" + new URLSearchParams({ platform: "kick", return: "http://127.0.0.1:5599/done" }));
ok(new URL(r.data.authorizeUrl).searchParams.get("scope").split(" ").includes("events:subscribe"), "Kick sign-in asks for events:subscribe (needed for chat webhooks)");
const state = new URL(r.data.authorizeUrl).searchParams.get("state");
r = await call("GET", "/platform-auth/kick/callback?" + new URLSearchParams({ state, code: "c" }));
const ticket = new URL(r.location).searchParams.get("ticket");
const session = (await call("POST", "/platform-auth/redeem", { body: { ticket } })).data.session;
const auth = { Authorization: "Bearer " + session, "content-type": "application/json" };

let seqId = 0;
const signWith = async (keys, id, ts, body) =>
  Buffer.from(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", keys.privateKey, new TextEncoder().encode(`${id}.${ts}.${body}`))).toString("base64");
const event = (over = {}) => JSON.stringify({
  message_id: over.message_id || "msg-" + (++seqId), broadcaster: { user_id: over.broadcaster ?? 4242, channel_slug: "test-kick" },
  sender: { user_id: 777, username: over.name || "KickFan", identity: { badges: over.badges || [] } },
  content: over.content || "hello [emote:37226:KEKW]", created_at: new Date().toISOString(),
});
const deliver = async ({ body = event(), id = "DLV-" + (++seqId), ts = new Date().toISOString(), type = "chat.message.sent", keys = kickKeys, signature } = {}) =>
  call("POST", "/kick/webhook", { raw: body, headers: {
    "Kick-Event-Message-Id": id, "Kick-Event-Message-Timestamp": ts, "Kick-Event-Type": type, "Kick-Event-Version": "1",
    "Kick-Event-Subscription-Id": "SUB1", "Kick-Event-Signature": signature ?? await signWith(keys, id, ts, body),
  } });
const chat = async (after = 0, headers = auth) => call("GET", "/kick/chat?after=" + after, { headers });

// ---- before the app subscribes
r = await deliver();
ok(r.status === 200 && r.data.ignored === "app closed", "a genuine message for a channel whose app is closed is acknowledged (200) but not stored");
r = await chat();
ok(r.status === 409 && r.data.resubscribe, "reading before subscribing asks the app to connect again");

// ---- subscribe
r = await call("POST", "/kick/subscribe", { headers: auth, body: { channel: "someone-else" } });
ok(r.data.notMine && r.data.channel === "test-kick" && !kick.subs.length, "another streamer's channel is not subscribed (the app keeps Pusher for it)");
r = await call("POST", "/kick/subscribe", { headers: auth, body: { channel: "Test-Kick" } });
const post = kick.calls.find((c) => c.method === "POST" && c.path === "/public/v1/events/subscriptions");
ok(r.status === 200 && r.data.ok && r.data.latest === 0 && JSON.parse(post.body).events[0].name === "chat.message.sent" && JSON.parse(post.body).method === "webhook",
   "subscribing asks Kick for chat.message.sent by webhook");
r = await call("POST", "/kick/subscribe", { headers: auth, body: { channel: "test-kick" } });
ok(r.data.ok && kick.subs.length === 1, "connecting again renews it without making a second subscription");

// ---- webhook deliveries
const first = await deliver({ body: event({ name: "ModUser", badges: [{ type: "moderator", text: "Moderator" }], content: "hi chat [emote:37226:KEKW]" }), id: "DLV-A" });
r = await chat();
ok(first.status === 200 && r.data.messages.length === 1 && r.data.messages[0].name === "ModUser" && r.data.messages[0].mod
   && r.data.messages[0].text === "hi chat [emote:37226:KEKW]" && r.data.messages[0].uid === "777" && r.data.latest === r.data.messages[0].seq,
   "signature OK: the message is stored and the app reads it with name, text, viewer id and the mod badge");
const latest = r.data.latest;
r = await deliver({ body: event({ message_id: "same" }), id: "DLV-A" });
ok(r.status === 200 && (await chat()).data.messages.length === 1, "duplicate message id (Kick delivers at least once): stored only once");
r = await deliver({ keys: forgedKeys });
ok(r.status === 401 && (await chat()).data.messages.length === 1, "bad signature: refused (401) and not stored");
const tampered = event({ content: "real" }), tid = "DLV-T", tts = new Date().toISOString();
r = await deliver({ body: tampered.replace("real", "fake"), id: tid, ts: tts, signature: await signWith(kickKeys, tid, tts, tampered) });
ok(r.status === 401, "a body changed after signing is refused");
r = await call("POST", "/kick/webhook", { raw: event(), headers: { "Kick-Event-Type": "chat.message.sent" } });
ok(r.status === 400, "a request without Kick's headers is refused");
ok(kick.keyFetches === 1, "Kick's public key is fetched once and cached (a burst of forged requests does not refetch it)");
r = await deliver({ ts: new Date(Date.now() - 30 * 60 * 1000).toISOString() });
ok(r.status === 200 && r.data.ignored === "late" && (await chat()).data.messages.length === 1, "a delivery retried half an hour late is acknowledged but not read aloud");
r = await deliver({ type: "channel.followed" });
ok(r.status === 200 && r.data.ignored === "event", "other Kick events are acknowledged and ignored");
await deliver({ body: event({ content: "second message" }) });
r = await chat(latest);
ok(r.data.messages.length === 1 && r.data.messages[0].text === "second message", "the app only gets messages after the last one it read");

// ---- sessions and sign-in problems
r = await chat(0, { Authorization: "Bearer " + "0".repeat(64) });
ok(r.status === 401, "an unknown session cannot read anyone's Kick chat");
kick.subscribeStatus = 403;
r = await call("POST", "/kick/subscribe", { headers: auth, body: { channel: "test-kick" } });
ok(r.status === 403 && r.data.needsLogin, "signed in before events:subscribe was asked for: told to sign in again");
kick.subscribeStatus = 200;

// ---- disconnect
r = await call("DELETE", "/kick/subscribe", { headers: auth });
const del = kick.calls.find((c) => c.method === "DELETE");
ok(r.data.ok && r.data.removed === 1 && del.query === "?id=SUB1" && !kick.subs.length, "disconnect removes the Kick subscription by its id");
r = await deliver();
ok(r.status === 200 && r.data.ignored === "app closed", "after disconnect, late messages are acknowledged but not stored");

console.log(fails ? `\n${fails} FAILED` : "\nall passed");
process.exit(fails ? 1 : 0);
