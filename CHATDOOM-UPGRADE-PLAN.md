# CHATDOOM upgrade plan (for AI coding in VS Code)

> **How to use this file:** put it in the root of the ChatDoom project (next to `main.py`).
> In your VS Code AI chat, attach this file and say:
> *"Read CHATDOOM-UPGRADE-PLAN.md. Do Task 1 only. Run the tests. Then stop and show me the changes."*
> Do one task per chat. Don't ask for everything at once.

Written 12 Nov 2026 from a review of `Deba-dev/ChatDoom` at commit `c6aa439` (v1.4.5).

---

## 0. Project facts the AI must know

- **App:** Windows desktop app, Python 3.12 + PySide6. Entry: `main.py`, code in `app/`.
- **Cloud:** Cloudflare Worker in `cloud/src/` (Discord roles, tips, YouTube mod bot, platform OAuth, Workers AI for translation).
- **Chat sources:** `app/platforms.py`
  - YouTube uses `pytchat` (no login).
  - Twitch uses anonymous IRC.
  - Kick uses the unofficial Pusher WebSocket.
- **Moderation (what gets read aloud):** `app/moderation.py`, `Moderator.check(m)`, called from `app/ui.py` `on_message()` (around line 1913).
- **Speech:** `app/speech.py`, `Speaker._format_spoken()`. The default format is `"{name}: {message}"`, so **the username is spoken**.
- **Settings defaults:** `app/settings.py`
- **Tests:**
  - App: `set APPDATA=<empty folder>` `QT_QPA_PLATFORM=offscreen` `PYTHONPATH=.` then `python tests\test_app.py`
  - Cloud: `cd cloud` then `node test.mjs` (also `test-youtube-bot.mjs`, `test-support.mjs`, `test-tips.mjs`)
- **Version lives in 3 places:** `app/version.py`, `installer.iss`, `version_info.txt`. The GitHub workflow rewrites all three when you push a tag like `v1.4.6`.

### Rules for the AI
1. Make small, focused changes. Don't reformat or rename things you weren't asked to touch.
2. Every task adds tests in `tests/test_app.py` (app) or `cloud/test.mjs` (cloud), and all old tests must still pass.
3. **YouTube policy:** YouTube viewers must never earn points, XP, roles or giveaway entries (the code already enforces this, so keep it).
4. Keep Windows 10 support and the "Lite mode / low CPU" promise. No heavy new dependencies in the desktop app without asking.
5. Code comments are plain English and short, matching the existing style.
6. Never commit secrets. Cloud secrets go through `npx wrangler secret put`.

---

## Task 1: Fix the 4 stale cloud tests (5 minutes)

**Problem:** `POST /api/grant` in `cloud/src/index.js` (around line 648) correctly refuses YouTube viewers. But the test helper in `cloud/test.mjs` (around line 219) defaults to `platform = "youtube"`, so 4 tests fail:
- regular role granted
- supporter role granted
- unlinked viewer
- 403 reported

**Do:**
- Change the helper default to `"twitch"`. The test data must have a linked `twitch:UC1` viewer, so add that link where the YouTube link is set up.
- Add one new test: granting a role to a YouTube viewer returns 403 with the "YouTube rules" message.

**Done when:** `node test.mjs` shows no FAILED lines.

---

## Task 2: Filter usernames, not only messages

**Problem:** `Moderator.check()` only checks `m.text` against blocked words. The name is still spoken, so an abusive username gets read aloud on stream.

**Do:**
- In `Moderator.check()`, also check `m.author` with the same blocked-word logic. This includes the improved matching from Task 3, once that's done.
- Add the setting `"blocked_name_action"` with values `"anonymous"` (default) or `"skip"`.
  - `anonymous`: read the message but replace the name with "Ek viewer" (English mode: "A viewer"). The feed shows the reason "blocked name".
  - `skip`: don't read the message at all. Reason: "blocked name".
- Mask the name the same way in the OBS chat overlay.
- Add a dropdown for it on the Moderation page.

**Tests:** blocked username + clean message → spoken text doesn't contain the name. With `skip`, nothing is spoken.

---

## Task 3: Blocked words that can't be dodged

**Problem:** `_blocked_hit()` only matches exact words. Viewers dodge it with tricks like these:

