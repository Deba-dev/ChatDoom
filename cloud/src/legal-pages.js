const CONTACT = "debarshiparasar.business@gmail.com";

const styles = `
  :root{color-scheme:dark;font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif;background:#0e1118;color:#e8ebf3}
  *{box-sizing:border-box}body{margin:0}header,main,footer{width:min(900px,100% - 36px);margin:auto}
  header{padding:30px 0 18px;border-bottom:1px solid #272d3e;display:flex;justify-content:space-between;gap:20px;align-items:center}
  header a:first-child{font-size:22px;font-weight:700;color:#fff;text-decoration:none}
  nav{display:flex;gap:18px;flex-wrap:wrap}a{color:#9bbcff}main{padding:42px 0 70px}
  h1{font-size:clamp(32px,6vw,48px);line-height:1.12;margin:0 0 12px}
  h2{font-size:22px;margin:32px 0 8px}p,li{color:#c8ccda}p{margin:10px 0}
  .eyebrow,.updated{color:#a9afc2}.card{margin-top:26px;padding:22px;border:1px solid #272d3e;border-radius:14px;background:#161b27}
  footer{border-top:1px solid #272d3e;padding:20px 0 30px;color:#a9afc2;font-size:14px}
  @media(max-width:540px){header{align-items:flex-start;flex-direction:column}main{padding-top:30px}}
`;

