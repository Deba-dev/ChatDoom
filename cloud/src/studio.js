// Overlay Studio's online storage: saved designs (D1) and uploaded pictures and sounds (KV).
// Designing needs no account: creating a design without signing in returns a secret key, kept in the streamer's browser; only its hash is stored.
// Signing in with Google or Discord ties designs to that account instead, and uploading files needs it. We keep the name and account ID only, never the provider's tokens.
// Anyone with an overlay link can read that design, because OBS has to. Only its owner can change it.
const SITE_ORIGINS = new Set(["https://zunimilabs.online", "https://www.zunimilabs.online"]);
const MAX_DESIGN = 300 * 1024;
const MAX_FILE = 2 * 1024 * 1024;
const MAX_DESIGN_FILES = 40;
const MAX_DESIGN_BYTES = 20 * 1024 * 1024;
const MAX_ALL_BYTES = 900 * 1024 * 1024;     // stays under the free plan's KV storage
const MAX_USER_DESIGNS = 20;
const MAX_USER_FILES = 200;                  // deleting an account removes every file in one request, which has a limit
const MAX_USER_BYTES = 60 * 1024 * 1024;
const DAILY = { design: 10, upload: 40, save: 1500 };
const SESSION_MS = 90 * 86400000;
const NOT_OWNER = "Please sign in to change this overlay";

const PROVIDERS = {
  google: {
    label: "Google", clientId: "GOOGLE_OAUTH_CLIENT_ID", clientSecret: "GOOGLE_OAUTH_CLIENT_SECRET", scope: "openid profile",
    authorize: "https://accounts.google.com/o/oauth2/v2/auth", token: "https://oauth2.googleapis.com/token",
    profile: "https://openidconnect.googleapis.com/v1/userinfo", extra: { prompt: "select_account" },
    read: (u) => ({ id: u.sub, name: u.name }),
  },
  discord: {
    label: "Discord", clientId: "DISCORD_CLIENT_ID", clientSecret: "DISCORD_CLIENT_SECRET", scope: "identify",
    authorize: "https://discord.com/oauth2/authorize", token: "https://discord.com/api/v10/oauth2/token",
    profile: "https://discord.com/api/v10/users/@me", extra: {},
    read: (u) => ({ id: u.id, name: u.global_name || u.username }),
  },
};

let ready = null;
function tables(env) {
  if (!ready) {
    ready = env.DB.batch([
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_designs (id TEXT PRIMARY KEY, key_hash TEXT NOT NULL, data TEXT NOT NULL, rev INTEGER NOT NULL, updated INTEGER NOT NULL)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_files (id TEXT PRIMARY KEY, design_id TEXT NOT NULL, kind TEXT NOT NULL, type TEXT NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL, created INTEGER NOT NULL)"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS studio_files_design ON studio_files (design_id)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_usage (day TEXT NOT NULL, who TEXT NOT NULL, kind TEXT NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (day, who, kind))"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_users (id TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_id TEXT NOT NULL, name TEXT NOT NULL, blocked INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL, UNIQUE (provider, provider_id))"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires INTEGER NOT NULL)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_owners (design_id TEXT PRIMARY KEY, user_id TEXT NOT NULL)"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS studio_owners_user ON studio_owners (user_id)"),
    ]).catch((e) => { ready = null; throw e; });
  }
  return ready;
}

function allowed(request, env) {
  const origin = request.headers.get("origin") || "";
  return SITE_ORIGINS.has(origin) || (env.STUDIO_DEV_ORIGIN && origin === env.STUDIO_DEV_ORIGIN) ? origin : "";
}
function send(request, env, data, status = 200) {
  const origin = allowed(request, env);
  const headers = { "content-type": "application/json", "cache-control": "no-store", vary: "Origin" };
  if (origin) headers["access-control-allow-origin"] = origin;
  return new Response(JSON.stringify(data), { status, headers });
}
const hex = (bytes) => Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
const random = (n) => hex(crypto.getRandomValues(new Uint8Array(n)));
const sha = async (text) => hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
const today = () => new Date().toISOString().slice(0, 10);

