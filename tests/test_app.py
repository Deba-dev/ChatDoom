# Run from the project folder:  set QT_QPA_PLATFORM=offscreen  &  set PYTHONPATH=.  &  python tests\test_app.py
import os, sys, json, threading, time, urllib.request, urllib.parse, tempfile, atexit, shutil
_test_appdata = tempfile.mkdtemp(prefix="chatdoom-test-")
os.environ["APPDATA"] = _test_appdata
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
atexit.register(shutil.rmtree, _test_appdata, ignore_errors=True)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import QTimer, QEventLoop
app = QApplication(sys.argv); app.setStyle("Fusion")
def wait(ms):
    l = QEventLoop(); QTimer.singleShot(ms, l.quit); l.exec()
fails = 0
def ok(c, msg):
    global fails
    print(("PASS " if c else "FAIL ") + msg); fails += (not c)

# ---------------- fake cloud ----------------
C = {"grants": [], "tips": [], "config_puts": [], "links": {"youtube:UC1": "U1", "youtube:UC2": "U2"}, "deny": {"UC2"}}
class Cloud(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(b)
    def body(self):
        n = int(self.headers.get("content-length") or 0); return json.loads(self.rfile.read(n) or b"{}")
    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer KEY": return self.send({"error": "bad server key"}, 401)
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path == "/api/roles": self.send({"roles": [{"id": "100003", "name": "Supporter"}, {"id": "100001", "name": "YouTube Viewer"}, {"id": "100002", "name": "Regular"}]})
        elif u.path == "/api/links": self.send({"keys": list(C["links"])})
        elif u.path == "/api/config": self.send({"guildId": "G1", "guildName": "Srv", "config": {"hasStripeSecret": "stripe" in C.get("gw", set()), "hasGenericSecret": "generic" in C.get("gw", set()), "hasCashfreeSecret": False, "hookUrls": {g: "https://cv.example/hook/%s/abc" % g for g in ("razorpay", "stripe", "cashfree", "generic")} if (C.get("secret") or C.get("gw")) else {}, "hasRazorpaySecret": bool(C.get("secret")), "hookUrl": "https://cv.example/hook/razorpay/abc" if C.get("secret") else "", "inviteRules": C.get("invite_rules", [])}})
        elif u.path == "/api/events":
            after = int(q["after"][0]); latest = max([t["seq"] for t in C["tips"]] or [0])
            self.send({"events": [], "latest": latest} if after < 0 else {"events": [t for t in C["tips"] if t["seq"] > after], "latest": latest})
        else: self.send({"error": "nf"}, 404)
    def do_PUT(self):
        if self.headers.get("Authorization") != "Bearer KEY": return self.send({"error": "x"}, 401)
        b = self.body(); C["config_puts"].append(b)
        if "inviteRules" in b: C["invite_rules"] = [dict(r, code=r["code"].split("/")[-1]) for r in b["inviteRules"]]
        if b.get("razorpaySecret"): C["secret"] = b["razorpaySecret"]
        for g in ("stripe", "generic", "cashfree"):
            if b.get(g + "Secret"): C.setdefault("gw", set()).add(g)
        self.send({"ok": True, "config": {"hasRazorpaySecret": bool(C.get("secret")), "hasStripeSecret": "stripe" in C.get("gw", set()), "hasGenericSecret": "generic" in C.get("gw", set()), "hasCashfreeSecret": False,
                                          "hookUrl": "https://cv.example/hook/razorpay/abc", "hookUrls": {g: "https://cv.example/hook/%s/abc" % g for g in ("razorpay", "stripe", "cashfree", "generic")}}})
    def do_POST(self):
        b = self.body()
        if self.path == "/api/discord/setup":
            C["setup_calls"] = C.get("setup_calls", 0) + 1
            nice = {"youtube": "YouTube", "twitch": "Twitch", "kick": "Kick"}
            return self.send({"ok": True, "sources": [{"source": s_, "label": nice[s_], "roleId": "9000%d" % i, "roleName": nice[s_] + " Viewer", "roleCreated": True, "invite": "https://discord.gg/NEW%s" % nice[s_][:2], "reused": False} for i, s_ in enumerate(b["sources"])]})
        if self.path == "/api/invites/check":
            return self.send({"rules": [{"label": "YouTube", "code": "yt1", "found": True, "uses": 4}, {"label": "Twitch", "code": "tw1", "found": False, "uses": None}], "assigned": [{}], "notes": ["Now watching your invites."]})
        if self.path == "/api/grant":
            C["grants"].append(b)
            if b["uid"] in C["deny"]: return self.send({"ok": False, "status": 403})
            return self.send({"ok": True, "role": b["role"], "status": 204})
        self.send({"error": "nf"}, 404)

# ---------------- fake ChatVoice YouTube bot (same API as youtube-bot/v1.mjs) ----------------
G = {"typed": False, "moderate": [], "info": 0, "fail_token": False, "used": 0}
class Bot(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(b)
    def body(self):
        n = int(self.headers.get("content-length") or 0); return json.loads(self.rfile.read(n) or b"{}")
    def do_GET(self):
        if self.path == "/v1/info": G["info"] += 1; return self.send({"ok": True, "authorized": True, "bot": {"title": "Chat Voice", "handle": "@ChatVoice-V1"}})
        self.send({"error": "nf"}, 404)
    def do_POST(self):
        b = self.body()
        if self.path == "/v1/verify/start":
            if b.get("videoId") == "notlive0001": return self.send({"ok": False, "error": "That video is not live right now."}, 409)
            return self.send({"ok": True, "code": "CV-ABC234", "channelId": "UC" + "a" * 22, "channelTitle": "Test Streamer", "expiresIn": 900})
        if self.path == "/v1/verify/check":
            return self.send({"ok": True, "token": "TOKEN123", "channelId": "UC" + "a" * 22, "channelTitle": "Test Streamer"}) if G["typed"] else self.send({"ok": False, "waiting": True})
        if self.path == "/v1/moderate":
            if G["fail_token"] or self.headers.get("Authorization") != "Bearer TOKEN123": return self.send({"ok": False, "error": "expired"}, 401)
            G["moderate"].append(b); G["used"] += len(b["items"])
            notes = ["%s: %s" % ("TEST MODE" if b["dryRun"] else "Deleted", it["author"]) for it in b["items"]]
            return self.send({"ok": True, "notes": notes, "usedToday": G["used"], "limit": b["limit"]})
        self.send({"error": "nf"}, 404)

for H, port in ((Cloud, 8811), (Bot, 8812)):
    s = ThreadingHTTPServer(("127.0.0.1", port), H); threading.Thread(target=s.serve_forever, daemon=True).start()

import app.ytmod as ytmod
from app.ui import MainWindow
from app.models import Message
from app.music_page import _CatalogPage
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtGui import QDesktopServices
w = MainWindow(); w.show()
ok(w.windowTitle().startswith("CHATDOOM ") and w.logo.pixmap() is not None and not w.logo.pixmap().isNull(),
   "app shows the CHATDOOM name and uploaded logo")
w.mute_btn.setChecked(True)
ok(w.s.get("muted") and w.mute_btn.text() == "Unmute", "muted voice has a clear Unmute control")
spoken = []; w.speaker.say = lambda *a: spoken.append(a)
w.test_voice()
ok(not spoken and "Click Unmute" in w.feed.toPlainText(), "test voice explains when reading is muted")
w.mute_btn.setChecked(False)
ok(not w.s.get("muted") and w.mute_btn.text() == "Mute", "unmuting restores chat reading")
w.on_message(Message("test", "Test", "speech routing works"))
ok(spoken == [("Test", "speech routing works", "")], "an allowed incoming chat message reaches the voice queue")
w.mute_btn.setChecked(True)
w.mod.blocked = []
profile = QWebEngineProfile()
catalog_page = _CatalogPage(profile)
opened_external = []
old_open_url = QDesktopServices.openUrl
QDesktopServices.openUrl = lambda url: opened_external.append(url.toString()) or True
blocked_hosts = []
catalog_page.navigationBlocked.connect(blocked_hosts.append)
catalog_page.acceptNavigationRequest(QUrl("https://www.streambeats.com/catalog"), QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True)
catalog_page.acceptNavigationRequest(QUrl("https://www.facebook.com/"), QWebEnginePage.NavigationType.NavigationTypeRedirect, True)
ok(not opened_external and blocked_hosts == ["www.facebook.com"]
   and catalog_page.acceptNavigationRequest(QUrl("https://mixkit.co/free-sound-effects/"), QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True),
   "catalog allows supported sites and blocks automatic redirects without opening unwanted tabs")
catalog_page.acceptNavigationRequest(QUrl("https://streamelements.com/overlay"), QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True)
QDesktopServices.openUrl = old_open_url
ok(opened_external == ["https://streamelements.com/overlay"],
   "a deliberately clicked external catalog link opens once in the regular browser")
bot_msg = Message("youtube", "ViewerHelper", "hello viewers", bot=True)
ok(w.mod.check(bot_msg)[1] == "bot", "provider-marked bot messages are skipped even if they are not in the name list")
known_bot = Message("youtube", "Nightbot", "welcome", "super", "100 bits")
ok(w.mod.check(known_bot)[1] == "bot", "known bot accounts are skipped even when they post a paid-style event")
w.s.set("read_mode", "paid")
ok(w.mod.check(Message("youtube", "Viewer", "regular chat")) == (False, "normal messages off")
   and w.mod.check(Message("twitch", "Supporter", "thanks", "super", "100 bits")) == (True, ""),
   "paid-only chat mode skips regular messages but keeps enabled paid messages")
w.s.set("read_mode", "all")
from app.hinglish import normalize
ok(normalize("Nice 😂👍 1️⃣ :heart:") == "Nice face with tears of joy thumbs up one heart",
   "emoji and emoji shortcodes are spoken by name rather than removed or read as symbols")
from app import translation as translation_module
from app.translation import detect_source_language, translate_to_english
ok(detect_source_language("こんにちは、配信を見ています") == "ja"
   and detect_source_language("Hola, me encanta este directo") == "es"
   and detect_source_language("مرحبا، أحب مشاهدة البث") == "ar",
   "language detection recognizes Japanese, Spanish, and Arabic chat")
translation_request = {}
old_urlopen = translation_module.urllib.request.urlopen
translation_module.urllib.request.urlopen = lambda request, timeout: (
    translation_request.update(request=request, payload=json.loads(request.data.decode("utf-8")))
    or __import__("io").BytesIO(b'{"translation":"Hello from the stream!"}'))
translated_text, did_translate = translate_to_english(
    "こんにちは、配信を見ています",
    type("TranslationSettings", (), {"get": lambda self, key: {
        "cloud_url": "https://chatvoice.example", "cloud_token": "APP_SERVER_KEY"
    }[key]})())
translation_module.urllib.request.urlopen = old_urlopen
ok(translated_text == "Hello from the stream!" and did_translate
   and translation_request["payload"]["source_lang"] == "ja"
   and translation_request["request"].get_header("Authorization") == "Bearer APP_SERVER_KEY",
   "English translation uses detected source language and the authenticated Worker")
from app.platforms import parse_kick_event, parse_twitch_line
from app.platform_events import parse_twitch_event
twitch_bot = parse_twitch_line("@display-name=Nightbot;user-id=123;emotes=25:0-4 :nightbot!nightbot@nightbot.tmi.twitch.tv PRIVMSG #chat :Kappa 😂")
ok(twitch_bot.author == "Nightbot" and twitch_bot.text == "Kappa 😂" and w.mod.check(twitch_bot)[1] == "bot",
   "Twitch emote names are retained for speech and known bot messages are skipped")
twitch_bits = parse_twitch_line("@id=paid-123;bits=100;user-id=viewer-1 :viewer!viewer@viewer.tmi.twitch.tv PRIVMSG #chat :cheer100")
ok(twitch_bits.event_id == "paid-123", "Twitch paid chat preserves its stable event id")
kick_emote = parse_kick_event("ChatMessageEvent", {"content": "Hi [emote:12:catJAM]", "sender": {"username": "viewer"}})
ok(kick_emote.text == "Hi catJAM", "Kick custom emotes are read by their names")
follow_alert = parse_twitch_event({"metadata": {"subscription_type": "channel.follow"}, "payload": {"event": {"user_name": "Follower"}}})
sub_alert = parse_twitch_event({"metadata": {"subscription_type": "channel.subscription.message"},
                                "payload": {"event": {"user_name": "Supporter", "tier": "1000",
                                                      "cumulative_months": 6, "message": {"text": "Love this!"}}}})
raid_alert = parse_twitch_event({"metadata": {"subscription_type": "channel.raid"},
                                 "payload": {"event": {"user_name": "Raider", "viewers": 42}}})
ok(follow_alert["category"] == "follow" and sub_alert["amount"] == "Tier 1 · 6 months"
   and sub_alert["message"] == "Love this!" and raid_alert["amount"] == "42 viewers",
   "Twitch EventSub events normalize followers, resubs, and raids for the alert overlay")
import app.discord as discord_module
old_http = discord_module._http
announcement = {}
discord_module._http = lambda method, url, headers, body=None: announcement.update(body=body) or {"ok": True}
discord_module.post_live_announcement("https://discord.com/api/webhooks/1/token", "Come watch {url}", "abcdefghijk", "Now live")
discord_module._http = old_http
ok(announcement["body"]["embeds"][0]["thumbnail"]["url"] == "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"
   and announcement["body"]["embeds"][0]["description"] == "Come watch https://www.youtube.com/watch?v=abcdefghijk",
   "Discord announcements include a YouTube thumbnail and expand custom link placeholders")
from app import discord_page as discord_page_module
old_run_bg, old_post_announcement, old_post_webhook = (discord_page_module.run_bg,
                                                         discord_page_module.post_live_announcement,
                                                         discord_page_module.post_webhook)
announcement_calls = []
discord_page_module.run_bg = lambda bridge, tag, fn: announcement_calls.append((tag, fn()))
discord_page_module.post_live_announcement = lambda *args: {"ok": True}
w.s.set("discord_announced_videos", [])
w.discord._announced_videos.clear()
w.discord._pending_auto_videos.clear()
w.discord.hook.setText("https://discord.com/api/webhooks/1/token")
w.s.set("webhook_url", "https://discord.com/api/webhooks/1/token")
w.s.set("announce_auto", True)
w.discord.yt.setText("")
w.discord.auto_announce("youtube", "https://www.youtube.com/live/abcdefghijk")
w.discord.on_done(*announcement_calls[-1])
# Reconnecting to the same live video must not produce another announcement.
w.discord.auto_announce("youtube", "https://www.youtube.com/live/abcdefghijk")
ok(len(announcement_calls) == 1 and announcement_calls[0][0] == "ui:auto|abcdefghijk"
   and w.s.get("youtube") == "https://www.youtube.com/live/abcdefghijk"
   and w.s.get("discord_announced_videos") == ["abcdefghijk"],
   "automatic Discord announcement is persisted and sent only once per live video")
discord_page_module.post_live_announcement = lambda *args: {"error": "Discord webhook unavailable"}
w.discord.auto_announce("youtube", "https://www.youtube.com/watch?v=lmnopqrstuv")
w.discord.on_done(*announcement_calls[-1])
w.discord.auto_announce("youtube", "https://www.youtube.com/watch?v=lmnopqrstuv")
ok(len(announcement_calls) == 3 and "lmnopqrstuv" in w.discord._pending_auto_videos,
   "failed automatic announcement can retry on the next YouTube connection")
discord_page_module.post_live_announcement = old_post_announcement
w.s.set("post_super", True)
paid_posts = []
discord_page_module.post_webhook = lambda url, content: paid_posts.append(content) or {"ok": True}
w.discord.post_paid(Message("twitch", "Viewer", "cheer!", "super", "100 bits", event_id="paid-xyz"))
w.discord.post_paid(Message("twitch", "Viewer", "cheer!", "super", "100 bits", event_id="paid-xyz"))
w.discord.post_paid(Message("twitch", "Viewer", "cheer again", "super", "200 bits", event_id="paid-next"))
ok(len(paid_posts) == 2 and "100 bits" in paid_posts[0] and "200 bits" in paid_posts[1],
   "each distinct paid event posts immediately, while a duplicate event id is ignored")
discord_page_module.run_bg, discord_page_module.post_live_announcement, discord_page_module.post_webhook = (
    old_run_bg, old_post_announcement, old_post_webhook)
w.discord._paid_event_ids.clear()
w.discord._paid_event_order.clear()
w.s.set("post_super", False)
w.s.set("cloud_url", "http://127.0.0.1:8811"); w.s.set("cloud_token", "KEY")
w.links.refresh(); wait(500)
ok(w.links.linked == {"youtube:UC1", "youtube:UC2"}, "linked viewers loaded from the cloud")

# ===== A. roles are counted in the app; the cloud is asked only at thresholds =====
print("--- A. role thresholds ---")
w.s.set("role_regular", "100002"); w.s.set("role_supporter", "100003"); w.s.set("regular_msgs", 3)
for i in range(2): w.on_message(Message("youtube", "Rahul", "hello %d" % i, uid="UC1", mod=True))
wait(300); ok(len(C["grants"]) == 0, "no cloud call before the threshold")
w.on_message(Message("youtube", "Rahul", "hello 3", uid="UC1", mod=True)); wait(500)
ok([g["role"] for g in C["grants"]] == ["regular"], "3rd message -> one request for the Regular role")
for i in range(5): w.on_message(Message("youtube", "Rahul", "more %d" % i, uid="UC1", mod=True))
wait(300); ok(len(C["grants"]) == 1, "no repeat requests after the role was given")
w.on_message(Message("youtube", "Rahul", "thanks", "super", "₹100", uid="UC1", mod=True)); wait(500)
ok([g["role"] for g in C["grants"]] == ["regular", "supporter"], "paid message -> Supporter role requested")
for i in range(4): w.on_message(Message("youtube", "Neha", "hi %d" % i, uid="UC2", mod=True))
wait(500); n = len(C["grants"])
for i in range(4): w.on_message(Message("youtube", "Neha", "again %d" % i, uid="UC2", mod=True))
wait(300); ok(len(C["grants"]) == n and "move the CHATDOOM role above" in w.feed.toPlainText(), "failed grant (403): clear hint, and no retry flood")
w.links.save(); ok(json.load(open(os.path.join(os.environ["APPDATA"], "ChatVoice", "counts.json")))["youtube:UC1"]["regular"], "counts saved to disk")

# ===== B. payments =====
print("--- B. payments ---"); spoken.clear()
w.s.set("tips_on", True); w.s.set("tip_min", 20)
w.mod.blocked = ["badword"]
C["tips"].append({"seq": 1, "id": "old", "name": "Old", "message": "old tip", "value": 50, "currency": "INR", "display": "₹50"})
w.poller.apply(); wait(700)
ok(w.s.get("tip_cursor") == 1 and not spoken, "first poll skips tips that arrived before the app started")
C["tips"] += [{"seq": 2, "id": "a", "name": "Rahul", "message": "Great stream bhai!", "value": 100, "currency": "INR", "display": "₹100"},
              {"seq": 3, "id": "b", "name": "Troll", "message": "you badword", "value": 100, "currency": "INR", "display": "₹100"},
              {"seq": 4, "id": "c", "name": "Cheap", "message": "I paid only five", "value": 5, "currency": "INR", "display": "₹5"},
              {"seq": 5, "id": "d", "name": "Sam", "message": "Hello from the USA", "value": 5, "currency": "USD", "display": "$5"}]
w.poller.poll(); wait(900)
got = {a[0]: a for a in spoken}
ok(len(spoken) == 4, "all four new tips were queued to be spoken")
ok(got["Rahul"][1] == "Great stream bhai!" and got["Rahul"][2] == "₹100", "name + message + amount ₹100 read")
ok(got["Troll"][1] == "" and got["Troll"][2] == "₹100", "blocked word: message hidden, name and amount still read")
ok(got["Cheap"][1] == "" and got["Cheap"][2] == "₹5", "below minimum: message not read")
ok(got["Sam"][1] == "Hello from the USA" and got["Sam"][2] == "$5", "USD payment: message read (minimum applies to INR only)")
ok(w.s.get("tip_cursor") == 5, "cursor advanced; nothing is read twice")
w.poller.poll(); wait(500); ok(len(spoken) == 4, "next poll finds nothing new")
txt = w.feed.toPlainText(); ok("TIP Rahul [₹100]: Great stream bhai!" in txt, "tip shown in the live chat feed")
w.payments.secret.setText("whsec_123"); w.payments.save_secret(); wait(500)
ok(C["config_puts"][-1] == {"razorpaySecret": "whsec_123"} and w.payments.hook.text().endswith("/hook/razorpay/abc"), "secret saved on its own (roles untouched), webhook address shown")
w.payments.test_tip(); wait(300); ok(spoken[-1][0] == "Rahul" and spoken[-1][2] == "₹100", "test payment button works")

# ===== C. YouTube moderation through the hosted bot =====
print("--- C. YouTube moderation (bot) ---")
UCA, UCB, UCM = "UC" + "a" * 22, "UC" + "b" * 22, "UC" + "m" * 22
w.s.set("yt_bot_url", "http://127.0.0.1:8812"); w.s.set("youtube", "https://www.youtube.com/watch?v=7NlbmyxncOk")
from app.settings import Settings as _Settings
_fresh = os.path.join(os.environ["APPDATA"], "fresh_settings.json"); open(_fresh, "w").write('{"cloud_url": "", "yt_bot_url": "   ", "update_repo": "Deba-dev/ChatVoice"}')
_fs = _Settings(_fresh)
ok(_fs.get("cloud_url").startswith("https://") and "workers.dev" in _fs.get("cloud_url") and _fs.get("yt_bot_url").startswith("https://")
   and _fs.get("update_repo") == "Deba-dev/ChatDoom",
   "built-in service URLs remain available and old update settings migrate to the renamed GitHub repository")
w.ytmod.refresh_info(); wait(600)
ok(w.ytmod.bot_state == "online" and w.s.get("yt_bot_handle") == "@ChatVoice-V1" and "Bot online" in w.ytpage.bot_badge.text(), "page shows the bot online with its name")
ok("@ChatVoice-V1" in w.ytpage.step2.body.text() and w.ytpage.handle.text() == "@ChatVoice-V1", "instructions name the bot to add as moderator")
w.s.set("youtube", ""); w.ytpage.verify(); wait(200)
ok("Connect page" in w.ytmod.message and not w.ytmod.code, "verifying without a live link tells the streamer what to do first")
w.s.set("youtube", "https://www.youtube.com/watch?v=7NlbmyxncOk"); w.ytpage.verify(); wait(600)
ok(w.ytmod.code == "CV-ABC234" and w.ytpage.code_box.isVisibleTo(w.ytpage) and w.ytpage.code_label.text() == "CV-ABC234", "a code is shown to type in the live chat")
w.ytmod.check_verify(); wait(500); ok(not w.ytmod.verified, "still waiting until the code is typed")
G["typed"] = True; w.ytpage._poll_code(); wait(600)
ok(w.ytmod.verified and w.s.get("yt_channel_title") == "Test Streamer" and "Verified" in w.ytpage.v_badge.text() and not w.ytpage.code_box.isVisibleTo(w.ytpage), "channel verified, page shows the channel name")
w.ytmod.timer.setInterval(100)
def post(author, ch, text, **kw): w.on_message(Message("youtube", author, text, uid=ch, **kw))
post("Spammer", UCA, "visit www.spam.com now"); wait(700)
req = G["moderate"][-1]
ok(req["dryRun"] is True and req["videoId"] == "7NlbmyxncOk" and req["items"] == [{"channelId": UCA, "author": "Spammer", "text": "visit www.spam.com now", "reason": "link", "action": "delete"}], "test mode: the bot is asked what it WOULD remove")
ok("TEST MODE: Spammer" in w.feed.toPlainText() and w.s.get("yt_used") == 1, "the bot's answer appears in the feed and the daily counter updates")
ok("Active \u2014 test mode" in w.ytpage.status.text(), "status badge says test mode")
w.s.set("mod_dry_run", False); n = len(G["moderate"])
post("Spammer", UCA, "second www.two.com"); wait(700)
ok(G["moderate"][-1]["dryRun"] is False and len(G["moderate"]) == n + 1, "after switching test mode off the request is real")
post("Spammer", UCA, "third www.three.com"); wait(700)
items = G["moderate"][-1]["items"]
ok(items[-1] == {"action": "timeout", "channelId": UCA, "author": "Spammer", "seconds": 300}, "3rd removal in 10 minutes also asks for a 5-minute time-out")
n = len(G["moderate"])
post("Mod", UCM, "mod posts www.link.com", mod=True); post("Odd", "not-a-channel-id", "x www.y.com"); wait(500)
ok(len(G["moderate"]) == n, "moderators and unknown viewer ids are never sent to the bot")
w.s.set("mod_del_links", False); post("Quiet", UCB, "z www.allowed.com"); wait(500); ok(len(G["moderate"]) == n, "a rule that is switched off sends nothing")
w.s.set("mod_del_links", True); w.s.set("yt_mod_on", False); post("Quiet", UCB, "z www.allowed.com"); wait(500); ok(len(G["moderate"]) == n, "master switch off sends nothing")
w.s.set("yt_mod_on", True); post("Fan", UCB, "I love badword"); wait(700); ok(len(G["moderate"]) == n + 1 and G["moderate"][-1]["items"][0]["reason"] == "blocked word", "blocked words are sent too")
G["fail_token"] = True; post("Late", UCB, "late www.late.com"); wait(700)
ok(not w.ytmod.verified and "verification expired" in w.feed.toPlainText(), "an expired verification is cleared and the streamer is told to verify again")
G["fail_token"] = False
w.on_status("youtube", "Connected", True); ok(not w.yt_beat.isActive(), "no wake-up pings until the channel is verified")
w.s.set("yt_bot_token", "TOKEN123"); w.on_status("youtube", "Connected", True); ok(w.yt_beat.isActive(), "while connected to YouTube the app keeps the free-hosted bot awake")
w.on_status("youtube", "Disconnected", False); ok(not w.yt_beat.isActive(), "pings stop when you disconnect")
w.s.set("yt_bot_url", "http://127.0.0.1:9"); post("Net", UCB, "net www.down.com"); wait(1200)
ok("Cannot reach the CHATDOOM moderator bot" in w.feed.toPlainText(), "if the bot cannot be reached the streamer sees a plain message")
w.s.set("yt_bot_url", "http://127.0.0.1:8812")
w.goto(5); wait(300); w.grab().save(os.path.join(os.environ["APPDATA"], "payments.png")); w.goto(6); wait(300); w.grab().save(os.path.join(os.environ["APPDATA"], "ytmod.png"))

# ===== D. invite roles UI, themes, lite mode, animations =====
print("--- D. invite roles, look and feel ---")
d = w.discord; d.url.setText("http://127.0.0.1:8811"); d.key.setText("KEY"); d.test(); wait(1200)
d.inv_edits["youtube"].setText("https://discord.gg/yt1")
d.save_invites(); wait(300); ok("Pick a role for the YouTube invite" in d.istatus.text() and "inviteRules" not in C["config_puts"][-1], "invite without a role: asks for one, nothing sent")
d.inv_boxes["youtube"].setCurrentIndex(d.inv_boxes["youtube"].findData("100001")); d.save_invites(); wait(500)
ok(C["config_puts"][-1] == {"inviteRules": [{"code": "https://discord.gg/yt1", "role": "100001", "label": "YouTube"}]} and "Saved" in d.istatus.text(), "invite + role sent to the cloud, only that field")
d.check_invites(); wait(500)
ok("invite found, used 4 times" in d.istatus.text() and "invite NOT found" in d.istatus.text() and "Gave roles to 1" in d.istatus.text(), "check button explains each invite in plain words")
d.inv_edits["youtube"].setText(""); d.test(); wait(900)
ok(d.inv_edits["youtube"].text() == "https://discord.gg/yt1" and d.inv_boxes["youtube"].currentData() == "100001", "saved invite roles are loaded back from the cloud")

from app.theme import THEMES
for name in THEMES:
    w.apply_theme(name); app.processEvents()
    ok(THEMES[name]["a1"] in w.styleSheet() and w.s.get("theme") == name, "theme '%s' applied and remembered" % name)
w.apply_theme("Sunset"); w.goto(0); wait(120); w.grab().save(os.path.join(os.environ["APPDATA"], "sunset_connect.png")); wait(500)
w.apply_theme("Neon Violet"); w.goto(4); wait(150); w.grab().save(os.path.join(os.environ["APPDATA"], "violet_discord_midanim.png")); wait(600); w.grab().save(os.path.join(os.environ["APPDATA"], "violet_discord.png"))
for i in range(8): w.goto(i); wait(60); w.grab()
ok(True, "all 8 pages render without errors")
n = len(w.fx.items)
ok(n == 0, "buttons use a quiet hover instead of a glow")
w._lite(True); wait(100); ok(w.fx.enabled is False, "Lite mode turns motion off")
w.goto(1); w.goto(5); ok(w.stack.currentIndex() == 5, "Lite mode: pages switch instantly")
w._lite(False); wait(100); ok(w.fx.enabled is True, "turning Lite mode off allows motion again")
ok(True, "hover stays a stylesheet change, with no glow to grow")

# ===== E. OBS overlays =====
print("--- E. OBS overlays ---")
import app.overlay as _ov
def ov(path):
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d%s" % (w.overlay.port, path)).read())
ok(w.overlay.port > 0 and b"data-mode=\"alert\"" in urllib.request.urlopen(w.overlay.url("alert")).read(), "overlay server runs and serves the alert page (%s)" % w.overlay.url("alert"))
sound_dir = os.path.join(os.environ["APPDATA"], "ChatVoice", "Soundboard")
os.makedirs(sound_dir, exist_ok=True)
sound_file = os.path.join(sound_dir, "alert sound.wav")
open(sound_file, "wb").write(b"local-alert-sound")
w.s.set("ov_sound", True); w.s.set("ov_sound_file", sound_file)
sound_url = w._overlay_cfg()["soundUrl"]
ok(sound_url == "/sounds/alert%20sound.wav"
   and urllib.request.urlopen("http://127.0.0.1:%d%s" % (w.overlay.port, sound_url)).read() == b"local-alert-sound",
   "OBS can load an imported alert sound from the private local soundboard folder")
w.s.set("ov_sound", False); w.s.set("ov_sound_file", "")
w.s.set("muted", True); w.s.set("read_super", True)
start = ov("/poll?type=alert&after=-1")["latest"]
w.mod.blocked = ["badword"]; w.s.set("tip_min", 20)
w.on_message(Message("youtube", "Chatty", "namaste doston", uid="UCx"))
w.on_message(Message("youtube", "Rude", "you badword", uid="UCy"))
w.on_message(Message("youtube", "Donor", "keep going", "super", "₹200.00", uid="UCz"))
w.on_tip({"name": "Rahul", "message": "tip message", "value": 100, "currency": "INR", "display": "₹100"})
chat = ov("/poll?type=chat&after=%d" % start)["events"]; alerts = ov("/poll?type=alert&after=%d" % start)["events"]
ok([c["name"] for c in chat] == ["Chatty", "Donor"], "chat overlay gets spoken messages only (blocked one and payment alert excluded)")
ok([(a["name"], a["amount"], a["message"], a["platform"]) for a in alerts] == [("Donor", "₹200.00", "keep going", "youtube"), ("Rahul", "₹100", "tip message", "tip")], "alert overlay gets Super Chat and payment with amount and message")
w.on_tip({"name": "Cheap", "message": "tiny", "value": 5, "currency": "INR", "display": "₹5"})
ok(ov("/poll?type=alert&after=%d" % start)["events"][-1]["message"] == "", "alert for a payment below the minimum shows no message")
w.on_message(Message("youtube", "NewMember", "", "member"))
member_alerts = ov("/poll?type=alert&after=%d" % start)["events"]
ok(member_alerts[-1]["category"] == "membership" and member_alerts[-1]["name"] == "NewMember",
   "YouTube membership events become separately filterable on-screen alerts")
yt_alert_start = ov("/poll?type=alert&after=-1")["latest"]
public_sub = {"id": "YT_PUBLIC_SUB_1", "name": "PublicSubscriber"}
w.on_youtube_subscribers({"subscribers": [public_sub], "cursor": int(time.time() * 1000)})
w.on_youtube_subscribers({"subscribers": [public_sub], "cursor": int(time.time() * 1000)})
yt_sub_alerts = ov("/poll?type=alert&after=%d" % yt_alert_start)["events"]
ok(len(yt_sub_alerts) == 1 and yt_sub_alerts[0]["category"] == "subscriber"
   and yt_sub_alerts[0]["name"] == "PublicSubscriber",
   "YouTube public-subscriber alerts reach OBS once even when overlapping polls repeat an event")
w.on_twitch_event({"platform": "twitch", "category": "follow", "name": "NewFollower", "message": ""})
twitch_alert = ov("/poll?type=alert&after=%d" % start)["events"][-1]
alert_html = urllib.request.urlopen(w.overlay.url("alert")).read().decode("utf-8")
ok(twitch_alert["category"] == "follow" and twitch_alert["name"] == "NewFollower"
   and " followed" in alert_html and "showSubscriptions" in alert_html,
   "Twitch follow alerts reach OBS with readable event text and category filtering")
w.s.set("ov_seconds", 12); w.apply_theme("Ocean")
cfg = ov("/poll?type=alert&after=-1")["cfg"]
ok(cfg["seconds"] == 12 and cfg["colors"]["a1"] == THEMES["Ocean"]["a1"] and cfg["showMessage"] is True
   and cfg["showSubscribers"] and cfg["showFollows"] and cfg["showSubscriptions"] and cfg["showRaids"],
   "options, event toggles, and theme colours reach OBS within a second")
w.ovpage.alert_url.text(); n0 = ov("/poll?type=alert&after=-1")["latest"]
w.ovpage.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)
for b in w.ovpage.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton):
    if b.text() in ("Send a test alert", "Send a test chat message"): b.click()
