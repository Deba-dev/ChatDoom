// Overlay Studio's online storage: saved designs (D1) and uploaded pictures and sounds (KV).
// There are no accounts. Creating a design returns a secret key, kept in the streamer's browser; only its hash is stored.
// Anyone with an overlay link can read that design, because OBS has to. Only the key can change it.
const SITE_ORIGINS = new Set(["https://zunimilabs.online", "https://www.zunimilabs.online"]);
const MAX_DESIGN = 300 * 1024;
const MAX_FILE = 2 * 1024 * 1024;
const MAX_DESIGN_FILES = 40;
const MAX_DESIGN_BYTES = 20 * 1024 * 1024;
const MAX_ALL_BYTES = 900 * 1024 * 1024;     // stays under the free plan's KV storage
const DAILY = { design: 10, upload: 40, save: 1500 };

let ready = null;
function tables(env) {
  if (!ready) {
    ready = env.DB.batch([
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_designs (id TEXT PRIMARY KEY, key_hash TEXT NOT NULL, data TEXT NOT NULL, rev INTEGER NOT NULL, updated INTEGER NOT NULL)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_files (id TEXT PRIMARY KEY, design_id TEXT NOT NULL, kind TEXT NOT NULL, type TEXT NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL, created INTEGER NOT NULL)"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS studio_files_design ON studio_files (design_id)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS studio_usage (day TEXT NOT NULL, who TEXT NOT NULL, kind TEXT NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (day, who, kind))"),
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

async function owner(request, env, id) {
  const auth = request.headers.get("authorization") || "";
  const key = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!/^[0-9a-f]{64}$/.test(key) || !/^[0-9a-f]{24}$/.test(id)) return null;
  const row = await env.DB.prepare("SELECT id, key_hash, rev FROM studio_designs WHERE id = ?").bind(id).first();
  return row && row.key_hash === await sha(key) ? row : null;
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
  if (!await owner(request, env, id)) return send(request, env, { error: "Sign-in key not accepted" }, 401);
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (!bytes.length) return send(request, env, { error: "That file is empty" }, 400);
  if (bytes.length > MAX_FILE) return send(request, env, { error: "Files can be up to 2 MB" }, 413);
  const found = fileKind(bytes);
  if (!found) return send(request, env, { error: "Use a PNG, JPG, GIF or WebP picture, or an MP3, WAV or OGG sound" }, 415);
  const mine = await env.DB.prepare("SELECT COUNT(*) AS n, COALESCE(SUM(size), 0) AS bytes FROM studio_files WHERE design_id = ?").bind(id).first();
  if (mine.n >= MAX_DESIGN_FILES || mine.bytes + bytes.length > MAX_DESIGN_BYTES) return send(request, env, { error: "Your file library is full. Delete a file first." }, 413);
  const all = await env.DB.prepare("SELECT COALESCE(SUM(size), 0) AS bytes FROM studio_files").first();
  if (all.bytes + bytes.length > MAX_ALL_BYTES) return send(request, env, { error: "Uploads are full right now. Please use a picture link for now." }, 507);
  if (!await spend(env, visitor(request), "upload", DAILY.upload)) return send(request, env, { error: "You have reached today's upload limit" }, 429);
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
  if (!await owner(request, env, designId)) return send(request, env, { error: "Sign-in key not accepted" }, 401);
  const row = await env.DB.prepare("SELECT id FROM studio_files WHERE id = ? AND design_id = ?").bind(file, designId).first();
  if (!row) return send(request, env, { error: "File not found" }, 404);
  await env.KV.delete("studio-file:" + file);
  await env.DB.prepare("DELETE FROM studio_files WHERE id = ?").bind(file).run();
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

    if (method === "GET" && parts[1] === "designs" && parts[2] && !parts[3]) {
      if (!/^[0-9a-f]{24}$/.test(parts[2])) return send(request, env, { error: "Not found" }, 404);
      const row = await env.DB.prepare("SELECT data, rev FROM studio_designs WHERE id = ?").bind(parts[2]).first();
      if (!row) return send(request, env, { error: "Not found" }, 404);
      return new Response(JSON.stringify({ rev: row.rev, design: JSON.parse(row.data) }), { headers: { "content-type": "application/json", "cache-control": "no-store", "access-control-allow-origin": "*" } });
    }

    // Everything below changes something, so only our own pages may ask.
    if (!allowed(request, env)) return send(request, env, { error: "Not allowed" }, 403);

    if (method === "POST" && parts[1] === "designs" && !parts[2]) {
      const body = await readDesign(request);
      if (body.error) return send(request, env, { error: body.error }, body.status);
      if (!await spend(env, visitor(request), "design", DAILY.design)) return send(request, env, { error: "You have reached today's limit for new overlays" }, 429);
      const id = random(12), key = random(32);
      await env.DB.prepare("INSERT INTO studio_designs (id, key_hash, data, rev, updated) VALUES (?, ?, ?, 1, ?)").bind(id, await sha(key), body.data, Date.now()).run();
      return send(request, env, { id, key, rev: 1 }, 201);
    }
    if (parts[1] === "designs" && parts[2] && parts[3] === "files" && method === "GET") {
      if (!await owner(request, env, parts[2])) return send(request, env, { error: "Sign-in key not accepted" }, 401);
      const rows = await env.DB.prepare("SELECT id, kind, name, size FROM studio_files WHERE design_id = ? ORDER BY created DESC").bind(parts[2]).all();
      return send(request, env, { files: rows.results.map((f) => ({ ...f, url: url.origin + "/studio/files/" + f.id })) });
    }
    if (parts[1] === "designs" && parts[2] && parts[3] === "files" && parts[4] && method === "DELETE") return await removeFile(request, env, parts[4], parts[2]);
    if (method === "PUT" && parts[1] === "designs" && parts[2]) {
      const row = await owner(request, env, parts[2]);
      if (!row) return send(request, env, { error: "Sign-in key not accepted" }, 401);
      const body = await readDesign(request);
      if (body.error) return send(request, env, { error: body.error }, body.status);
      if (!await spend(env, parts[2], "save", DAILY.save)) return send(request, env, { error: "Too many saves today" }, 429);
      await env.DB.prepare("UPDATE studio_designs SET data = ?, rev = rev + 1, updated = ? WHERE id = ?").bind(body.data, Date.now(), parts[2]).run();
      return send(request, env, { rev: row.rev + 1 });
    }
    if (method === "DELETE" && parts[1] === "designs" && parts[2]) {
      if (!await owner(request, env, parts[2])) return send(request, env, { error: "Sign-in key not accepted" }, 401);
      const files = await env.DB.prepare("SELECT id FROM studio_files WHERE design_id = ?").bind(parts[2]).all();
      await Promise.all(files.results.map((f) => env.KV.delete("studio-file:" + f.id)));
      await env.DB.batch([env.DB.prepare("DELETE FROM studio_files WHERE design_id = ?").bind(parts[2]), env.DB.prepare("DELETE FROM studio_designs WHERE id = ?").bind(parts[2])]);
      return send(request, env, { ok: true });
    }
    if (method === "POST" && parts[1] === "files") return await upload(request, env, url);
    return send(request, env, { error: "Not found" }, 404);
  } catch (e) {
    console.error("studio failed", e);
    return send(request, env, { error: "Something went wrong. Please try again." }, 500);
  }
}