| Trick | Example |
|---|---|
| Dots or spaces between letters | `b.c`, `b c`, `b-c` |
| Repeated letters | `bhennnnn` |
| Leetspeak | `bh3n`, `ch0d` |
| Lookalike Unicode | `ʙᴄ`, fullwidth letters, zalgo marks |
| Mixed scripts | Devanagari and Roman spelling of the same word |

**Do:** create `app/wordguard.py` with a function `canonical(text) -> str` that runs these steps in order:
1. NFKC Unicode normalization, then remove combining marks (zalgo).
2. Lowercase. Map common lookalikes to Latin, e.g. the small-caps letters and Cyrillic `а е о р с х`.
3. Leetspeak map: `0→o 1→i 3→e 4→a 5→s 7→t @→a $→s`.
4. Squeeze any letter repeated 3+ times down to 1.
5. Make a "joined" version with all non-letters removed, used to catch `b.c` / `b c`.

**Matching:**
- Check each blocked word against both the word-boundary version and the joined version.
- Join only short runs (single letters separated by symbols) so normal sentences don't false-match. For example, "abc deal" must not match "bcd".
- Add an **allow list** file `allowed_words.txt`, checked first, so words like "class" or "assassin" never get blocked.

**Word list:**
- Don't hardcode slurs in source code.
- Ship an optional starter list as a separate file the streamer can turn on ("Use ZunimiLabs Hindi/Hinglish starter list").
- Public lists to review before building it: the `cleanword` npm package (Hindi plus other Indian languages) and `LDNOOBW` (English). Check each list's license before shipping it.

**Tests:** each trick in the table above gets caught. Normal Hinglish sentences from `hinglish_words.txt` do **not** get blocked (run all of them as a false-positive check).

---

## Task 4: Hate-raid shield (auto safe mode)

**Problem:** A raid of new accounts can flood the TTS with abuse faster than mods can react.

**Do:** add `app/raidguard.py`. It watches the last 30 seconds of chat. It turns safe mode ON when either of these happens:
- At least `raid_new_chatters` (default 15) first-time chatters appear, **or**
- At least 8 near-identical messages arrive (same canonical text from Task 3).

**While safe mode is on:**
- `read_mode` temporarily becomes `"paid"` (or mods-only if the streamer picks that).
- Links are always skipped.
- A toast "Safe mode ON (raid detected)" appears, plus an optional Discord webhook message.

**Turning off:** automatically after `raid_cooldown_min` (default 3) quiet minutes, or with a hotkey or button. **Always restore the streamer's original settings.**

**Where:** settings go on the Moderation page. Use the existing `seen_ever` / `seen_stream` in `app/tools.py` to spot first-time chatters.

**Tests:** simulate 20 new chatters in 10 seconds → safe mode turns on. After the cooldown, the original `read_mode` comes back.

---

## Task 5: A YouTube reader that won't die with pytchat

**Problem:** `pytchat` (pinned 0.5.5) was archived by its author in January 2022. The next YouTube change will break it, and no one will fix it.

**Do:** refactor `YouTubeSource` in `app/platforms.py` to try several readers with automatic failover:

**Reader A (default, no login): our own InnerTube poller**, in a new `app/yt_innertube.py`.
1. Load `https://www.youtube.com/live_chat?v=<id>`.
2. Pull `ytInitialData` and the first continuation token.
3. Poll the `youtubei/v1/live_chat/get_live_chat` endpoint and wait the timeout YouTube returns each time.
4. Parse these renderers:
   - `liveChatTextMessageRenderer`
   - `liveChatPaidMessageRenderer` (Super Chat)
   - `liveChatPaidStickerRenderer`
   - `liveChatMembershipItemRenderer`
   - gifted memberships
5. Keep the existing `youtube_text()` emoji/emote handling.
6. Return the same `Message` objects as today.

**Reader B (optional, official): YouTube Data API `liveChatMessages.streamList`.**
- A gRPC server-streaming call that pushes messages over one long connection.
- Costs 5 quota units per call, and accepts an API key or OAuth token.
- Get the `liveChatId` from `videos.list` → `liveStreamingDetails.activeLiveChatId`.
- Save `nextPageToken` so a reconnect doesn't replay old messages.
- Needs `grpcio` (adds size to the exe). Only use it when the streamer is logged in with YouTube, because the app's API quota is shared across all users.

**Reader C (last resort):** the current `pytchat` code, unchanged.

**Failover rule:** if a reader fails 3 times in a row, or gets no messages for 90 seconds while the stream is live, switch to the next reader. Log which reader is active, and show it on the Connect page ("YouTube: Reader A").

