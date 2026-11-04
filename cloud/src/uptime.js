// Uptime history for the website's status page (zunimilabs.online/status/).
// The 2-minute cron checks each bot and adds the result to one row per hour in D1. /status.json serves the totals.
// It holds only up/down counts: no tokens, names or viewer data, so the feed is public.
import { botSignedIn } from "./youtube-bot.js";

const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const KEEP_DAYS = 90;
const STALE_MS = 10 * 60_000;       // no check for this long means the checker itself has stopped

// true = working, false = not working, null = could not tell (the check is skipped, so it counts for neither)
async function checkDiscord(env) {
  if (!env.DISCORD_BOT_TOKEN) return false;
  const r = await fetch("https://discord.com/api/v10/users/@me", { headers: { authorization: `Bot ${env.DISCORD_BOT_TOKEN}` } });
  if (r.status === 429) return null;
  return r.ok;
}

export const SERVICES = [
  { key: "discord", name: "Discord bot", detail: "Roles, invites, announcements and payment alerts", check: checkDiscord },
  { key: "youtube", name: "YouTube bot", detail: "The moderator bot for live chat", check: botSignedIn },
];

let tableReady = null;
function ready(env) {
  if (!tableReady) {
    tableReady = env.DB.batch([
      env.DB.prepare("CREATE TABLE IF NOT EXISTS uptime_hours (service TEXT NOT NULL, hour INTEGER NOT NULL, checks INTEGER NOT NULL, ups INTEGER NOT NULL, PRIMARY KEY (service, hour))"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS uptime_latest (service TEXT PRIMARY KEY, up INTEGER NOT NULL, at INTEGER NOT NULL)"),
    ]).catch((e) => { tableReady = null; throw e; });
  }
  return tableReady;
}

export async function recordUptime(env, now = Date.now()) {
  if (!env.DB) return;
  await ready(env);
  const hour = Math.floor(now / HOUR);
  const results = await Promise.all(SERVICES.map((s) => s.check(env).catch(() => false)));
  const writes = [];
  SERVICES.forEach((s, i) => {
    const up = results[i];
    if (up === null) return;
    writes.push(env.DB.prepare("INSERT INTO uptime_hours (service, hour, checks, ups) VALUES (?, ?, 1, ?) " +
                               "ON CONFLICT (service, hour) DO UPDATE SET checks = checks + 1, ups = ups + excluded.ups").bind(s.key, hour, up ? 1 : 0));
    writes.push(env.DB.prepare("INSERT INTO uptime_latest (service, up, at) VALUES (?, ?, ?) " +
                               "ON CONFLICT (service) DO UPDATE SET up = excluded.up, at = excluded.at").bind(s.key, up ? 1 : 0, now));
  });
  if (now % HOUR < 150_000) writes.push(env.DB.prepare("DELETE FROM uptime_hours WHERE hour < ?").bind(hour - (KEEP_DAYS + 1) * 24));
  if (writes.length) await env.DB.batch(writes);
}

const percent = (ups, checks) => (checks ? Math.round((ups / checks) * 10000) / 100 : null);

function summarise(service, rows, latest, now) {
  const hourNow = Math.floor(now / HOUR);
  const byHour = new Map(rows.map((r) => [r.hour, r]));
  const hours = [];
  for (let h = hourNow - 47; h <= hourNow; h++) {
    const r = byHour.get(h);
    hours.push({ at: h * HOUR, uptime: r ? percent(r.ups, r.checks) : null });
  }
  const dayNow = Math.floor(now / DAY);
  const days = new Map();
  let checks = 0, ups = 0, checks24 = 0, ups24 = 0;
  for (const r of rows) {
    const d = Math.floor((r.hour * HOUR) / DAY);
    const total = days.get(d) || { checks: 0, ups: 0 };
    total.checks += r.checks;
    total.ups += r.ups;
    days.set(d, total);
    checks += r.checks;
    ups += r.ups;
    if (r.hour > hourNow - 24) { checks24 += r.checks; ups24 += r.ups; }
  }
  const dayList = [];
  for (let d = dayNow - KEEP_DAYS + 1; d <= dayNow; d++) {
    const t = days.get(d);
    dayList.push({ day: new Date(d * DAY).toISOString().slice(0, 10), uptime: t ? percent(t.ups, t.checks) : null });
  }
  const fresh = latest && now - latest.at < STALE_MS;
  return { key: service.key, name: service.name, detail: service.detail, status: !fresh ? "unknown" : latest.up ? "up" : "down",
           lastCheck: latest ? latest.at : null, uptime24h: percent(ups24, checks24), uptime90d: percent(ups, checks), hours, days: dayList };
}

export async function statusFeed(env, now = Date.now()) {
  const headers = { "content-type": "application/json", "access-control-allow-origin": "*", "cache-control": "public, max-age=60" };
  if (!env.DB) return new Response(JSON.stringify({ error: "status storage is not set up" }), { status: 503, headers });
  await ready(env);
  const oldest = Math.floor(now / HOUR) - KEEP_DAYS * 24;
  const [hours, latest] = await env.DB.batch([
    env.DB.prepare("SELECT service, hour, checks, ups FROM uptime_hours WHERE hour >= ?").bind(oldest),
    env.DB.prepare("SELECT service, up, at FROM uptime_latest"),
  ]);
  const services = SERVICES.map((s) => summarise(s, hours.results.filter((r) => r.service === s.key),
                                                 latest.results.find((r) => r.service === s.key), now));
  return new Response(JSON.stringify({ updated: now, services }), { headers });
}
