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
      async get(k) { const e = kv.get(k); return e ? e.v : null; },
      async getWithMetadata(k) { const e = kv.get(k); return e ? { value: e.v.buffer, metadata: e.m } : { value: null, metadata: null }; } } };
}

if (path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const env = Object.assign(fakeEnv(), { GOOGLE_OAUTH_CLIENT_ID: "g-id", GOOGLE_OAUTH_CLIENT_SECRET: "g-secret", DISCORD_CLIENT_ID: "d-id", DISCORD_CLIENT_SECRET: "d-secret" }), SITE = "https://zunimilabs.online", BASE = "https://cloud.zunimilabs.online";
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

  // Stands in for Google and Discord. The code says which account signs in.
  const seen = [];
  globalThis.fetch = async (u, o = {}) => {
    const address = String(u);
    seen.push({ address, body: String(o.body || "") });
    const reply = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
    if (address.includes("/token")) {
      const code = new URLSearchParams(String(o.body)).get("code");
      return code === "refused" ? reply({ error: "invalid_client" }, 401) : reply({ access_token: "at-" + code });
    }
    const who = o.headers.authorization.slice(10);
    return address.includes("googleapis") ? reply({ sub: "g-" + who, name: "Google " + who }) : reply({ id: "d-" + who, username: "disc" + who, global_name: null });
  };
  const nonce = "a".repeat(32);
  const startAt = (q) => { const u = BASE + "/studio/auth/start?" + q; return handleStudio(new Request(u), env, new URL(u)); };
  const startLogin = async (name) => new URL((await startAt("provider=" + name + "&site=" + encodeURIComponent(SITE) + "&nonce=" + nonce)).headers.get("location"));
  const finishLogin = async (name, code, state) => {
    const u = BASE + "/studio/auth/" + name + "/callback?state=" + state + (code ? "&code=" + code : "&error=access_denied");
    const r = await handleStudio(new Request(u), env, new URL(u));
    return new URL(r.headers.get("location"));
  };
  const signIn = async (name, code) => {
    const to = await startLogin(name), back = await finishLogin(name, code, to.searchParams.get("state"));
    return (await call("POST", "/studio/auth/redeem", { body: { ticket: back.hash.slice(7), nonce } })).data;
  };

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
  ok(r.status === 401 && r.data.error.includes("sign in"), "uploading needs a signed-in account, not just a design key");

  // Signing in
  let to = await startLogin("google");
  ok(to.origin === "https://accounts.google.com" && to.searchParams.get("scope") === "openid profile" && to.searchParams.get("redirect_uri") === BASE + "/studio/auth/google/callback", "Google sign-in asks for the basic profile only");
  to = await startLogin("discord");
  ok(to.origin === "https://discord.com" && to.searchParams.get("scope") === "identify" && to.searchParams.get("redirect_uri") === BASE + "/studio/auth/discord/callback", "Discord sign-in asks for the basic profile only");
  r = await startAt("provider=google&nonce=" + nonce + "&site=" + encodeURIComponent("https://evil.example"));
  ok(r.status === 403, "sign-in never returns to another website");
  r = await startAt("provider=constructor&nonce=" + nonce + "&site=" + encodeURIComponent(SITE));
  ok(r.headers.get("location").includes("#login-error="), "an unknown provider is refused");
  let back = await finishLogin("google", "x", "f".repeat(48));
  ok(back.origin === SITE && back.hash.startsWith("#login-error="), "a made-up state is refused");
  to = await startLogin("google");
  back = await finishLogin("discord", "x", to.searchParams.get("state"));
  ok(back.hash.startsWith("#login-error="), "a state from the other provider is refused");
  to = await startLogin("google");
  back = await finishLogin("google", "", to.searchParams.get("state"));
  ok(decodeURIComponent(back.hash).includes("cancelled"), "pressing cancel returns to the Studio with a reason");
  to = await startLogin("google");
  back = await finishLogin("google", "refused", to.searchParams.get("state"));
  ok(decodeURIComponent(back.hash).includes("invalid_client"), "a provider failure shows the real reason");
  to = await startLogin("google");
  const state = to.searchParams.get("state");
  back = await finishLogin("google", "one", state);
  ok(back.origin === SITE && back.pathname === "/studio/" && back.hash.startsWith("#login="), "signing in returns to the Studio with a ticket");
  const ticket = back.hash.slice(7);
  ok(seen.at(-2).body.includes("client_secret=g-secret"), "the secret goes only to the provider");
  ok(!back.toString().includes("at-one"), "the provider's token never reaches the browser");
  back = await finishLogin("google", "one", state);
  ok(back.hash.startsWith("#login-error="), "a sign-in state works only once");
  r = await call("POST", "/studio/auth/redeem", { body: { ticket, nonce: "b".repeat(32) } });
  ok(r.status === 400, "another browser cannot use the ticket");
  r = await call("POST", "/studio/auth/redeem", { body: { ticket, nonce } });
  ok(r.status === 400, "a ticket is used up after one try");
  const one = await signIn("google", "one");
  ok(one.token.length === 64 && one.user.name === "Google one" && one.user.provider === "google", "the right browser gets a session");
  const session = one.token;
  const stored = await env.DB.prepare("SELECT * FROM studio_sessions").all();
  ok(stored.results.every((s) => s.token_hash !== session), "sessions are only stored as hashes");
  ok(!JSON.stringify((await env.DB.prepare("SELECT * FROM studio_users").all()).results).includes("at-one"), "provider tokens are not kept");
  r = await call("GET", "/studio/auth/me", { key: session, origin: "https://evil.example" });
  ok(r.status === 403, "other websites cannot read the account");
  r = await call("GET", "/studio/auth/me", { key: "0".repeat(64) });
  ok(r.status === 401, "a wrong session is refused");
  const again = await signIn("google", "one");
  r = await call("GET", "/studio/auth/me", { key: again.token });
  ok(r.data.designs.length === 0 && (await env.DB.prepare("SELECT COUNT(*) AS n FROM studio_users").first()).n === 1, "signing in twice is the same account");
  const discordUser = await signIn("discord", "two");
  ok(discordUser.user.name === "disctwo", "Discord names work without a display name");

  // Moving an existing design to the account
  r = await call("POST", "/studio/files?design=" + id + "&name=logo.png", { raw: png, key: session });
  ok(r.status === 401, "a design that is not yours cannot take uploads");
  r = await call("POST", "/studio/designs/" + id + "/claim", { body: { key: "0".repeat(64) }, key: session });
  ok(r.status === 403, "claiming a design needs its key");
  r = await call("POST", "/studio/designs/" + id + "/claim", { body: { key } });
  ok(r.status === 401, "claiming a design needs an account");
  r = await call("POST", "/studio/designs/" + id + "/claim", { body: { key }, key: session });
  ok(r.status === 200, "signing in moves an existing design to the account");
  r = await call("POST", "/studio/designs/" + id + "/claim", { body: { key }, key: discordUser.token });
  ok(r.status === 403, "nobody else can claim it with the old key");
  r = await call("PUT", "/studio/designs/" + id, { body: { design: { ...design, v: 4 } }, key });
  ok(r.status === 401, "the old key stops working after the move");
  r = await call("PUT", "/studio/designs/" + id, { body: { design: { ...design, v: 4 } }, key: discordUser.token });
  ok(r.status === 401, "another account cannot change it");
  r = await call("PUT", "/studio/designs/" + id, { body: { design: { ...design, v: 3 } }, key: session });
  ok(r.status === 200, "the account can change it");
  r = await call("GET", "/studio/designs/" + id, { origin: "" });
  ok(r.status === 200 && r.data.design.v === 3, "OBS links keep working after the move");
  r = await call("GET", "/studio/auth/me", { key: session });
  ok(r.data.designs.length === 1 && r.data.designs[0].id === id, "the account lists its overlays on any computer");

  r = await call("POST", "/studio/files?design=" + id + "&name=logo.png", { raw: png, key: session });
  ok(r.status === 201 && r.data.kind === "image" && r.data.url.includes("/studio/files/"), "a real PNG uploads");
  const file = r.data.id;
  r = await call("POST", "/studio/files?design=" + id, { raw: png });
  ok(r.status === 401, "uploads need the key");
  r = await call("POST", "/studio/files?design=" + id + "&name=x.png", { raw: new TextEncoder().encode("<svg onload=alert(1)>"), key: session });
  ok(r.status === 415, "a script named as a picture is refused");
  r = await call("POST", "/studio/files?design=" + id + "&name=x.html", { raw: new TextEncoder().encode("<html><script>alert(1)</script>"), key: session });
  ok(r.status === 415, "HTML is refused");
  const big = new Uint8Array(2 * 1024 * 1024 + 1); big.set(png);
  r = await call("POST", "/studio/files?design=" + id, { raw: big, key: session });
  ok(r.status === 413, "files over 2 MB are refused");
  r = await call("POST", "/studio/files?design=" + id + "&name=a.mp3", { raw: new Uint8Array([0x49, 0x44, 0x33, 4, 0, 0, 1, 2]), key: session });
  ok(r.status === 201 && r.data.kind === "sound", "an MP3 uploads as a sound");

  r = await call("GET", "/studio/files/" + file, { origin: "" });
  ok(r.status === 200 && r.headers.get("content-type") === "image/png" && r.headers.get("x-content-type-options") === "nosniff" && r.headers.get("content-security-policy").includes("sandbox"), "files are served safely by their real type");
  ok(new Uint8Array(r.data)[1] === 0x50, "the file's bytes come back unchanged");
  r = await call("GET", "/studio/designs/" + id + "/files", { key: session });
  ok(r.status === 200 && r.data.files.length === 2, "the owner can list their files");
  r = await call("GET", "/studio/designs/" + id + "/files", { origin: SITE });
  ok(r.status === 401, "others cannot list files");
  r = await call("DELETE", "/studio/designs/" + id + "/files/" + file, { key: session });
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

  r = await call("DELETE", "/studio/designs/" + id, { key: session });
  ok(r.status === 200 && ![...env.kv.keys()].some((k) => k.startsWith("studio-file:")), "deleting a design removes it and its files");
  r = await call("GET", "/studio/designs/" + id, { origin: "" });
  ok(r.status === 404, "a deleted design is gone");
  r = await call("GET", "/studio/auth/me", { key: session });
  ok(r.data.designs.length === 0 && !(await env.DB.prepare("SELECT 1 AS y FROM studio_owners WHERE design_id = ?").bind(id).first()), "a deleted design leaves the account");

  // Signed-in saving, blocking, signing out and deleting an account
  r = await call("POST", "/studio/designs", { body: { design }, key: session });
  ok(r.status === 201 && !r.data.key, "a signed-in design needs no secret key");
  const owned = r.data.id;
  r = await call("POST", "/studio/designs", { body: { design }, key: "0".repeat(64) });
  ok(r.status === 401, "an expired session does not quietly make an anonymous design");
  r = await call("POST", "/studio/files?design=" + owned + "&name=a.png", { raw: png, key: session });
  ok(r.status === 201, "uploads work on a signed-in design");
  const ownedFile = r.data.id;
  await env.DB.prepare("UPDATE studio_users SET blocked = 1 WHERE provider = 'google'").run();
  r = await call("POST", "/studio/files?design=" + owned + "&name=a.png", { raw: png, key: session });
  ok(r.status === 401, "a blocked account cannot upload");
  to = await startLogin("google");
  back = await finishLogin("google", "one", to.searchParams.get("state"));
  ok(back.hash.startsWith("#login-error="), "a blocked account cannot sign in");
  await env.DB.prepare("UPDATE studio_users SET blocked = 0 WHERE provider = 'google'").run();
  await env.DB.prepare("UPDATE studio_sessions SET expires = 1 WHERE token_hash = (SELECT token_hash FROM studio_sessions LIMIT 1)").run();
  const fresh = await signIn("google", "one");
  r = await call("GET", "/studio/auth/me", { key: fresh.token });
  ok(r.status === 200, "a new session works");
  ok(!(await env.DB.prepare("SELECT 1 AS y FROM studio_sessions WHERE expires = 1").first()), "old sessions are cleared");
  await call("DELETE", "/studio/auth/session", { key: fresh.token });
  r = await call("GET", "/studio/auth/me", { key: fresh.token });
  ok(r.status === 401, "signing out ends the session");
  const final = await signIn("google", "one");
  r = await call("DELETE", "/studio/auth/account", { key: final.token });
  ok(r.status === 200, "an account can be deleted");
  r = await call("GET", "/studio/designs/" + owned, { origin: "" });
  ok(r.status === 404, "deleting an account deletes its overlays");
  r = await call("GET", "/studio/files/" + ownedFile, { origin: "" });
  ok(r.status === 404, "deleting an account deletes its files");
  ok(!(await env.DB.prepare("SELECT 1 AS y FROM studio_users WHERE provider = 'google'").first()), "nothing about the account is left");

  const pre = await handleStudio(new Request(BASE + "/studio/designs", { method: "OPTIONS", headers: { origin: SITE } }), env, new URL(BASE + "/studio/designs"));
  ok(pre.status === 204 && pre.headers.get("access-control-allow-methods").includes("PUT"), "the browser's pre-check passes for our site");
  console.log(fails ? fails + " FAILED" : "All passed");
  process.exit(fails ? 1 : 0);
}