// Counts an action. The visitor's address is only kept as a hash that changes every day.
async function spend(env, who, kind, limit) {
  const day = today(), key = await sha(who + ":" + day);
  await env.DB.prepare("DELETE FROM studio_usage WHERE day < ?").bind(day).run();
  const r = await env.DB.prepare("INSERT INTO studio_usage (day, who, kind, n) VALUES (?, ?, ?, 1) ON CONFLICT (day, who, kind) DO UPDATE SET n = n + 1 WHERE n < ?")
    .bind(day, key, kind, limit).run();
  return !!(r.meta && r.meta.changes === 1);
}
const visitor = (request) => request.headers.get("cf-connecting-ip") || "unknown";

function bearer(request) {
  const auth = request.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  return /^[0-9a-f]{64}$/.test(token) ? token : "";
}

async function currentUser(request, env) {
  const token = bearer(request);
  if (!token) return null;
  return env.DB.prepare("SELECT u.id, u.name, u.provider FROM studio_sessions s JOIN studio_users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires > ? AND u.blocked = 0")
    .bind(await sha(token), Date.now()).first();
}

// The bearer token is either the design's own secret key or the session of the account that owns it.
async function owner(request, env, id) {
  const token = bearer(request);
  if (!token || !/^[0-9a-f]{24}$/.test(id)) return null;
  const row = await env.DB.prepare("SELECT id, key_hash, rev FROM studio_designs WHERE id = ?").bind(id).first();
  if (!row) return null;
  if (row.key_hash === await sha(token)) return row;
  const user = await currentUser(request, env);
  if (!user) return null;
  const mine = await env.DB.prepare("SELECT 1 AS yes FROM studio_owners WHERE design_id = ? AND user_id = ?").bind(id, user.id).first();
  return mine ? row : null;
}

async function readDesign(request) {
  const text = await request.text();
  if (text.length > MAX_DESIGN) return { error: "This design is too large to save online", status: 413 };
  let body;
  try { body = JSON.parse(text); } catch (e) { return { error: "That is not a valid design", status: 400 }; }
  const design = body && body.design;
  if (!design || !Array.isArray(design.scenes) || !design.source) return { error: "That is not a valid design", status: 400 };
  return { data: JSON.stringify(design) };
}

// Files are checked by their real contents, never by their name. SVG and HTML are refused because they can run code.
function fileKind(b) {
  const at = (i, text) => [...text].every((c, n) => b[i + n] === c.charCodeAt(0));
  if (b[0] === 0x89 && at(1, "PNG")) return ["image", "image/png"];
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return ["image", "image/jpeg"];
  if (at(0, "GIF8")) return ["image", "image/gif"];
  if (at(0, "RIFF") && at(8, "WEBP")) return ["image", "image/webp"];
  if (at(0, "RIFF") && at(8, "WAVE")) return ["sound", "audio/wav"];
  if (at(0, "OggS")) return ["sound", "audio/ogg"];
  if (at(0, "ID3") || (b[0] === 0xff && (b[1] & 0xe0) === 0xe0)) return ["sound", "audio/mpeg"];
  return null;
}

