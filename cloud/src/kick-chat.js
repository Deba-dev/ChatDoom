// Kick chat through Kick's official webhooks (docs.kick.com/events). Kick posts each chat message of a subscribed channel to
// /kick/webhook; it is checked against Kick's public key, kept for a few minutes, and the app reads it from /kick/chat.
// The app falls back to the old Pusher reader whenever this does not work.
//
// One-time setup in the Kick developer settings (kick.com/settings/developer): Edit the app, turn on "Enable Webhooks",
// and enter https://<this worker>/kick/webhook.
import { database, failed, hash, signedIn, tokenResponse } from "./platform-auth.js";

const KICK_API = "https://api.kick.com/public/v1/";
const EVENT = "chat.message.sent";
const KEEP_SECONDS = 600;          // messages older than this are deleted; the app reads every ~2 s
const LISTEN_SECONDS = 900;        // a channel's messages are stored while its app polled in the last 15 minutes
const MAX_AGE_SECONDS = 600;       // late deliveries (Kick retries) older than this are not worth reading aloud
const KEY_REFETCH_SECONDS = 600;   // a bad signature refetches Kick's key (it can rotate), at most this often

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
const clean = (value, max) => String(value ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
const now = () => Math.floor(Date.now() / 1000);

let tableReady = null;
let keyCache = null, keyFetchedAt = 0;

async function tables(env) {
  const d = await database(env);
  if (!tableReady) {
    tableReady = (async () => {
      await d.prepare("CREATE TABLE IF NOT EXISTS kick_chat (seq INTEGER PRIMARY KEY AUTOINCREMENT, broadcaster TEXT NOT NULL, message_id TEXT NOT NULL UNIQUE, ts INTEGER NOT NULL, data TEXT NOT NULL)").run();
      await d.prepare("CREATE INDEX IF NOT EXISTS kick_chat_by_channel ON kick_chat (broadcaster, seq)").run();
      await d.prepare("CREATE TABLE IF NOT EXISTS kick_listeners (broadcaster TEXT PRIMARY KEY, until INTEGER NOT NULL)").run();
    })().catch((error) => { tableReady = null; throw error; });
  }
  await tableReady;
  return d;
}

// ---------- the webhook ----------
function pemToDer(pem) {
  const body = String(pem).replace(/-----[^-]+-----/g, "").replace(/\s+/g, "");
  return Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
}

async function kickKey(env, fresh) {
  if (keyCache && !fresh) return keyCache;
  let pem = fresh ? null : await env.KV.get("kick-public-key");
  if (!pem) {
    keyFetchedAt = now();
    const response = await fetch(KICK_API + "public-key");
    const text = await response.text();
    if (!response.ok) throw new Error(`Kick public key lookup failed (${response.status})`);
    try { pem = JSON.parse(text).data.public_key; } catch (_) { pem = text; }   // the docs show both shapes
    if (!String(pem || "").includes("PUBLIC KEY")) throw new Error("Kick did not return its public key");
    await env.KV.put("kick-public-key", pem, { expirationTtl: 86400 });
  }
  keyCache = await crypto.subtle.importKey("spki", pemToDer(pem), { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  return keyCache;
}

async function signatureOk(env, id, timestamp, body, signature) {
  let sig;
  try { sig = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0)); } catch (_) { return false; }
  const data = new TextEncoder().encode(`${id}.${timestamp}.${body}`);
  if (await crypto.subtle.verify("RSASSA-PKCS1-v1_5", await kickKey(env, false), sig, data)) return true;
  if (now() - keyFetchedAt < KEY_REFETCH_SECONDS) return false;
  return crypto.subtle.verify("RSASSA-PKCS1-v1_5", await kickKey(env, true), sig, data);   // Kick may have rotated its key
}

// Always 200 for anything genuine, even when it is not stored: Kick drops the whole app's subscription after a day of failures.
async function webhook(request, env) {
  const id = request.headers.get("Kick-Event-Message-Id") || "";
  const timestamp = request.headers.get("Kick-Event-Message-Timestamp") || "";
  const signature = request.headers.get("Kick-Event-Signature") || "";
  const type = request.headers.get("Kick-Event-Type") || "";
  const body = await request.text();
  if (!id || !timestamp || !signature) return json({ error: "Kick webhook headers are missing" }, 400);
  if (body.length > 65536) return json({ error: "too large" }, 413);
  if (!(await signatureOk(env, id, timestamp, body, signature))) return json({ error: "bad signature" }, 401);
  if (type !== EVENT) return json({ ok: true, ignored: "event" });
  const sent = Date.parse(timestamp);
  if (Number.isFinite(sent) && Date.now() - sent > MAX_AGE_SECONDS * 1000) return json({ ok: true, ignored: "late" });
  let event;
  try { event = JSON.parse(body); } catch (_) { return json({ ok: true, ignored: "body" }); }
  const broadcaster = clean(event.broadcaster && event.broadcaster.user_id, 20);
  if (!/^\d+$/.test(broadcaster)) return json({ ok: true, ignored: "broadcaster" });
  const d = await tables(env);
  const listening = await d.prepare("SELECT until FROM kick_listeners WHERE broadcaster = ?").bind(broadcaster).first();
  if (!listening || listening.until < now()) return json({ ok: true, ignored: "app closed" });
  const sender = event.sender || {};
  const badges = ((sender.identity && sender.identity.badges) || []).map((b) => String(b && b.type || "").toLowerCase());
  const message = {
    id: clean(event.message_id || id, 80),
    name: clean(sender.username, 60),
    uid: clean(sender.user_id, 20),
    text: clean(event.content, 600),
    mod: badges.includes("moderator") || badges.includes("broadcaster"),
  };
  // Kick delivers at least once: the message id header is unique, so a repeat delivery is ignored
  await d.prepare("INSERT OR IGNORE INTO kick_chat (broadcaster, message_id, ts, data) VALUES (?, ?, ?, ?)")
    .bind(broadcaster, clean(id, 80), now(), JSON.stringify(message)).run();
  if (Math.random() < 0.02) await d.prepare("DELETE FROM kick_chat WHERE ts < ?").bind(now() - KEEP_SECONDS).run();
  return json({ ok: true });
}

// ---------- the app's side ----------
async function kickAccount(request, env) {
  const { account, failure } = await signedIn(request, env);
  if (failure) return { failure };
  if (account.platform !== "kick") return { failure: json({ error: "Sign in to Kick to read Kick chat this way" }, 400) };
  return { account };
}

async function latestSeq(d, broadcaster) {
  const row = await d.prepare("SELECT MAX(seq) AS m FROM kick_chat WHERE broadcaster = ?").bind(broadcaster).first();
  return (row && row.m) || 0;
}

// Called on every Connect (Kick drops failing subscriptions, so it is renewed each time). Only for the signed-in channel.
async function subscribe(request, env) {
  const { account, failure } = await kickAccount(request, env);
  if (failure) return failure;
  const body = await request.json().catch(() => ({}));
  const wanted = clean(body.channel, 60).toLowerCase();
  const headers = { Authorization: "Bearer " + account.accessToken, "content-type": "application/json" };
  try {
    const d = await tables(env);
    const channels = await tokenResponse(await fetch(KICK_API + "channels", { headers }), "Kick", "channel lookup");
    const channel = Array.isArray(channels.data) ? channels.data[0] : channels.data;
    const slug = clean(channel && channel.slug, 60).toLowerCase();
    if (!slug) return json({ error: "Kick did not return your channel" }, 502);
    if (wanted && wanted !== slug) return json({ ok: false, notMine: true, channel: slug, error: "This is not the signed-in Kick channel" });
    const broadcaster = String(account.provider_user_id);
    const existing = await tokenResponse(await fetch(KICK_API + "events/subscriptions", { headers }), "Kick", "subscription list");
    const has = (existing.data || []).some((s) => s.event === EVENT && String(s.broadcaster_user_id) === broadcaster);
    if (!has) {
      const made = await tokenResponse(await fetch(KICK_API + "events/subscriptions", {
        method: "POST", headers, body: JSON.stringify({ events: [{ name: EVENT, version: 1 }], method: "webhook" }),
      }), "Kick", "chat subscription");
      const result = (made.data || []).find((x) => x.name === EVENT);
      if (!result || result.error) return json({ error: clean("Kick refused the chat subscription" + (result && result.error ? ": " + result.error : ""), 180) }, 502);
    }
    await d.prepare("INSERT INTO kick_listeners (broadcaster, until) VALUES (?, ?) ON CONFLICT(broadcaster) DO UPDATE SET until = excluded.until")
      .bind(broadcaster, now() + LISTEN_SECONDS).run();
    return json({ ok: true, channel: slug, latest: await latestSeq(d, broadcaster) });
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      return json({ error: "Kick needs a new sign-in to allow chat events. Sign out and sign in to Kick again on the Connect page.", needsLogin: true }, 403);
    }
    return failed(error, "Could not subscribe to Kick chat");
  }
}