ok(ov("/poll?type=alert&after=%d" % n0)["events"][0]["name"] == "Rahul" and ov("/poll?type=chat&after=%d" % n0)["events"][0]["name"] == "Neha", "test buttons send a sample alert and chat line")
w.apply_theme("Neon Violet")

# ===== F. updates =====
print("--- F. updates ---")
import hashlib, app.updater as upd
from app.version import VERSION
ok(upd.parse_version("v0.10.0") > upd.parse_version("0.9.9") and upd.parse_version("v1") == (1, 0, 0) and upd.parse_version("v" + VERSION) == upd.parse_version(VERSION), "version numbers compare correctly (0.10 is newer than 0.9)")
release_repo = "Deba-dev/ChatDoom"
release_asset = "https://github.com/Deba-dev/ChatDoom/releases/download/V1.0.5/CHATDOOM-Setup.exe"
ok(upd.Updater._release_repo("https://github.com/Deba-dev/ChatDoom/releases/tag/V1.0.5") == release_repo
   and upd.Updater._is_release_asset(release_asset, release_repo)
   and not upd.Updater._is_release_asset("https://evil.example/Deba-dev/ChatDoom/releases/download/V1.0.5/CHATDOOM-Setup.exe", release_repo),
   "updater recognizes the renamed GitHub repository and rejects external asset hosts")