async function upload(request, env, url) {
  const id = url.searchParams.get("design") || "";
  const user = await currentUser(request, env);
  if (!user) return send(request, env, { error: "Please sign in to upload files" }, 401);
  if (!await owner(request, env, id)) return send(request, env, { error: NOT_OWNER }, 401);
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (!bytes.length) return send(request, env, { error: "That file is empty" }, 400);
  if (bytes.length > MAX_FILE) return send(request, env, { error: "Files can be up to 2 MB" }, 413);
  const found = fileKind(bytes);
  if (!found) return send(request, env, { error: "Use a PNG, JPG, GIF or WebP picture, or an MP3, WAV or OGG sound" }, 415);
  const mine = await env.DB.prepare("SELECT COUNT(*) AS n, COALESCE(SUM(size), 0) AS bytes FROM studio_files WHERE design_id = ?").bind(id).first();
  if (mine.n >= MAX_DESIGN_FILES || mine.bytes + bytes.length > MAX_DESIGN_BYTES) return send(request, env, { error: "Your file library is full. Delete a file first." }, 413);
  const used = await env.DB.prepare("SELECT COUNT(*) AS n, COALESCE(SUM(f.size), 0) AS bytes FROM studio_files f JOIN studio_owners o ON o.design_id = f.design_id WHERE o.user_id = ?").bind(user.id).first();
  if (used.n >= MAX_USER_FILES || used.bytes + bytes.length > MAX_USER_BYTES) return send(request, env, { error: "Your account's file storage is full. Delete a file first." }, 413);
  const all = await env.DB.prepare("SELECT COALESCE(SUM(size), 0) AS bytes FROM studio_files").first();
  if (all.bytes + bytes.length > MAX_ALL_BYTES) return send(request, env, { error: "Uploads are full right now. Please use a picture link for now." }, 507);
  if (!await spend(env, "user:" + user.id, "upload", DAILY.upload)) return send(request, env, { error: "You have reached today's upload limit" }, 429);
  const file = random(16), name = String(url.searchParams.get("name") || "file").replace(/[\u0000-\u001f]/g, " ").slice(0, 80);
  await env.KV.put("studio-file:" + file, bytes, { metadata: { type: found[1] } });
  await env.DB.prepare("INSERT INTO studio_files (id, design_id, kind, type, name, size, created) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .bind(file, id, found[0], found[1], name, bytes.length, Date.now()).run();
  return send(request, env, { id: file, kind: found[0], name, size: bytes.length, url: url.origin + "/studio/files/" + file }, 201);
}

async function serveFile(file, env) {
  if (!/^[0-9a-f]{32}$/.test(file)) return new Response("Not found", { status: 404 });
  const { value, metadata } = await env.KV.getWithMetadata("studio-file:" + file, "arrayBuffer");
  if (!value || !metadata) return new Response("Not found", { status: 404 });
  return new Response(value, { headers: {
    "content-type": metadata.type, "x-content-type-options": "nosniff", "content-security-policy": "default-src 'none'; sandbox",
    "cache-control": "public, max-age=86400", "access-control-allow-origin": "*", "cross-origin-resource-policy": "cross-origin",
  } });
}

async function removeFile(request, env, file, designId) {
  if (!await owner(request, env, designId)) return send(request, env, { error: NOT_OWNER }, 401);
  const row = await env.DB.prepare("SELECT id FROM studio_files WHERE id = ? AND design_id = ?").bind(file, designId).first();
  if (!row) return send(request, env, { error: "File not found" }, 404);
  await env.KV.delete("studio-file:" + file);
  await env.DB.prepare("DELETE FROM studio_files WHERE id = ?").bind(file).run();
  return send(request, env, { ok: true });
}

// ----- signing in -----
const siteAllowed = (site, env) => SITE_ORIGINS.has(site) || (!!env.STUDIO_DEV_ORIGIN && site === env.STUDIO_DEV_ORIGIN);
const clean = (text, max) => String(text || "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
const backToSite = (site, part) => Response.redirect(site + "/studio/#" + part, 302);
const loginFailed = (site, why) => backToSite(site, "login-error=" + encodeURIComponent(clean(why, 140)));
const provider = (name) => (Object.hasOwn(PROVIDERS, name) ? PROVIDERS[name] : null);

// The browser makes up the nonce and keeps it. Only that browser can finish the sign-in, so nobody can send a link that signs a visitor in to the wrong account.
async function loginStart(request, env, url) {
  const name = url.searchParams.get("provider") || "", site = url.searchParams.get("site") || "", nonce = url.searchParams.get("nonce") || "";
  const p = provider(name);
  if (!siteAllowed(site, env)) return send(request, env, { error: "Not allowed" }, 403);
  if (!p || !/^[0-9a-f]{32}$/.test(nonce)) return loginFailed(site, "That sign-in link is not valid");
  if (!env[p.clientId] || !env[p.clientSecret]) return loginFailed(site, p.label + " sign-in is not set up yet");
  const state = random(24);
  await env.KV.put("studio-login:" + state, JSON.stringify({ name, site, nonce }), { expirationTtl: 600 });
  const to = new URL(p.authorize);
  to.search = new URLSearchParams({
    client_id: env[p.clientId], redirect_uri: url.origin + "/studio/auth/" + name + "/callback",
    response_type: "code", scope: p.scope, state, ...p.extra,
  });
  return Response.redirect(to.toString(), 302);
}

async function askProvider(p, response, stage) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(p.label + " " + stage + " failed (" + response.status + ")" + (data.error_description || data.error ? ": " + (data.error_description || data.error) : ""));
  return data;
}

async function loginCallback(env, url, name) {
  const p = provider(name), state = url.searchParams.get("state") || "";
  const raw = /^[0-9a-f]{48}$/.test(state) ? await env.KV.get("studio-login:" + state) : null;
  const saved = raw ? JSON.parse(raw) : null;
  if (!saved || saved.name !== name) return loginFailed("https://zunimilabs.online", "That sign-in expired. Please try again.");
  await env.KV.delete("studio-login:" + state);
  const code = url.searchParams.get("code");
  if (!code) return loginFailed(saved.site, "Sign-in was cancelled");

  let who;
  try {
    const token = await askProvider(p, await fetch(p.token, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: env[p.clientId], client_secret: env[p.clientSecret], code,
        grant_type: "authorization_code", redirect_uri: url.origin + "/studio/auth/" + name + "/callback",
      }),
    }), "sign-in");
    who = p.read(await askProvider(p, await fetch(p.profile, { headers: { authorization: "Bearer " + token.access_token } }), "account lookup"));
    if (!who.id) throw new Error(p.label + " did not say which account signed in");
  } catch (e) {
    console.error("studio login failed", e);
    return loginFailed(saved.site, e.message);
  }

  await env.DB.prepare("INSERT INTO studio_users (id, provider, provider_id, name, created) VALUES (?, ?, ?, ?, ?) ON CONFLICT (provider, provider_id) DO UPDATE SET name = excluded.name")
    .bind(random(12), name, String(who.id), clean(who.name, 80) || p.label + " user", Date.now()).run();
  const user = await env.DB.prepare("SELECT id, blocked FROM studio_users WHERE provider = ? AND provider_id = ?").bind(name, String(who.id)).first();
  if (user.blocked) return loginFailed(saved.site, "This account cannot use Overlay Studio");
  const ticket = random(24);
  await env.KV.put("studio-ticket:" + ticket, JSON.stringify({ userId: user.id, nonce: saved.nonce }), { expirationTtl: 120 });
  return backToSite(saved.site, "login=" + ticket);
}