function layout(title, description, body) {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="${description}"><title>${title} | CHATDOOM</title>
<style>${styles}</style></head><body>
<header><a href="/">CHATDOOM</a><nav aria-label="Main navigation">
<a href="/">Home</a><a href="/privacy">Privacy policy</a><a href="/terms">Terms of service</a>
</nav></header><main>${body}</main>
<footer>CHATDOOM is an independent project and is not affiliated with Google, YouTube, Twitch, Discord, or Cloudflare.
<br>Contact: <a href="mailto:${CONTACT}">${CONTACT}</a></footer></body></html>`;
}

const pages = {
  "/": () => layout("Streaming tools for Windows", "CHATDOOM reads live stream chat aloud and provides stream tools for Windows.",
    `<p class="eyebrow">A desktop companion for livestreamers</p>
<h1>Make your stream chat easier to follow.</h1>
<p>CHATDOOM is a Windows desktop app that reads YouTube, Twitch, and Kick chat aloud, with moderation controls, OBS overlays, music playback, Discord role tools, and optional YouTube and Twitch chat actions.</p>
<div class="card"><h2>Platform sign-in</h2>
<p>Signing in is optional. Reading chat aloud works without it. If you connect a YouTube or Twitch account, CHATDOOM uses the requested permissions only for features you turn on:</p>
<ul><li>sending a chat message you type in the app, or a reply to a chat command you set up,</li>
<li>creating a chat poll when you start one,</li>
<li>showing alerts for new public subscribers or followers.</li></ul>
<p>CHATDOOM uses YouTube API Services. It never posts, deletes or changes anything on your channel unless you ask it to, and it does not use your account data for advertising. You can disconnect from the platform card in the app, or remove access in your <a href="https://myaccount.google.com/permissions">Google account settings</a>. Read the <a href="/privacy">privacy policy</a> for details.</p>
<h2>YouTube moderator bot</h2>
<p>Streamers can add CHATDOOM's moderator bot to their channel. After the streamer proves the stream is theirs by typing a short code in their own live chat, the bot removes messages or times out viewers according to the rules the streamer chooses. It cannot see anything private.</p>
<h2>Get the app</h2><p>CHATDOOM is distributed through its <a href="https://github.com/Deba-dev/ChatDoom">GitHub project</a>. Builds and availability are managed by the project maintainer.</p></div>
<h2>Public information</h2><p>Read the <a href="/privacy">privacy policy</a> and <a href="/terms">terms of service</a>, or contact <a href="mailto:${CONTACT}">${CONTACT}</a>.</p>
<p class="updated">CHATDOOM cloud service and project information.</p>`),
  "/privacy": () => layout("Privacy policy", "How CHATDOOM handles information in its desktop app and cloud services.",
    `<p class="eyebrow">Privacy policy</p><h1>Your data and CHATDOOM</h1>
<p class="updated">Effective November 2, 2026</p>
<p>This policy explains how the CHATDOOM desktop application and its optional Cloudflare services handle information. CHATDOOM is maintained by its project developer. Questions or deletion requests: <a href="mailto:${CONTACT}">${CONTACT}</a>.</p>
<h2>Information stored on your device</h2>
<p>CHATDOOM stores your preferences and feature configuration in your Windows user profile, including channel names, moderation and voice settings, music-folder location, overlay and integration settings, account session handles, and a rolling list of YouTube public-subscriber IDs to avoid duplicate alerts. YouTube, Twitch, and Kick chat used for local reading is processed by the app to provide its features. Ordinary chat-reading content stays on your device unless you enable the optional English translation feature. When enabled, message text is sent through your authenticated CHATDOOM Worker to Cloudflare Workers AI for language detection and translation; text is not intentionally stored by CHATDOOM.</p>
<p>On Windows, platform session handles are protected with Windows Data Protection API (DPAPI) when available; if protection is unavailable, the app falls back to its regular local settings storage. Local files remain on your device unless you choose to share or back them up.</p>
<h2>YouTube and Twitch sign-in</h2>
<p>If you connect an account, CHATDOOM receives the provider's account identifier and display name and stores access and refresh tokens encrypted in the Cloudflare D1 database. The cloud keeps a hash of the app session handle rather than the handle itself. Short-lived sign-in state and hand-off tickets are stored in Cloudflare KV and expire automatically.</p>
<p>These permissions are used to check your connected account, send a chat message or create a poll when you request it, and provide the platform alerts you enable. YouTube subscriber alerts periodically request the channel's publicly visible subscriber list; private subscriptions are not returned. Twitch EventSub sends follow, subscription, gift, and raid notifications directly to the running desktop app. CHATDOOM does not use these tokens for advertising. Disconnecting in the app revokes the provider authorization and deletes the associated cloud account record. You can also revoke access in your Google or Twitch account settings.</p>
<h2>Google user data and YouTube API Services</h2>
<p>CHATDOOM uses YouTube API Services. By using CHATDOOM's YouTube features you agree to the <a href="https://www.youtube.com/t/terms">YouTube Terms of Service</a>, and Google's handling of your data is described in the <a href="https://policies.google.com/privacy">Google Privacy Policy</a>.</p>
<p>When you sign in with Google, CHATDOOM requests your basic profile (name and account identifier) and the <code>youtube.force-ssl</code> permission. It uses them only to:</p>
<ul><li>show which YouTube channel is connected,</li>
<li>post chat messages you send from the app or replies to chat commands you configured, in your own live chat,</li>
<li>create chat polls you start,</li>
<li>check your channel's public subscriber list for the subscriber alerts you enable.</li></ul>
<p>CHATDOOM does not read your email, private videos or account settings, does not sell Google user data, does not use it for advertising, and nobody reads it by hand except when you ask for help or the law requires it. It is shared only with the service providers listed below as needed to run these features. CHATDOOM's use and transfer of information received from Google APIs adheres to the <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>, including the Limited Use requirements.</p>
<p>You can revoke CHATDOOM's access at any time on the <a href="https://myaccount.google.com/permissions">Google security settings page</a> or by disconnecting in the app. Either way, the stored tokens stop working, and disconnecting in the app also deletes the cloud account record.</p>
<h2>YouTube moderator bot</h2>
<p>If a streamer uses the moderator bot, the app sends the bot the stream's video identifier and, for each message to act on, the viewer's channel identifier, display name and message text. The bot uses its own YouTube account (not the streamer's) to find that message in the public live chat and remove it or time out the viewer. To confirm the stream belongs to the streamer, the bot looks for a short code in the live chat. The cloud keeps the 15-minute codes and a per-channel daily action count in Cloudflare KV. The streamer's verification is a signed token stored on their PC that expires after about 90 days. Chat message text is not stored by the bot.</p>
<h2>Discord and streamer service data</h2>
<p>If you use Discord features, the cloud stores Discord server identifiers and names, feature configuration, role and invite rules, invite-use tracking, and platform-to-Discord account links needed to provide those features. Temporary Discord login codes expire automatically. Server configuration and account links remain until the service operator deletes them; email us to request removal.</p>
<h2>Payment alert data</h2>
<p>CHATDOOM does not process or hold payments. If you configure payment alerts, your payment provider sends webhook data needed to display an alert, such as a transaction identifier, time, display name, message, amount, and currency. When a webhook is processed, alert records older than three days are cleaned up; if no later webhook is received, cleanup may occur later. Payment credentials supplied to configure webhook verification are stored in the cloud service configuration and are used to validate webhook requests.</p>
<h2>Service providers and sharing</h2>
<p>Cloudflare provides the Worker, KV, D1, and (if enabled) Workers AI translation infrastructure. Google/YouTube, Twitch, and Discord receive requests necessary for the platform features you use. Your selected payment provider sends webhook events to the configured service. These providers handle information under their own terms and privacy policies. CHATDOOM does not sell personal information or use it for targeted advertising.</p>
<p>Cloudflare and other providers may process technical information such as IP address, request time, and browser or device details to deliver, secure, and operate their services, subject to their own policies.</p>
<h2>Retention and your choices</h2>
<p>Platform account records are kept until you disconnect or request deletion. Payment alert records are kept for up to three days. Discord configuration and account-link records are retained while those features are set up, unless removed on request. Local app settings can be removed by uninstalling CHATDOOM and deleting its existing data folder under <code>%APPDATA%\\ChatVoice</code>.</p>
<p>To request deletion of cloud data or ask a privacy question, email <a href="mailto:${CONTACT}">${CONTACT}</a>. Include enough detail to identify the relevant service or account, but do not email passwords, OAuth tokens, or other secrets.</p>
<h2>Children and policy changes</h2>
<p>CHATDOOM is a general-purpose tool for streamers and is not designed to collect personal information from children. If you believe a child has provided personal information through a CHATDOOM service, contact us so we can review and remove it.</p>
<p>This policy may be updated as CHATDOOM changes. The effective date above will be revised when material changes are made.</p>`),
  "/terms": () => layout("Terms of service", "Terms for using the CHATDOOM desktop application and cloud features.",
    `<p class="eyebrow">Terms of service</p><h1>Using CHATDOOM</h1>
<p class="updated">Effective November 2, 2026</p>
<p>By installing or using CHATDOOM, you agree to these terms. If you do not agree, do not use the application or its cloud features. Questions: <a href="mailto:${CONTACT}">${CONTACT}</a>.</p>
<h2>What CHATDOOM provides</h2>
<p>CHATDOOM is a desktop application and optional cloud service for reading livestream chat, moderation support, overlays, music playback, Discord role features, payment alerts from a streamer's own provider, and optional YouTube or Twitch chat actions. Features may change, be unavailable, or be discontinued.</p>
<h2>Your accounts and content</h2>
<p>You are responsible for securing your device and accounts, choosing appropriate settings, and ensuring that you have permission to use the content, accounts, and services you connect. Messages and polls are submitted to YouTube or Twitch only when you request them; you remain responsible for their content and compliance with applicable platform rules.</p>
<p>CHATDOOM does not process payments. Payment alerts depend on your own payment provider, webhook configuration, and internet connectivity. You are responsible for verifying your payment setup and for any payments or refunds handled by that provider.</p>
<h2>Third-party services</h2>
<p>YouTube, Google, Twitch, Discord, Cloudflare, and payment providers are independent services with their own terms, privacy practices, availability, and enforcement decisions. CHATDOOM is not affiliated with or endorsed by them. Your use of each service is also governed by that provider's terms.</p>
<p>CHATDOOM uses YouTube API Services. By using CHATDOOM's YouTube features, you agree to be bound by the <a href="https://www.youtube.com/t/terms">YouTube Terms of Service</a>. See also the <a href="https://policies.google.com/privacy">Google Privacy Policy</a>.</p>
<h2>Music and other third-party materials</h2>
<p>You are responsible for confirming that you have the necessary rights for any music or other material you play or distribute. Links or license information provided in CHATDOOM are for convenience and do not guarantee that a stream will avoid copyright claims or platform action. Do not redistribute third-party files unless their license permits it.</p>
<h2>Acceptable use</h2>
<p>Do not use CHATDOOM to violate laws, infringe others' rights, bypass platform safeguards, abuse connected services, or interfere with the service or other users. You are responsible for reviewing messages, moderation actions, and account permissions before relying on them.</p>
<h2>Availability and warranty</h2>
<p>CHATDOOM is provided on an “as available” basis, without guarantees that it will be uninterrupted, error-free, or suitable for a particular purpose. To the extent permitted by law, the project maintainer disclaims implied warranties. Nothing in these terms excludes rights or liability that cannot legally be excluded.</p>
<h2>Limitation of liability</h2>
<p>To the extent permitted by law, the project maintainer is not liable for indirect or consequential loss, loss of data, lost revenue, stream interruption, or actions taken by third-party platforms arising from use of CHATDOOM. This does not limit liability that applicable law does not allow to be limited.</p>
<h2>Changes and contact</h2>
<p>These terms may be updated when the application or its services change. Continued use after updated terms are posted means you accept them to the extent permitted by law. Contact <a href="mailto:${CONTACT}">${CONTACT}</a> with questions.</p>`)
};

export function handlePublicPage(request, url) {
  if (request.method !== "GET" && request.method !== "HEAD") return null;
  const render = pages[url.pathname];
  if (!render) return null;
  const body = render();
  return new Response(request.method === "HEAD" ? null : body, {
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=3600" },
  });
}