**Tests:** parser tests using saved JSON samples in `tests/fixtures/yt_*.json` (one of each renderer type). No internet needed in tests.

---

## Task 6: Kick through its official API (keep Pusher as backup)

**Problem:** The Kick reader uses a hardcoded Pusher key, and the manual "paste chatroom ID" workaround. Kick's public API docs describe Pusher as unofficial and recommend the `chat.message.sent` webhook for production.

**Do:**

**Cloud side** (`cloud/src/`): add a `POST /kick/webhook` route.
- Verify Kick's signature: fetch the public key from `GET https://api.kick.com/public/v1/public-key`, cache it, and re-fetch if verification fails.
- Dedupe by the `Kick-Event-Message-Id` header (delivery is at-least-once).
- Store messages per streamer for a short time (KV or D1, like tips), and let the app poll them the same way it polls `/api/events`.

**App side:**
- When the streamer is logged in with Kick (OAuth already exists in `app/platform_auth.py`), subscribe to `chat.message.sent` for their channel and read from the cloud.
- If that fails or they aren't logged in, use the current Pusher reader.

**Note:** Kick automatically unsubscribes a webhook that keeps failing, so re-subscribe on every Connect.

**Tests:** cloud tests for signature OK / bad signature / duplicate message ID.

---

## Task 7: Viewer memory cards

**Idea:** When a returning viewer chats, a small **private** card shows on the streamer's screen only (never on the OBS overlay). For example:
> *Rahul: 23rd stream · first seen 4 Aug · note: "exam on Monday"*

**Do:**
- `viewers.json` currently stores only keys. Migrate it to `{key: {name, first_seen, streams, messages, last_seen, note}}`, keeping the old format readable.
- Count streams once per stream (use the existing `seen_stream`).
- Right-click a name in the Live chat feed → "Add note".
- Show the card for at most 1 viewer every 10 seconds.
- Setting on the Stream tools page: show for "regulars only (5+ streams)" or "everyone returning".
- Only store what the streamer types or what's public in chat. Add a "Forget this viewer" button.

**Tests:** migration from the old file, stream counting, and the card limit.

---

## Task 8: Facebook Live chat (new platform)

- Meta's Live Video API streams live comments as Server-Sent Events from `https://streaming-graph.facebook.com/{live-video-id}/live_comments?access_token=...`.
- Normal comments come from `graph.facebook.com/{live-video-id}/comments`.
- It needs a Page access token, so add Facebook to the platform login in `cloud/src/platform-auth.js`, the same way YouTube and Twitch work today.
- Meta requires the Page (or professional profile) to have at least 100 followers to go live through the API, so mention this in the UI.
- Add `FacebookSource` in `app/platforms.py` returning normal `Message` objects (`platform="facebook"`). Add a Facebook box on the Connect page.

---

## Task 9: AI check for paid messages (optional)

- Paid messages (Super Chat, tips, bits) are the ones abusers pay to get read aloud.
- Before reading a paid message, call a new cloud route `POST /api/check-text`. It uses the Workers AI binding the cloud already has, with a small instruction model.
- The model answers only `ok` or `block`.
- Timeout is 1.5 seconds. If the check is slow or fails, fall back to Tasks 2–3 only, so a tip is never delayed for long.
- Show blocked tips in the feed so the streamer can still thank the person without it being read aloud.

---

## Release checklist (after each task)
1. All app and cloud tests pass.
2. Add a line to `UPDATING.txt` or the changelog.
3. Bump the version (e.g. `v1.4.6`), push the tag, and let GitHub Actions build `CHATDOOM-Setup.exe`.
4. Test the built exe once on a real stream before announcing.

## Sources used for this plan
- pytchat archived: https://github.com/taizan-hokuto/pytchat
- YouTube streamList: https://developers.google.com/youtube/v3/live/docs/liveChatMessages/streamList and https://developers.google.com/youtube/v3/live/streaming-live-chat
- Kick public API, webhooks, and Pusher being unofficial: https://docs.kick.com (summarised at https://skills.sh/goncy/skills/kick-api)
- Facebook live comments (SSE): https://developers.facebook.com/docs/live-video-api/interact-with-viewers
- Facebook Live API requirements: https://developers.facebook.com/docs/live-video-api/overview
- Hindi/Indian-language abuse list (npm `cleanword`): https://www.npmjs.com/package/cleanword