async function redeemTicket(request, env) {
  const body = await request.json().catch(() => ({}));
  const ticket = String(body.ticket || ""), bad = () => send(request, env, { error: "That sign-in expired. Please try again." }, 400);
  if (!/^[0-9a-f]{48}$/.test(ticket)) return bad();
  const raw = await env.KV.get("studio-ticket:" + ticket);
  if (!raw) return bad();
  await env.KV.delete("studio-ticket:" + ticket);
  const saved = JSON.parse(raw);
  if (saved.nonce !== body.nonce) return bad();
  const user = await env.DB.prepare("SELECT name, provider FROM studio_users WHERE id = ? AND blocked = 0").bind(saved.userId).first();
  if (!user) return bad();
  const token = random(32), now = Date.now();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM studio_sessions WHERE expires < ?").bind(now),
    env.DB.prepare("INSERT INTO studio_sessions (token_hash, user_id, expires) VALUES (?, ?, ?)").bind(await sha(token), saved.userId, now + SESSION_MS),
  ]);
  return send(request, env, { token, user });
}

async function whoAmI(request, env) {
  const user = await currentUser(request, env);
  if (!user) return send(request, env, { error: "Please sign in again" }, 401);
  const rows = await env.DB.prepare("SELECT d.id, d.updated FROM studio_designs d JOIN studio_owners o ON o.design_id = d.id WHERE o.user_id = ? ORDER BY d.updated DESC").bind(user.id).all();
  return send(request, env, { user: { name: user.name, provider: user.provider }, designs: rows.results });
}