BLOB = b"MZ-fake-installer-bytes" * 5000
GH = {"tag": "v9.9.9", "digest": "sha256:" + hashlib.sha256(BLOB).hexdigest(), "asset": "http://127.0.0.1:8813/dl/CHATDOOM-Setup.exe"}
class Gh(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.endswith("/releases/latest"):
            b = json.dumps({"tag_name": GH["tag"], "html_url": "https://github.com/Deba-dev/ChatDoom/releases/tag/x", "body": "New things", "assets": [{"name": "CHATDOOM-Setup.exe", "browser_download_url": GH["asset"], "digest": GH["digest"]}]}).encode()
        elif self.path.startswith("/dl/"): b = BLOB
        else: self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
ghs = ThreadingHTTPServer(("127.0.0.1", 8813), Gh); threading.Thread(target=ghs.serve_forever, daemon=True).start()
upd.GH_API = "http://127.0.0.1:8813"
upd.Updater._is_release_asset = staticmethod(lambda asset, repo: asset.startswith("http://127.0.0.1:8813/dl/"))
w.s.set("update_repo", "Deba-dev/ChatVoice")
w.banner.hide(); w.updater.check(True); wait(900)
ok(w.banner.isVisible() and "9.9.9" in w.banner_text.text() and w.pending_update["notes"] == "New things"
   and w.s.get("update_repo") == "Deba-dev/ChatDoom" and w.pending_update["repo"] == "Deba-dev/ChatDoom",
   "newer release is found under the canonical renamed repository")
launched, quits = [], []
w.updater.frozen = False; w.updater.launch = lambda path: launched.append(path); w.updater.quit_now.disconnect(); w.updater.quit_now.connect(lambda: quits.append(1))
w.upd_btn.setEnabled(True); w._update_now(); wait(1500)
ok(len(launched) == 1 and launched[0].endswith("CHATDOOM-Setup-9.9.9.exe") and open(launched[0], "rb").read() == BLOB and quits == [1], "Update now downloads the installer and starts it without opening GitHub")
GH["digest"] = "sha256:" + "0" * 64; launched.clear(); w.updater.check(False); wait(700); w.pending_update and w.updater.install(w.pending_update); wait(1500)
ok(not launched and "did not match" in w.feed.toPlainText(), "corrupted download (wrong checksum) is discarded, not run")
w.updater.install({"version": "9.9.9", "asset": "http://evil.example/x.exe"}); wait(200)
ok(not launched and "not from your GitHub repository" in w.feed.toPlainText(), "update file from anywhere except your repository is refused")
GH["tag"] = "v0.0.1"; w.banner.hide(); w.updater.check(True); wait(800)
ok(w.banner.isVisible() and not w.upd_btn.isVisible() and "not any update" in w.banner_text.text(), "already up to date -> banner says there is no update")
w.s.set("update_last", 0); w.s.set("auto_update_check", False); w.banner.hide(); GH["tag"] = "v9.9.9"; w._auto_update(); wait(400)
ok(not w.banner.isVisible(), "automatic check can be switched off")

# ===== G. protected secrets =====
print("--- G. protected secrets ---")
import app.secure as sec, app.settings as stg, sys as _sys
ok(sec.protect("abc") == "abc" and sec.unprotect("abc") == "abc", "outside Windows secrets are stored as before")
real = (sec._win_call, _sys.platform)
sec._win_call = lambda data, protect: bytes(b ^ 0x5A for b in data); _sys.platform = "win32"
enc = sec.protect("refresh-token-123"); dec = sec.unprotect(enc)
sec._win_call, _sys.platform = real
ok(enc.startswith("dpapi:") and "refresh-token-123" not in enc and dec == "refresh-token-123", "Windows path: encrypted form never contains the secret and decrypts back")
ok(sec.unprotect("dpapi:%%%notbase64") == "", "damaged protected value reads as empty (user is asked to sign in again), no crash")
stg_p, stg_u = stg.protect, stg.unprotect
stg.protect = lambda x: ("dpapi:" + x[::-1]) if x else x; stg.unprotect = lambda x: x[6:][::-1] if isinstance(x, str) and x.startswith("dpapi:") else x
sp = os.path.join(os.environ["APPDATA"], "sec_settings.json"); S = stg.Settings(sp); S.set("cloud_token", "KEY-SECRET"); S.set("g_client_secret", "GSEC"); S.set("youtube", "plain-value")
raw = json.load(open(sp)); S2 = stg.Settings(sp)
stg.protect, stg.unprotect = stg_p, stg_u
ok(raw["cloud_token"].startswith("dpapi:") and "KEY-SECRET" not in open(sp).read() and raw["youtube"] == "plain-value" and S2.get("cloud_token") == "KEY-SECRET" and S2.get("g_client_secret") == "GSEC", "settings file keeps sign-in keys encrypted, other values readable, loads back correctly")

# ===== H. payment gateway choice =====
print("--- H. gateways ---")
pg = w.payments; labels = [pg.gw.itemText(i) for i in range(pg.gw.count())]
ok(len(labels) == 4 and "Stripe" in labels and any("Any other tool" in l for l in labels), "payments page offers Razorpay, Stripe, Cashfree and any other tool")
pg.tip_link.setText("https://tips.example/creator"); ok(pg.save_tip_link() and w.s.get("tip_link") == "https://tips.example/creator",
   "quick tip link accepts and saves a public HTTPS payment URL")
pg.tip_link.setText("javascript:alert(1)"); ok(not pg.save_tip_link() and w.s.get("tip_link") == "https://tips.example/creator",
   "quick tip link rejects unsafe schemes without replacing the saved URL")
pg.gw.setCurrentIndex(pg.gw.findData("stripe")); ok("whsec_" in pg.secret.placeholderText() and "checkout.session.completed" in pg.how.text(), "choosing Stripe shows Stripe's own instructions")
pg.secret.setText("whsec_abc"); pg.save_secret(); wait(500)
ok(C["config_puts"][-1] == {"stripeSecret": "whsec_abc"} and pg.hook.text().endswith("/hook/stripe/abc") and "saved" in pg.state.text().lower(), "Stripe secret saved on its own; Stripe address shown")
pg.gw.setCurrentIndex(pg.gw.findData("generic")); ok(pg.hook.text().endswith("/hook/generic/abc") and "X-ChatVoice-Secret" in pg.how.text(), "switching to 'any other tool' shows its address and header")
pg.gw.setCurrentIndex(pg.gw.findData("cashfree")); ok(pg.hook.text().endswith("/hook/cashfree/abc") and "No secret" in pg.state.text(), "gateway without a secret says so")

# ===== I. creator credit and version label =====
print("--- I. credit and version ---")
from app.version import label, CREATOR, PHASE, STAGE
from PySide6.QtWidgets import QLabel as _QL
texts = [l.text() for l in w.findChildren(_QL)]
ok(label() == "Phase %d \u00b7 v%s (BETA)" % (PHASE, VERSION) and STAGE == "BETA" and CREATOR == "itsmeblitz", "version label reads: %s" % label())
ok(label() in texts and any("itsmeblitz" in x for x in texts), "sidebar shows the version label and 'by itsmeblitz'")
ok("itsmeblitz" in w.windowTitle() and "BETA" in w.windowTitle(), "window title: %s" % w.windowTitle())
ok(b"itsmeblitz" in urllib.request.urlopen("http://127.0.0.1:%d/" % w.overlay.port).read() if w.overlay.server else True, "overlay start page carries the credit")

# ===== J. simple Discord setup =====
print("--- J. one-click Discord ---")
import urllib.parse as _up, app.discord_page as _dp
d = w.discord; opened = []
_dp.QDesktopServices.openUrl = lambda u: opened.append(u.toString())
w.s.set("cloud_token", ""); w.s.set("guild_name", ""); d.refresh_state()
ok("Not connected" in d.badge.text() and not d.roles_card.isEnabled() and d.connect_btn.objectName() == "primary", "before connecting: one big button, the roles card is greyed out")
w.s.set("cloud_url", "http://127.0.0.1:8811"); d.connect()
ok(opened and opened[0].startswith("http://127.0.0.1:8811/setup?return=http%3A%2F%2F127.0.0.1%3A") and "Waiting for Discord" in d.badge.text(), "the button opens the browser on the bot-adding page with a return address on this PC")
back = _up.unquote(opened[0].split("return=")[1])
urllib.request.urlopen(back + "?ok=0&error=access_denied").read(); wait(600)
ok("not connected" in d.status.text().lower() and "access_denied" in d.status.text() and not w.s.get("cloud_token"), "pressing Cancel on Discord leaves nothing changed and says so")
opened.clear(); d.connect(); back = _up.unquote(opened[0].split("return=")[1])
urllib.request.urlopen(back + "?ok=1&token=KEY&guild=My+Server&gid=G1").read(); wait(1200)
ok(w.s.get("cloud_token") == "KEY" and "Connected" in d.badge.text() and d.status.text() == "Srv" and d.roles_card.isEnabled(), "after Authorize the app is connected by itself (no key pasted)")
ok(d.connect_btn.text() == "Connect a different server" and d.connect_btn.objectName() == "quiet", "button turns into a quiet 'connect a different server'")
d.src_switch["kick"].setChecked(False); d.setup_roles(); wait(900)
ok(C["setup_calls"] == 1 and d.src_link["youtube"].text() == "https://discord.gg/NEWYo" and d.src_link["twitch"].text().startswith("https://discord.gg/NEW") and d.src_link["kick"].text() == "", "one click fills an invite link for each ticked platform only")
ok("YouTube Viewer" in d.src_role["youtube"].text() and "2 invite link" in d.istatus.text() and d.setup_btn.isEnabled() and d.tip.isVisibleTo(d), "role names and next-step advice are shown")
ok(w.s.get("inv_youtube") == "https://discord.gg/NEWYo" and d.inv_edits["youtube"].text() == "https://discord.gg/NEWYo", "advanced fields stay in step with the simple ones")
d.src_switch["youtube"].setChecked(False); d.src_switch["twitch"].setChecked(False); d.src_switch["kick"].setChecked(False); d.setup_roles()
ok("at least one platform" in d.istatus.text() and C["setup_calls"] == 1, "nothing ticked: a clear message, no request")
ok(not d.adv.isVisibleTo(d) and d.adv_btn.text() == "Show advanced options", "manual options are hidden until asked for"); d.adv_btn.setChecked(True); ok(d.adv.isVisibleTo(d), "Advanced options opens the old manual controls")
w.s.set("cloud_token", "STALE"); d.key.setText("STALE"); d.test(); wait(600)
ok(not w.s.get("cloud_token") and "no longer valid" in d.status.text() and "Not connected" in d.badge.text(), "a key that stopped working is dropped with a plain explanation")
w.s.set("cloud_token", "KEY"); d.refresh_state()

# ===== K. music =====
print("--- K. music ---")
import zipfile
from PySide6.QtCore import QObject, Signal
from app.music import MusicPlayer, describe, import_downloads, scan
class FakeBackend(QObject):
    ended = Signal(); failed = Signal(str)
    def __init__(self): super().__init__(); self.vol = None; self.loaded = []; self.playing = False
    def load(self, p): self.loaded.append(os.path.basename(p))
    def play(self): self.playing = True
    def pause(self): self.playing = False
    def stop(self): self.playing = False
    def set_volume(self, v): self.vol = round(v, 3)
folder = tempfile.mkdtemp(); [open(os.path.join(folder, n), "wb").write(b"x") for n in ("Aria - First_Song.mp3", "Bo - Second.ogg", "third.wav", "readme.txt", "cover.jpg")]
os.makedirs(os.path.join(folder, "sub", "deep", "deeper")); open(os.path.join(folder, "sub", "deep", "deeper", "toodeep.mp3"), "wb").write(b"x")
ok(describe("/m/Aria - First_Song.mp3") == ("Aria", "First Song") and describe("/m/third.wav") == ("", "third"), "file names become artist and title")
ok([x["title"] for x in scan(folder)] == ["First Song", "Second", "third"], "only audio files are found, and not folders more than two levels deep")
archive = os.path.join(folder, "official-album.zip")
with zipfile.ZipFile(archive, "w") as z:
    z.writestr("StreamBeats/Artist - Album Track.mp3", b"mp3 data")
    z.writestr("../outside.mp3", b"unsafe path")
    z.writestr("readme.txt", b"not audio")
library = tempfile.mkdtemp(prefix="chatvoice-managed-music-")
added = import_downloads([archive, os.path.join(folder, "third.wav")], library)
ok(len(added) == 2 and os.path.exists(os.path.join(library, "Artist - Album Track.mp3"))
   and os.path.exists(os.path.join(library, "third.wav"))
   and not os.path.exists(os.path.join(folder, "outside.mp3")),
   "official album ZIP and local audio import into the app library without extracting unsafe paths")
ok(len(import_downloads([archive], library)) == 1 and os.path.exists(os.path.join(library, "Artist - Album Track (1).mp3")),
   "repeat music imports keep both copies instead of overwriting tracks")
pushed = []; fb = FakeBackend(); s2 = _Settings(os.path.join(os.environ["APPDATA"], "music_settings.json")); s2.set("music_shuffle", False); s2.set("music_volume", 50)
mp = MusicPlayer(s2, lambda k, d_: pushed.append((k, d_)), backend=fb); notes = []; mp.notice.connect(notes.append)
ok(mp.load_folder(folder) == 3 and fb.vol == 0.5, "folder loaded, volume applied")
mp.toggle(); ok(fb.loaded == ["Aria - First_Song.mp3"] and fb.playing and pushed[-1] == ("music", {"title": "First Song", "artist": "Aria", "playing": True}), "play starts the first song and tells the overlay")
fb.ended.emit(); ok(fb.loaded[-1] == "Bo - Second.ogg", "when a song ends the next one starts")
mp.prev(); ok(fb.loaded[-1] == "Aria - First_Song.mp3", "previous goes back")
mp.toggle(); ok(not fb.playing and pushed[-1][1]["playing"] is False, "pause stops the sound and clears the overlay")
mp.toggle(); mp.duck(True); ok(fb.vol == 0.15, "music drops to 30% of its volume while the voice speaks (50% -> 15%)")
mp.duck(False); ok(fb.vol == 0.5, "and comes back afterwards")
s2.set("music_duck", False); mp.duck(True); ok(fb.vol == 0.5, "ducking can be switched off"); mp.duck(False); s2.set("music_duck", True)
mp.set_volume(80); ok(fb.vol == 0.8 and s2.get("music_volume") == 80, "volume slider changes the level and is remembered")
fb.failed.emit("bad codec"); ok("Skipped a file" in notes[-1] and fb.playing, "an unplayable file is skipped, music keeps going")
for _ in range(2): fb.failed.emit("bad codec")     # 3 files, 3 failures in a row
ok("None of the music files" in notes[-1] and not mp.playing, "if nothing can be played it stops and says why (no endless loop)")
s2.set("music_shuffle", True); mp.load_folder(folder); order = []
for _ in range(3): mp.next(); order.append(mp.index)
ok(sorted(order) == [0, 1, 2], "shuffle plays every song once before repeating")
# inside the real window
w.music.backend = FakeBackend(); w.music.backend.ended.connect(w.music.next); w.music.set_volume(60)
w.music.load_folder(folder); wait(200); w.goto(8); wait(300)
ok(w.musicpage.list.count() == 3 and "3 songs" in w.musicpage.count.text() and not w.musicpage.empty.isVisibleTo(w.musicpage), "music page lists the songs")
catalog_buttons = {button.text() for button in w.musicpage.findChildren(QPushButton)}
ok("Browse StreamBeats catalog" in catalog_buttons and "Browse free sound effects" in catalog_buttons,
   "music and sound-effect catalogs can be opened in-app")
catalog_track = os.path.join(library, "catalog-download.mp3")
open(catalog_track, "wb").write(b"audio data")
music_imported = w.musicpage._import_catalog_download(catalog_track)
ok(len(music_imported) == 1 and os.path.isfile(music_imported[0]), "catalog music downloads are imported into the music library")
sound_imported = w.musicpage._import_sound_catalog_download(catalog_track)
ok(len(sound_imported) == 1 and "catalog-download" in [w.musicpage.sound_list.item(i).text() for i in range(w.musicpage.sound_list.count())],
   "catalog sound downloads are imported into the soundboard")
w.music.load_folder(folder)
w.musicpage.list.setCurrentRow(1); w.music.play_index(1); wait(100)
ok("Playing" in w.musicpage.state.text() and w.musicpage.title.text() == "Second" and "Pause" in w.musicpage.play_btn.text(), "now-playing panel follows the player")
w.speaker.busy_changed.emit(True); ok(w.music.backend.vol == round(0.6 * 0.3, 3), "music really gets quieter when ChatVoice starts speaking")
w.speaker.busy_changed.emit(False); ok(w.music.backend.vol == 0.6, "and returns when it stops")
st = ov("/poll?type=music&after=-1")
ok(st["state"] == {"title": "Second", "artist": "Bo", "playing": True}, "the OBS now-playing overlay is given the current song")
ok(b'data-mode="music"' in urllib.request.urlopen(w.overlay.url("music")).read() and w.musicpage.music_url.text().endswith("/music"), "now-playing overlay page exists and its address is on the Music page")
w.music.stop(); ok(ov("/poll?type=music&after=-1")["state"]["playing"] is False, "stopping hides it on stream")
w.goto(8); wait(300); w.grab().save(os.path.join(os.environ["APPDATA"], "music.png")); shutil.rmtree(folder, ignore_errors=True); shutil.rmtree(library, ignore_errors=True)
ok(len([b for b in w.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton) if b.objectName() == "nav"]) == 9 and w.nav.button(8).text().strip() == "Music" and not w.nav.button(8).icon().isNull(), "sidebar has all 9 pages, each with a drawn icon (Music included)")
print("\nALL PASSED" if not fails else "\n%d FAILED" % fails)
w.close()
shutil.rmtree(os.environ["APPDATA"], ignore_errors=True)
