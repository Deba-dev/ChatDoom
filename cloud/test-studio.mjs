// Offline test of Overlay Studio's storage, with a real SQLite database and a fake KV. Run: node test-studio.mjs
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { handleStudio } from "./src/studio.js";

let fails = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };

export function fakeEnv() {
  const sql = new DatabaseSync(":memory:"), kv = new Map();
  const stmt = (q) => ({ args: [], bind(...a) { this.args = a; return this; },
    async run() { const r = sql.prepare(q).run(...this.args); return { meta: { changes: Number(r.changes) } }; },
    async first() { return sql.prepare(q).get(...this.args) || null; },
    async all() { return { results: sql.prepare(q).all(...this.args) }; } });
  return { kv, DB: { prepare: stmt, async batch(list) { for (const s of list) await s.run(); return []; } },
    KV: { async put(k, v, o) { kv.set(k, { v, m: o && o.metadata }); }, async delete(k) { kv.delete(k); },
      async getWithMetadata(k) { const e = kv.get(k); return e ? { value: e.v.buffer, metadata: e.m } : { value: null, metadata: null }; } } };
}

if (path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const env = fakeEnv(), SITE = "https://zunimilabs.online", BASE = "https://cloud.zunimilabs.online";
  const call = async (method, path, { body, key, origin = SITE, ip = "1.1.1.1", raw } = {}) => {
    const headers = { "cf-connecting-ip": ip };
    if (origin) headers.origin = origin;
    if (key) headers.authorization = "Bearer " + key;
    const req = new Request(BASE + path, { method, headers, body: raw ?? (body === undefined ? undefined : JSON.stringify(body)) });
    const res = await handleStudio(req, env, new URL(req.url));
    const type = res.headers.get("content-type") || "";
    return { status: res.status, headers: res.headers, data: type.includes("json") ? await res.json() : await res.arrayBuffer() };
  };
  const design = { v: 2, source: { kind: "none" }, scenes: [{ id: "a", widgets: [] }] };
  const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10, 1, 2, 3]);

  let r = await call("POST", "/studio/designs", { body: { design } });
  ok(r.status === 201 && /^[0-9a-f]{24}$/.test(r.data.id) && r.data.key.length === 64 && r.headers.get("access-control-allow-origin") === SITE, "creating a design returns a link ID and a secret key");
  const { id, key } = r.data;
  r = await call("POST", "/studio/designs", { body: { design }, origin: "https://evil.example" });
  ok(r.status === 403, "other websites cannot create designs");
  r = await call("POST", "/studio/designs", { body: { design: { nope: 1 } } });
  ok(r.status === 400, "bad designs are refused");
  r = await call("POST", "/studio/designs", { raw: JSON.stringify({ design: { ...design, pad: "x".repeat(400000) } }) });
  ok(r.status === 413, "huge designs are refused");

  r = await call("GET", "/studio/designs/" + id, { origin: "" });
  ok(r.status === 200 && r.data.rev === 1 && r.data.design.scenes[0].id === "a" && !JSON.stringify(r.data).includes(key), "OBS can read a design, and the key is never sent");
  r = await call("PUT", "/studio/designs/" + id, { body: { design: { ...design, v: 3 } } });
  ok(r.status === 401, "changing a design needs the key");
  r = await call("PUT", "/studio/designs/" + id, { body: { design }, key: "0".repeat(64) });
  ok(r.status === 401, "a wrong key is refused");
  r = await call("PUT", "/studio/designs/" + id, { body: { design: { ...design, v: 3 } }, key });
  ok(r.status === 200 && r.data.rev === 2, "the right key saves a new version");
  r = await call("GET", "/studio/designs/" + id, { origin: "" });
  ok(r.data.rev === 2 && r.data.design.v === 3, "the new version is what OBS gets");

  r = await call("POST", "/studio/files?design=" + id + "&name=logo.png", { raw: png, key });
  ok(r.status === 201 && r.data.kind === "image" && r.data.url.includes("/studio/files/"), "a real PNG uploads");
  const file = r.data.id;
  r = await call("POST", "/studio/files?design=" + id, { raw: png });
  ok(r.status === 401, "uploads need the key");
  r = await call("POST", "/studio/files?design=" + id + "&name=x.png", { raw: new TextEncoder().encode("<svg onload=alert(1)>"), key });
  ok(r.status === 415, "a script named as a picture is refused");
  r = await call("POST", "/studio/files?design=" + id + "&name=x.html", { raw: new TextEncoder().encode("<html><script>alert(1)</script>"), key });
  ok(r.status === 415, "HTML is refused");
  const big = new Uint8Array(2 * 1024 * 1024 + 1); big.set(png);
  r = await call("POST", "/studio/files?design=" + id, { raw: big, key });
  ok(r.status === 413, "files over 2 MB are refused");
  r = await call("POST", "/studio/files?design=" + id + "&name=a.mp3", { raw: new Uint8Array([0x49, 0x44, 0x33, 4, 0, 0, 1, 2]), key });
  ok(r.status === 201 && r.data.kind === "sound", "an MP3 uploads as a sound");

  r = await call("GET", "/studio/files/" + file, { origin: "" });
  ok(r.status === 200 && r.headers.get("content-type") === "image/png" && r.headers.get("x-content-type-options") === "nosniff" && r.headers.get("content-security-policy").includes("sandbox"), "files are served safely by their real type");
  ok(new Uint8Array(r.data)[1] === 0x50, "the file's bytes come back unchanged");
  r = await call("GET", "/studio/designs/" + id + "/files", { key });
  ok(r.status === 200 && r.data.files.length === 2, "the owner can list their files");
  r = await call("GET", "/studio/designs/" + id + "/files", { origin: SITE });
  ok(r.status === 401, "others cannot list files");
  r = await call("DELETE", "/studio/designs/" + id + "/files/" + file, { key });
  ok(r.status === 200, "the owner can delete a file");
  r = await call("GET", "/studio/files/" + file, { origin: "" });
  ok(r.status === 404, "a deleted file is gone");

  let last;
  for (let i = 0; i < 12; i++) last = await call("POST", "/studio/designs", { body: { design }, ip: "2.2.2.2" });
  ok(last.status === 429, "new overlays per visitor are limited each day");
  const quiet = await call("POST", "/studio/designs", { body: { design }, ip: "3.3.3.3" });
  ok(quiet.status === 201, "the limit is per visitor");
  const usage = await env.DB.prepare("SELECT who FROM studio_usage").all();
  ok(usage.results.every((u) => /^[0-9a-f]{64}$/.test(u.who)), "visitor addresses are only stored as hashes");

  r = await call("DELETE", "/studio/designs/" + id, { key });
  ok(r.status === 200 && env.kv.size === 0, "deleting a design removes it and its files");
  r = await call("GET", "/studio/designs/" + id, { origin: "" });
  ok(r.status === 404, "a deleted design is gone");
  const pre = await handleStudio(new Request(BASE + "/studio/designs", { method: "OPTIONS", headers: { origin: SITE } }), env, new URL(BASE + "/studio/designs"));
  ok(pre.status === 204 && pre.headers.get("access-control-allow-methods").includes("PUT"), "the browser's pre-check passes for our site");
  console.log(fails ? fails + " FAILED" : "All passed");
  process.exit(fails ? 1 : 0);
}