// Moves a design made before signing in to this account. The old key stops working, so a recovery code someone kept cannot change it later.
async function claimDesign(request, env, id) {
  const user = await currentUser(request, env);
  if (!user) return send(request, env, { error: "Please sign in again" }, 401);
  const body = await request.json().catch(() => ({}));
  const key = String(body.key || "");
  const row = /^[0-9a-f]{64}$/.test(key) && /^[0-9a-f]{24}$/.test(id) ? await env.DB.prepare("SELECT key_hash FROM studio_designs WHERE id = ?").bind(id).first() : null;
  if (!row || row.key_hash !== await sha(key)) return send(request, env, { error: "That overlay could not be added to your account" }, 403);
  const mine = await env.DB.prepare("SELECT COUNT(*) AS n FROM studio_owners WHERE user_id = ?").bind(user.id).first();
  if (mine.n >= MAX_USER_DESIGNS) return send(request, env, { error: "Your account has the most overlays it can hold. Delete one first." }, 409);
  await env.DB.batch([
    env.DB.prepare("INSERT INTO studio_owners (design_id, user_id) VALUES (?, ?)").bind(id, user.id),
    env.DB.prepare("UPDATE studio_designs SET key_hash = ? WHERE id = ?").bind(await sha(random(32)), id),
  ]);
  return send(request, env, { ok: true });
}

async function signOut(request, env) {
  const token = bearer(request);
  if (token) await env.DB.prepare("DELETE FROM studio_sessions WHERE token_hash = ?").bind(await sha(token)).run();
  return send(request, env, { ok: true });
}

async function deleteAccount(request, env) {
  const user = await currentUser(request, env);
  if (!user) return send(request, env, { error: "Please sign in again" }, 401);
  const files = await env.DB.prepare("SELECT f.id FROM studio_files f JOIN studio_owners o ON o.design_id = f.design_id WHERE o.user_id = ?").bind(user.id).all();
  await Promise.all(files.results.map((f) => env.KV.delete("studio-file:" + f.id)));
  const owned = "(SELECT design_id FROM studio_owners WHERE user_id = ?)";
  await env.DB.batch([
    env.DB.prepare("DELETE FROM studio_files WHERE design_id IN " + owned).bind(user.id),
    env.DB.prepare("DELETE FROM studio_designs WHERE id IN " + owned).bind(user.id),
    env.DB.prepare("DELETE FROM studio_owners WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM studio_sessions WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM studio_users WHERE id = ?").bind(user.id),
  ]);
  return send(request, env, { ok: true });
}

