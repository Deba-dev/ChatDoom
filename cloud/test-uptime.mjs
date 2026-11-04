// Offline test of the uptime history, running the real SQL on an in-memory database. Run: node test-uptime.mjs
import { DatabaseSync } from "node:sqlite";
import { recordUptime, statusFeed } from "./src/uptime.js";

let fails = 0;
const ok = (c, msg) => { console.log((c ? "PASS " : "FAIL ") + msg); if (!c) fails++; };

const sql = new DatabaseSync(":memory:");
const stmt = (q, args = []) => ({
  bind: (...a) => stmt(q, a),
  run() { sql.prepare(q).run(...args); return { success: true }; },
  all() { return { results: sql.prepare(q).all(...args) }; },
  q,
});
const DB = { prepare: (q) => stmt(q), batch: async (list) => list.map((s) => (/^\s*SELECT/i.test(s.q) ? s.all() : s.run())) };

const state = { discord: 200, tokeninfo: 200, refresh: 200 };
const store = new Map();
const KV = { async get(k) { return store.get(k) ?? null; }, async put(k, v) { store.set(k, v); }, async delete(k) { store.delete(k); } };
const seen = [];
globalThis.fetch = async (url) => {
  const u = new URL(url);
  seen.push(u.hostname + u.pathname);
  if (u.hostname === "discord.com") return new Response("{}", { status: state.discord });
  if (u.pathname === "/token") return new Response(JSON.stringify(state.refresh === 200 ? { access_token: "A", expires_in: 3600 } : { error: "invalid_grant" }), { status: state.refresh });
  if (u.pathname === "/tokeninfo") return new Response("{}", { status: state.tokeninfo });
  throw new Error("unexpected call " + url);
};
const env = { DB, KV, DISCORD_BOT_TOKEN: "T", YT_BOT_KEY: "K", YT_BOT_CLIENT_ID: "C", YT_BOT_CLIENT_SECRET: "S", YT_BOT_REFRESH_TOKEN: "R" };
const feed = async (now) => (await statusFeed(env, now)).json();
const HOUR = 3_600_000, DAY = 24 * HOUR;
const t0 = Math.floor(Date.UTC(2026, 10, 4, 12) / HOUR) * HOUR;

let d = await feed(t0);
ok(d.services.length === 2 && d.services.every((s) => s.status === "unknown" && s.uptime90d === null && s.days.length === 90 && s.hours.length === 48),
   "before any check both bots show unknown, not up");

for (let i = 0; i < 3; i++) await recordUptime(env, t0 + i * 120_000);
state.discord = 503;
await recordUptime(env, t0 + 3 * 120_000);
d = await feed(t0 + 3 * 120_000);
const [discord, youtube] = d.services;
ok(discord.status === "down" && discord.uptime24h === 75 && discord.days.at(-1).uptime === 75 && discord.hours.at(-1).uptime === 75, "a failed Discord check shows down and lowers its uptime");
ok(youtube.status === "up" && youtube.uptime24h === 100, "the other bot is not affected");
ok(discord.name === "Discord bot" && youtube.name === "YouTube bot", "both bots are named for the page");

state.discord = 429; const before = (await feed(t0 + 4 * 120_000)).services[0].days.at(-1).uptime;
await recordUptime(env, t0 + 4 * 120_000);
ok((await feed(t0 + 4 * 120_000)).services[0].days.at(-1).uptime === before, "a Discord rate limit is skipped, not counted as down");

state.discord = 200; state.refresh = 400; store.clear();
await recordUptime(env, t0 + 5 * 120_000);
ok((await feed(t0 + 5 * 120_000)).services[1].status === "down", "a YouTube bot whose sign-in was revoked shows down");
state.refresh = 200; store.clear(); state.tokeninfo = 400;
await recordUptime(env, t0 + 6 * 120_000);
ok((await feed(t0 + 6 * 120_000)).services[1].status === "down", "a rejected Google token shows down");
state.tokeninfo = 200;

ok((await feed(t0 + 6 * 120_000 + 11 * 60_000)).services.every((s) => s.status === "unknown"), "if the checker stops, the page says unknown instead of a stale up");

await recordUptime(env, t0 + 92 * DAY);
const rows = sql.prepare("SELECT COUNT(*) AS n FROM uptime_hours WHERE hour = ?").get(t0 / HOUR).n;
ok(rows === 0, "history older than 90 days is removed");

const res = await statusFeed(env, t0);
const text = JSON.stringify(await res.clone().json());
ok(res.headers.get("access-control-allow-origin") === "*" && res.headers.get("cache-control").includes("max-age=60"), "the website may read the feed, and it is cached for a minute");
ok(!text.includes('"T"') && !text.includes('"R"') && !text.toLowerCase().includes("token"), "the public feed contains no secrets");
ok(!seen.some((u) => u.includes("googleapis.com/youtube")), "the checks use no YouTube API quota");

const noDb = await statusFeed({}, t0);
ok(noDb.status === 503, "without storage the feed says so instead of crashing");
await recordUptime({}, t0);
ok(true, "without storage the check does nothing");

console.log(fails ? fails + " FAILED" : "all passed");
process.exit(fails ? 1 : 0);
