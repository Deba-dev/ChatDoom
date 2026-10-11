CHATDOOM (BETA)  -  Phase 5  -  v0.5.0
Created by itsmeblitz
Reads YouTube, Twitch and Kick chat aloud in Hindi / Hinglish / English, with moderation, Discord roles,
payment alerts from the streamer's own payment page (Razorpay, Stripe, Cashfree or any tool), YouTube message deleting,
OBS overlays (alerts and chat on screen) and one-click self-updates.

WHAT IS INSIDE
  main.py, app\           the Windows app (Python + PySide6)
  cloud\                  the free Cloudflare server (Discord roles, payment webhook)
  youtube-bot\            the hosted YouTube moderator bot (Node; runs free on Render)
  assets\                 CHATDOOM logo, app icon and the Poppins font
  tests\                  automatic checks (node test.mjs for the cloud, python tests\test_app.py for the app)
  CLOUD-SETUP.txt         one-time cloud + Discord setup (you, once)
  PAYMENTS-SETUP.txt      Razorpay payment page and webhook
  YT-MODERATION-SETUP.txt add the bot to your channel and verify it (streamers) + how it is run
  youtube-bot\README.txt  deploy the bot, free hosting, other hosting options
  GITHUB-BUILD-GUIDE.txt  turn the project into CHATDOOM-Setup.exe, free
  UPDATING.txt            publish a new version; users update with one click
  OBS-GUIDE.txt           voice, alerts, chat and now-playing in OBS
  MUSIC-GUIDE.txt         StreamBeats downloads/imports, licenses and OBS music setup

PAGES IN THE APP
  Connect     paste your YouTube link and channel names, press Connect; optional YouTube/Twitch login enables chat messages and polls
  Live chat   combined feed; grey lines were skipped by moderation
  Voice       voices, speed, volume, multilingual chat translation, all-chat / paid-only reading modes
  Moderation  what gets read aloud: link / command / bot / repeat filters, blocked words
  Discord     one click to add the bot, one click to make roles and invite links; the rest is under Advanced
  Payments    payment alerts (Razorpay / Stripe / Cashfree / any tool) plus a shareable quick tip link
  YouTube mod add the ChatVoice bot to your channel, verify it is yours, choose the rules (like Nightbot)
  OBS overlays  alerts for tips, YouTube public subscribers/members, and Twitch follows/subs/raids, with multiple looks
  Music       browse StreamBeats music and Mixkit sound effects in-app, download/import them, and use local files
  Sidebar     Theme (4 colour themes) and Lite mode (turns off glow/fade animations for weak PCs or gaming)

RUN IT (easiest)
1. Install Python 3.12 from python.org.
2. Double-click run.bat   (installs the libraries the first time, then opens the app)

GET A REAL CHATDOOM-Setup.exe  (free, no command window when it runs)
Your friends only run the finished Setup.exe. They never need Python or any command line.
Option 1 - build it in the cloud, nothing to install on your PC:
  1. Make a free GitHub account, create a repository, upload everything from this folder.
  2. Open the "Actions" tab > "Build CHATDOOM" > "Run workflow".
  3. When it finishes (about 5-10 minutes), download "CHATDOOM-Setup" from the run page.
  (Public repositories get unlimited free build minutes; private ones get a monthly allowance.)
Option 2 - build it on your PC: install Python 3.12 and the free Inno Setup 6 (jrsoftware.org),
  then double-click build.bat. You get installer\CHATDOOM-Setup.exe.

ABOUT WINDOWS WARNINGS AND GAMES
- A new unsigned app shows "Windows protected your PC": click "More info" > "Run anyway". Removing this
  needs a paid code-signing certificate; free signing exists only for open-source projects.
- Some antivirus programs wrongly flag apps made this way. The build keeps the app as a folder (not one
  big file) which reduces this. You can report a false alarm to Microsoft Defender.
- While running, CHATDOOM has no console window, runs at below-normal CPU priority so games and OBS
  always come first, and it does not hook into games.

USING IT
- Connect: paste your YouTube live link, Twitch channel, Kick channel. Press Connect.
- Kick: if it says "Kick blocked the lookup", open  https://kick.com/api/v2/channels/YOURNAME  in a browser,
  find  "chatroom":{"id":NUMBER  and paste that number in the box under the Kick channel.
- Voice: voices, speed, volume. Unicode emoji and named emotes are spoken by name; known bots are skipped by default.
- Moderation: link / command / bot / repeat filters and your own blocked-words list (what gets READ).
- Discord: invite roles, automatic YouTube live announcements with a thumbnail, and customizable title/message templates.
  Needs the one-time cloud setup: see CLOUD-SETUP.txt.

USING IT WITH OBS
CHATDOOM is a normal window that plays sound on your PC. To put the voice on your stream:
1. Start CHATDOOM BEFORE you go live and keep it running (minimised is fine).
2. In OBS: Sources > + > "Application Audio Capture", pick the CHATDOOM window.
   (Needs Windows 10 version 2004+ and OBS 28 or newer. If it is missing, add "Audio Output Capture" instead,
   or just rely on "Desktop Audio".) If you started it with run.bat, the app may show as python.exe.
3. In the OBS audio mixer you can now raise or lower the voice separately from your game and mic.
4. USE HEADPHONES. With speakers, your microphone picks the voice up again and viewers hear an echo.
5. To show the chat on screen: Sources > + > "Window Capture" > CHATDOOM, then open its "Live chat" page.

FILES THE APP KEEPS  (%APPDATA%\ChatVoice)
settings.json, hinglish_words.txt (add short forms: short=how to say it), blocked_words.txt

NOTES
- Neural voices need internet. If they fail, the app falls back to Windows voices.
- Chat reading is anonymous; YouTube automatically retries after a chat connection drops. Kick uses its
  unofficial chat connection and remains read-only. YouTube/Twitch login enables sending chat messages and creating polls.
- Platform sign-in needs the one-time OAuth setup in CLOUD-SETUP.txt. YouTube API quota is shared by all users of the app.
- YouTube moderation still uses the separate ChatVoice moderator bot; login does not make the app a platform moderator.