export async function handleStudio(request, env, url) {
  const parts = url.pathname.split("/").filter(Boolean), method = request.method;   // ["studio", "designs", id, ...]
  if (method === "OPTIONS") {
    const origin = allowed(request, env);
    const headers = { vary: "Origin" };
    if (origin) Object.assign(headers, { "access-control-allow-origin": origin, "access-control-allow-methods": "GET, POST, PUT, DELETE", "access-control-allow-headers": "authorization, content-type", "access-control-max-age": "86400" });
    return new Response(null, { status: 204, headers });
  }
  if (!env.DB || !env.KV) return send(request, env, { error: "Online saving is not available" }, 503);
  await tables(env);
  try {
    if (method === "GET" && parts[1] === "files" && parts[2]) return await serveFile(parts[2], env);
    if (method === "GET" && parts[1] === "auth" && parts[2] === "start") return await loginStart(request, env, url);
    if (method === "GET" && parts[1] === "auth" && provider(parts[2]) && parts[3] === "callback") return await loginCallback(env, url, parts[2]);

    if (method === "GET" && parts[1] === "designs" && parts[2] && !parts[3]) {
      if (!/^[0-9a-f]{24}$/.test(parts[2])) return send(request, env, { error: "Not found" }, 404);
      const row = await env.DB.prepare("SELECT data, rev FROM studio_designs WHERE id = ?").bind(parts[2]).first();
      if (!row) return send(request, env, { error: "Not found" }, 404);
      return new Response(JSON.stringify({ rev: row.rev, design: JSON.parse(row.data) }), { headers: { "content-type": "application/json", "cache-control": "no-store", "access-control-allow-origin": "*" } });
    }

    // Everything below changes something, so only our own pages may ask.
    if (!allowed(request, env)) return send(request, env, { error: "Not allowed" }, 403);

    if (parts[1] === "auth") {
      if (method === "POST" && parts[2] === "redeem") return await redeemTicket(request, env);
      if (method === "GET" && parts[2] === "me") return await whoAmI(request, env);
      if (method === "DELETE" && parts[2] === "session") return await signOut(request, env);
      if (method === "DELETE" && parts[2] === "account") return await deleteAccount(request, env);
      return send(request, env, { error: "Not found" }, 404);
    }

    if (method === "POST" && parts[1] === "designs" && !parts[2]) {
      const body = await readDesign(request);
      if (body.error) return send(request, env, { error: body.error }, body.status);
      const user = await currentUser(request, env);
      if (request.headers.has("authorization") && !user) return send(request, env, { error: "Please sign in again" }, 401);
      if (user) {
        const mine = await env.DB.prepare("SELECT COUNT(*) AS n FROM studio_owners WHERE user_id = ?").bind(user.id).first();
        if (mine.n >= MAX_USER_DESIGNS) return send(request, env, { error: "Your account has the most overlays it can hold. Delete one first." }, 409);
      }
      if (!await spend(env, user ? "user:" + user.id : visitor(request), "design", DAILY.design)) return send(request, env, { error: "You have reached today's limit for new overlays" }, 429);
      const id = random(12), key = random(32);
      const add = env.DB.prepare("INSERT INTO studio_designs (id, key_hash, data, rev, updated) VALUES (?, ?, ?, 1, ?)").bind(id, await sha(key), body.data, Date.now());
      if (!user) { await add.run(); return send(request, env, { id, key, rev: 1 }, 201); }
      await env.DB.batch([add, env.DB.prepare("INSERT INTO studio_owners (design_id, user_id) VALUES (?, ?)").bind(id, user.id)]);
      return send(request, env, { id, rev: 1 }, 201);
    }
    if (method === "POST" && parts[1] === "designs" && parts[2] && parts[3] === "claim") return await claimDesign(request, env, parts[2]);
    if (parts[1] === "designs" && parts[2] && parts[3] === "files" && method === "GET") {
      if (!await owner(request, env, parts[2])) return send(request, env, { error: NOT_OWNER }, 401);
      const rows = await env.DB.prepare("SELECT id, kind, name, size FROM studio_files WHERE design_id = ? ORDER BY created DESC").bind(parts[2]).all();
      return send(request, env, { files: rows.results.map((f) => ({ ...f, url: url.origin + "/studio/files/" + f.id })) });
    }
    if (parts[1] === "designs" && parts[2] && parts[3] === "files" && parts[4] && method === "DELETE") return await removeFile(request, env, parts[4], parts[2]);
    if (method === "PUT" && parts[1] === "designs" && parts[2]) {
      const row = await owner(request, env, parts[2]);
      if (!row) return send(request, env, { error: NOT_OWNER }, 401);
      const body = await readDesign(request);
      if (body.error) return send(request, env, { error: body.error }, body.status);
      if (!await spend(env, parts[2], "save", DAILY.save)) return send(request, env, { error: "Too many saves today" }, 429);
      await env.DB.prepare("UPDATE studio_designs SET data = ?, rev = rev + 1, updated = ? WHERE id = ?").bind(body.data, Date.now(), parts[2]).run();
      return send(request, env, { rev: row.rev + 1 });
    }
    if (method === "DELETE" && parts[1] === "designs" && parts[2]) {
      if (!await owner(request, env, parts[2])) return send(request, env, { error: NOT_OWNER }, 401);
      const files = await env.DB.prepare("SELECT id FROM studio_files WHERE design_id = ?").bind(parts[2]).all();
      await Promise.all(files.results.map((f) => env.KV.delete("studio-file:" + f.id)));
      await env.DB.batch([
        env.DB.prepare("DELETE FROM studio_files WHERE design_id = ?").bind(parts[2]),
        env.DB.prepare("DELETE FROM studio_designs WHERE id = ?").bind(parts[2]),
        env.DB.prepare("DELETE FROM studio_owners WHERE design_id = ?").bind(parts[2]),
      ]);
      return send(request, env, { ok: true });
    }
    if (method === "POST" && parts[1] === "files") return await upload(request, env, url);
    return send(request, env, { error: "Not found" }, 404);
  } catch (e) {
    console.error("studio failed", e);
    return send(request, env, { error: "Something went wrong. Please try again." }, 500);
  }
}