// Polled every ~2 s, so it is kept cheap: no token decryption, one lookup of the session and one of the messages.
async function chat(request, env, url) {
  const authorization = request.headers.get("Authorization") || "";
  const session = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!/^[0-9a-f]{64}$/.test(session)) return json({ error: "Sign in to Kick again" }, 401);
  const d = await tables(env);
  const row = await d.prepare("SELECT provider_user_id FROM platform_accounts WHERE session_hash = ? AND platform = 'kick'").bind(await hash(session)).first();
  if (!row) return json({ error: "Kick login expired or disconnected. Sign in again." }, 401);
  const broadcaster = String(row.provider_user_id);
  const listen = await d.prepare("SELECT until FROM kick_listeners WHERE broadcaster = ?").bind(broadcaster).first();
  if (!listen) return json({ error: "Not subscribed to Kick chat; connect again", resubscribe: true }, 409);
  if (listen.until - now() < LISTEN_SECONDS - 300) {           // keep storing while the app keeps reading (one write per 5 minutes)
    await d.prepare("UPDATE kick_listeners SET until = ? WHERE broadcaster = ?").bind(now() + LISTEN_SECONDS, broadcaster).run();
  }
  const after = parseInt(url.searchParams.get("after") || "0", 10) || 0;
  const rows = await d.prepare("SELECT seq, data FROM kick_chat WHERE broadcaster = ? AND seq > ? ORDER BY seq LIMIT 100").bind(broadcaster, after).all();
  const messages = (rows.results || []).map((r) => ({ seq: r.seq, ...JSON.parse(r.data) }));
  return json({ messages, latest: messages.length ? messages[messages.length - 1].seq : after });
}

