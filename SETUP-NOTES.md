# CHATDOOM setup notes

Notes from the 2026-11-02 session: hosting, YouTube login, the bot account, the VPS, and what is still open.
For the person who runs CHATDOOM (streamers never do any of this).

`YOUR-CLOUD` = `https://chatvoice-cloud.debarshiparasar7.workers.dev` today, `https://yourdomain.com` once a custom domain is attached to the Worker.

---

## 1. How everything stays online 24/7

Everything runs on the Cloudflare Worker `chatvoice-cloud` (the `cloud/` folder). Workers are free and never sleep. Render isn't used any more.

| Part | Where | Notes |
|---|---|---|
| YouTube moderator bot (`/v1`) | Worker, `cloud/src/youtube-bot.js` | Runs only when the app calls it. Secrets: `YT_BOT_KEY`, `YT_BOT_CLIENT_ID`, `YT_BOT_CLIENT_SECRET`, `YT_BOT_REFRESH_TOKEN`. Check: `YOUR-CLOUD/v1/info` → `"authorized": true`. |
| Discord bot (roles, invites, announcements, payment alerts) | Worker | Uses Discord's web API plus a 2-minute cron job. Already 24/7. |
| Discord bot's green "online" dot | Needs an always-on machine (section 5) | `discord-presence/presence.mjs`. Optional, cosmetic only. |
| Streamer login (`/platform-auth`) | Worker, `cloud/src/platform-auth.js` | Secrets: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (and the Twitch ones). |
| Home, `/privacy`, `/terms` | Worker, `cloud/src/legal-pages.js` | Updated for Google verification on 2026-11-02 (section 4). |

More detail: `HOSTING.txt`, `CLOUD-SETUP.txt`, `YT-MODERATION-SETUP.txt`.

---

## 2. What needs the streamer's YouTube login

Reading chat never needs a login. Only **posting into chat** does.

| Works without login | Needs login |
|---|---|
| Read-aloud commands, memes (sound, overlay image, voice) | Text replies from `!commands` in chat |
| Counting loyalty points, poll votes, giveaway entries | `!points`, `!top`, `!gamble` answers in chat |
| Counters, widgets overlay, hotkeys, song requests | Welcome messages and timers posted in chat |
| | Typing in chat from the app, YouTube polls, subscriber alerts |

Without a login, the app shows the reply in the feed marked "not sent in chat" (`app/ui.py`, `_reply_target`).

**Kick login doesn't exist in the code.** `PlatformAuth.SUPPORTED = ("youtube", "twitch")` in `app/platform_auth.py`. Kick is read-only until it's built: a Kick developer app, OAuth with PKCE, and a Kick provider in `platform-auth.js`.

### Ways to do YouTube login (decided: keep the real login and add the others)

Posting in someone's chat as that person always needs Google OAuth with `youtube.force-ssl`. That scope is **sensitive, not restricted**, so it gets Google's normal review with no paid security audit.

