CHATDOOM YOUTUBE MODERATOR BOT  (for the person who runs CHATDOOM - streamers never see this)

One YouTube channel ("Chat Voice", @ChatVoice-V1) acts as the moderator bot. Each streamer adds that channel as a
moderator of their own channel (manual step, shown inside the CHATDOOM app). The bot then removes messages.

TWO WAYS TO USE IT
A) APP-DRIVEN  (recommended, works on a FREE host)             -> the /v1/... API, used by the CHATDOOM app
   CHATDOOM reads the chat itself (free, no YouTube quota) and asks the bot only to remove a message.
   Cost to the shared YouTube quota: 1 unit to look + 50 to delete. It only works while the streamer's CHATDOOM
   is open and connected to their live chat. The streamer proves the channel is theirs by typing a code
   in their own live chat; the server then gives the app a signed token. Nothing is stored on the server for that,
   so a sleeping/restarting free host loses nothing.
B) SERVER-POLLING  (optional; the original MVP, the /api/... + /admin pages)
   The server itself polls each registered stream. It works without the streamer's PC, like Nightbot, but it uses
   quota all the time (about 700+ units an hour per live stream) and it needs a disk to keep its settings.
   Needs a paid always-on host. Not needed for the CHATDOOM app.

FREE SETUP ON RENDER  (what you have now)
 1. Google Cloud: YouTube Data API v3 enabled, OAuth consent screen, a "Web application" OAuth client.
    Click "Publish app" on the consent screen (it stays "unverified", which is fine: only the bot account signs in).
    If it stays in "Testing", Google may expire the bot's login after about 7 days.
 2. Render > your service > Environment. Set:
        GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET   from Google Cloud (reset the secret if it was ever shared)
        BOT_ADMIN_KEY      a long random private value (32+ characters). It also signs the streamers' tokens.
        PUBLIC_URL         https://YOUR-SERVICE.onrender.com   (no trailing slash)
        SHOW_REFRESH_TOKEN 1          (temporary, see step 4)
    Optional: BOT_HANDLE=@ChatVoice-V1 and BOT_TITLE=CHATDOOM Moderator (shown in the app if YouTube cannot be asked).
 3. Google Cloud > the OAuth client > Authorized redirect URI:  https://YOUR-SERVICE.onrender.com/oauth/callback
 4. Open https://YOUR-SERVICE.onrender.com/admin , enter BOT_ADMIN_KEY, press "Authorize bot Google account" and sign
    in as the bot's Google account. The next page shows the bot's login code ONCE. Copy it into a NEW Render
    variable named BOT_REFRESH_TOKEN, then DELETE the SHOW_REFRESH_TOKEN variable and redeploy.
    (A free Render service has no permanent disk, so the login has to live in an environment variable.
    Treat it like a password.)
 5. Check https://YOUR-SERVICE.onrender.com/v1/info : it should say "authorized": true and show the bot's name.
 6. In the CHATDOOM project, app/config.py has YT_BOT_URL. Put your Render address there before building the installer.

FREE HOSTING HAS A CATCH
 - A free Render service goes to sleep after about 15 minutes without visits, and the first request after that waits
   up to ~50 seconds. CHATDOOM handles it: it wakes the bot when you open the YouTube mod page and keeps it awake
   (a visit every 8 minutes) while you are connected to YouTube. The status badge shows "Waking up..." meanwhile.
 - Everything the bot needs to remember is either in environment variables (its login) or in the streamers' own
   apps (their token, their rules). The daily counters live in memory and restart from zero after a restart; YouTube's
   own quota still protects you. 

OTHER WAYS TO BUILD AND HOST THIS BOT  (honest options)
 1. What you did - one bot channel that streamers add as a moderator. Simple for streamers, no Google sign-in for them,
    and no Google verification needed. Good for 10 friends and beyond.
 2. Nightbot style - each streamer signs in with their own Google account and authorizes the app. Nothing to add as a
    moderator, but Google requires app verification once more than ~100 people use it. Much heavier.
 3. Hosting: (a) Render Free as above, $0, sleeps; (b) Render paid, always on with a disk, enables mode B;
    (c) Cloudflare Workers - free, never sleeps, keeps data in KV; it is where the Discord part already lives, so the
    bot's "hands" can move there later and Render can be switched off; (d) Railway, Koyeb, Fly - trial credits or a card
    may be needed, check current terms; (e) a spare PC or Raspberry Pi at home - free, only runs while it is on.
 4. YouTube quota is the real limit: 10,000 units a day for the whole Google project. Mode A keeps you far from it.
    For many streamers using mode B you would need to apply to Google for more.

API USED BY THE APP  (all JSON)
   GET  /v1/info             bot name/handle, whether it is logged in. Also wakes a sleeping host.
   POST /v1/verify/start     {videoId}  -> {code}        the streamer types the code in their own live chat
   POST /v1/verify/check     {videoId}  -> {token}       proof the channel is theirs; token valid 90 days
   POST /v1/moderate         Bearer token; {videoId, items:[{channelId, author, text, reason, action}], dryRun, limit}
        action "delete" (default) or "timeout" with seconds (10..3600). Moderators and the streamer are never touched.
        A streamer can only act on streams of the channel they verified. Daily cap per streamer: 150 (default asked: 60).

SERVER-POLLING MODE (B) - SETUP AND LIMITS
   Needs a persistent disk mounted at /data (render.yaml uses the paid Starter plan with a 1 GB disk) and DATA_DIR=/data.
   Register a test stream from /admin with JSON like:
       {"channelId":"UC...","videoId":"...","blockedWords":["word"],"deleteLinks":true,"deleteSpam":false,"dryRun":true,"dailyLimit":60}
   Test mode ("dryRun") is on for every new stream. The service caps itself at 8,000 API units per Pacific Time day.
   All /api endpoints need the private bearer key BOT_ADMIN_KEY. DELETE /api/streams/CHANNEL_ID removes a stream.

SECURITY
 - Never put secrets in the repository, screenshots or chat. Reset the Google client secret if it was shared.
 - Signed tokens use BOT_ADMIN_KEY. If you change it, every streamer has to verify again (a one-minute job).
 - The server only accepts moderation for a video that belongs to the channel in the token.

LOCAL TESTS
   npm test        (11 checks with a simulated YouTube)