// Disconnect: stop Kick sending this channel's chat here.
async function unsubscribe(request, env) {
  const { account, failure } = await kickAccount(request, env);
  if (failure) return failure;
  const headers = { Authorization: "Bearer " + account.accessToken };
  const broadcaster = String(account.provider_user_id);
  try {
    const d = await tables(env);
    await d.prepare("DELETE FROM kick_listeners WHERE broadcaster = ?").bind(broadcaster).run();
    const existing = await tokenResponse(await fetch(KICK_API + "events/subscriptions", { headers }), "Kick", "subscription list");
    const ids = (existing.data || []).filter((s) => s.event === EVENT && String(s.broadcaster_user_id) === broadcaster).map((s) => s.id);
    if (ids.length) {
      const query = new URLSearchParams(ids.map((x) => ["id", String(x)]));
      const response = await fetch(KICK_API + "events/subscriptions?" + query, { method: "DELETE", headers });
      if (!response.ok && response.status !== 204) await tokenResponse(response, "Kick", "unsubscribe");
    }
    return json({ ok: true, removed: ids.length });
  } catch (error) {
    return failed(error, "Could not unsubscribe from Kick chat");
  }
}

export async function handleKick(request, env, url) {
  const route = request.method + " " + url.pathname;
  if (route === "POST /kick/webhook") return webhook(request, env);
  if (route === "POST /kick/subscribe") return subscribe(request, env);
  if (route === "DELETE /kick/subscribe") return unsubscribe(request, env);
  if (route === "GET /kick/chat") return chat(request, env, url);
  return json({ error: "not found" }, 404);
}
