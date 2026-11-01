// OPTIONAL: shows the CHATDOOM Discord bot as "Online" (green dot) in member lists.
// The bot already works 24/7 without this: roles, invites and announcements run on the Cloudflare Worker.
// Discord only shows the green dot while a program keeps a gateway connection open, so this needs an always-on
// machine (see HOSTING.txt). Node 22 or newer, no packages:   DISCORD_BOT_TOKEN=... node presence.mjs
const TOKEN = process.env.DISCORD_BOT_TOKEN;
const STATUS_TEXT = process.env.PRESENCE_TEXT || "your chat | CHATDOOM";
if (!TOKEN) { console.error("Set DISCORD_BOT_TOKEN first."); process.exit(1); }

let seq = null, beat = null, acked = true, backoff = 2000;

function connect() {
  const ws = new WebSocket("wss://gateway.discord.gg/?v=10&encoding=json");
  const send = (op, d) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ op, d }));
  ws.onmessage = (event) => {
    const { op, d, s, t } = JSON.parse(event.data);
    if (s !== null && s !== undefined) seq = s;
    if (op === 10) {                                                     // Hello: start heartbeats, then identify
      clearInterval(beat);
      acked = true;
      beat = setInterval(() => {
        if (!acked) return ws.close(4900, "no heartbeat ack");            // zombie connection: reconnect
        acked = false;
        send(1, seq);
      }, d.heartbeat_interval);
      send(2, { token: TOKEN, intents: 0, properties: { os: process.platform, browser: "chatdoom", device: "chatdoom" },
                presence: { status: "online", since: null, afk: false, activities: [{ name: STATUS_TEXT, type: 3 }] } });
    } else if (op === 11) acked = true;
    else if (op === 1) send(1, seq);
    else if (op === 7 || op === 9) ws.close(4901, "reconnect requested");
    else if (op === 0 && t === "READY") { backoff = 2000; console.log(new Date().toISOString(), "online as", d.user.username); }
  };
  ws.onclose = (event) => {
    clearInterval(beat);
    if ([4004, 4010, 4011, 4012, 4013, 4014].includes(event.code)) {    // bad token or settings: retrying will not help
      console.error("Discord refused the connection:", event.code, event.reason);
      process.exit(1);
    }
    console.log(new Date().toISOString(), "disconnected", event.code, "- reconnecting in", backoff / 1000, "s");
    setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, 60_000);
  };
  ws.onerror = () => {};                                                 // onclose handles the retry
}

connect();