1. **Unverified OAuth app** (what's built now): max 100 users, warning screen. Publish it to production so logins don't expire after 7 days. Fine for a beta.
2. **Verified OAuth app:** the end goal. Needs your own domain, Search Console, a demo video, and weeks of waiting.
3. **Bot posts the replies** (Nightbot style): no streamer login needed, replies come from the bot channel. About 50 units per message, so roughly 200 messages a day on 10k quota. *Not built yet.*
4. Streamers use their own Google Cloud project: works, but too hard for most streamers.
5. Showing YouTube's own chat page inside the app: manual typing only. Automating it breaks YouTube's rules, so don't.

Plan: options 1 + 3 now, option 2 in parallel once a domain is set up.

---

## 3. Bot account security (how Nightbot does it)

Nightbot uses its own dedicated "Nightbot" channel. Streamers add it as a moderator, and its Google project is verified by Google.

Problem: the CHATDOOM bot currently runs on **your personal YouTube account** (`@ChatVoice-V1`). Its refresh token in the Worker gives full YouTube control of that account. Streamers aren't at risk (a moderator can only delete messages and time people out); **your** account is.

Fix:
1. Create a brand-new Google account used only for the bot. Turn on 2FA and create a YouTube channel on it (e.g. "ChatDoom Bot").
2. Sign it in via Part 2 below and replace `YT_BOT_REFRESH_TOKEN`.
3. Change `YT_BOT_HANDLE` in `app/config.py` (and the guides and tests that mention `@ChatVoice-V1`).
4. Streamers have to add the new bot as a moderator again.
5. On your personal account, revoke the old access: myaccount.google.com → Security → Third-party connections.

---

## 4. Google Cloud Console: full setup

Use **two projects**. Each gets its own 10,000-unit daily quota, and the bot project never needs a review.
Use **your** account in Google Cloud. Use the bot account only in Part 2, step 9.

### Part 1: Streamer login project

1. console.cloud.google.com → project picker → **New project** `CHATDOOM` → select it.
2. **APIs & Services → Library → YouTube Data API v3 → Enable**.
3. **Google Auth Platform → Get started**:
   - App name `CHATDOOM`, your support email.
   - Audience **External**, your contact email → **Create**.
4. **Branding**:
   - Home `YOUR-CLOUD/`, Privacy `YOUR-CLOUD/privacy`, Terms `YOUR-CLOUD/terms`.
   - Authorized domain = your domain (skip while on workers.dev).
   - **No logo** (a logo forces a review) → Save.
5. **Data Access → Add or remove scopes**: `openid`, `.../auth/userinfo.profile`, `https://www.googleapis.com/auth/youtube.force-ssl` → Save.
6. **Audience → Test users**: add your Gmail and any tester accounts (max 100).
7. **Clients → Create client → Web application** `CHATDOOM login`:
   - Redirect URI: `YOUR-CLOUD/platform-auth/youtube/callback`. Must match exactly: https, no slash at the end.
   - Copy the ID and secret right away; the secret is shown only once.
8. In `cloud/`:
   ```
   npx wrangler secret put GOOGLE_OAUTH_CLIENT_ID
   npx wrangler secret put GOOGLE_OAUTH_CLIENT_SECRET
   npx wrangler deploy
   ```
   Check `YOUR-CLOUD/health` → `GOOGLE_OAUTH_CLIENT_ID` shows `looks_right: true`.
9. Test: in the app, YouTube card → Sign in. On "Google hasn't verified this app", click Continue.
10. **Audience → Publish app**. Status becomes "In production" (unverified: 100 users, no 7-day expiry).
11. **Verification** (once you have a domain):
    - Verify the domain in **Search Console** with the same account that owns the project, using a DNS TXT record in Cloudflare.
    - Record an unlisted YouTube demo video showing sign-in, the consent screen with the client ID in the URL, sending a message and creating a poll.
    - **Verification Center**: explain the scope ("Posts chat messages and creates polls in the user's own live chat when they request it, and reads the public subscriber list for alerts."), add the video, and submit.

### Part 2: Bot project

1. **New project** `CHATDOOM Bot` → enable **YouTube Data API v3**.
2. **Google Auth Platform → Get started**: `CHATDOOM Bot`, External.
3. **Branding**: same URLs as Part 1, no logo.
4. **Data Access**: only `https://www.googleapis.com/auth/youtube.force-ssl`.
5. **Audience → Publish app** ("In production"). **Don't submit for verification.** Publishing stops the bot's login expiring after 7 days.
6. **Clients → Create client → Web application** `CHATDOOM bot`, redirect URI `YOUR-CLOUD/v1/oauth/callback`.
7. In `cloud/`:
   ```
   node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
   npx wrangler secret put YT_BOT_KEY             (the random value; keep a copy)
   npx wrangler secret put YT_BOT_CLIENT_ID
   npx wrangler secret put YT_BOT_CLIENT_SECRET
   npx wrangler deploy
   ```
   A new `YT_BOT_KEY` cancels old streamer verifications (fine when switching to a new bot account).
8. In an **incognito window**, open `YOUR-CLOUD/v1/admin`:
   - Paste `YT_BOT_KEY` → **Authorize bot Google account** → sign in as the **bot** account.
   - Click Advanced → Go to CHATDOOM Bot (unsafe) → Allow.
   - Copy the refresh token, then:
   ```
   npx wrangler secret put YT_BOT_REFRESH_TOKEN
   npx wrangler deploy
   ```
9. Check `YOUR-CLOUD/v1/info` → `"authorized": true` with the bot channel's name.

### If something goes wrong

| Error | Fix |
|---|---|
| `redirect_uri_mismatch` | The URI in the client doesn't exactly match the one used (https, domain, path, slash at the end). |
| "Access blocked: app is being tested" | Add the account as a test user, or publish the app. |
| "Google hasn't verified this app" | Expected until verification. Click Advanced/Continue. |
| `invalid_grant` after about a week | The project was still in Testing. Publish it and sign in again. |
| Publish fails | Fill in every Branding field, remove the logo, use a real domain you own. |
| `quotaExceeded` | 10k units a day, resets at midnight Pacific. Ask for more under YouTube Data API v3 → Quotas. |
| Bot can't act | The bot account has no channel, or the streamer hasn't added it as a moderator. |

---

## 5. Own domain

The Worker pages use relative links, so they work on any domain automatically.

1. Add the domain to Cloudflare. Then go to **Workers → chatvoice-cloud → Settings → Domains & Routes → Add custom domain**.
2. Verify the domain in Google Search Console (DNS TXT record in Cloudflare).
3. Update the Branding URLs and authorized domain. Add both redirect URIs on the domain:
   - `/platform-auth/youtube/callback`
   - `/v1/oauth/callback`
4. Code: point `CLOUD_URL` and `YT_BOT_URL` in `app/config.py` at the domain. Move saved `workers.dev` addresses over in `app/settings.py`, the same way `OLD_YT_BOT_URLS` handled Render.

Legal pages (`cloud/src/legal-pages.js`, edited 2026-11-02) now include:
- Limited Use statement
- links to the YouTube Terms of Service, Google Privacy Policy and User Data Policy
- scope uses and how to revoke access
- moderator bot data handling
- "agree to be bound by the YouTube Terms of Service" in the terms

**Not claimed yet:** "YouTube API data is refreshed or deleted within 30 days" (a YouTube API rule). Check the code does this before submitting for verification.

---

## 6. Free VPS: Oracle Cloud Always Free

Only needed for the Discord green dot, or a future bot that has to stay connected all the time. Everything else stays on the Worker.

- **What you get:** Ampere A1 (ARM, up to 4 CPUs / 24 GB) or AMD `VM.Standard.E2.1.Micro`. Needs a card for identity checks. Only choose "Always Free eligible" shapes.
- **Home region:** can't be changed later (Mumbai or Hyderabad). If A1 says "out of capacity", retry later or use E2.1.Micro.
- **Idle servers:** Oracle can take back Always Free servers that stay nearly idle. Upgrading to Pay As You Go (Always Free stays free) plus a small budget alert avoids this.
- **Setup:**
  1. Create an Ubuntu instance and download the SSH key.
  2. `ssh -i key ubuntu@PUBLIC_IP`
  3. Follow `HOSTING.txt` PART 3 A (Node 22 + `chatdoom-presence` systemd service).
  4. Check with `sudo journalctl -u chatdoom-presence -f`.
- **If Oracle rejects the card:** Google Cloud e2-micro (US regions), or a home PC/Raspberry Pi running `presence.mjs` from Task Scheduler "At startup".

---

## 7. Still to do

- [ ] Fix whatever is blocking Google "Publish" (get the exact error message).
- [ ] Create the dedicated bot Google account + channel, sign it in, update `YT_BOT_HANDLE` / guides / tests.
- [ ] Buy and attach a domain, then update `CLOUD_URL`, `YT_BOT_URL` and the address migration.
- [ ] Build **bot replies**: use the streamer's login when signed in, otherwise the bot, with a daily cap per channel.
- [ ] Build **Kick login** (check Kick's current developer API docs first).
- [ ] Check the 30-day YouTube data refresh/delete rule before verification.
- [ ] Optional: one-command install script for the Oracle server.
- [ ] Optional: proper landing page (screenshots, features, download button).
- [ ] Commit + `npx wrangler deploy` the `legal-pages.js` changes (not committed yet).
