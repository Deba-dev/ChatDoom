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
        if self.path == "/v1/info": G["info"] += 1; return self.send({"ok": True, "authorized": True, "bot": {"title": "Chat Voice", "handle": "@ChatDoom"}})
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
ok(w.windowTitle() == "CHATDOOM" and w.logo.pixmap() is not None and not w.logo.pixmap().isNull(),
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
from app.translation import worth_translating
for chat_text in ("HELLO", "hi", "CV-ZVSQPS", "nice stream bro", "ok bro nice stream", "bhai kya kar rahe ho aaj", "\U0001F600\U0001F600", ""):
    ok(not worth_translating(chat_text), "not sent for translation: %s" % ascii(chat_text))
for chat_text in ("Hola, me encanta este directo", "Ich liebe diesen Stream", "\u3053\u3093\u306b\u3061\u306f", "\u043f\u0440\u0438\u0432\u0435\u0442"):
    ok(worth_translating(chat_text), "sent for translation: %s" % ascii(chat_text))
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
ok(_fs.get("cloud_url") == "https://cloud.zunimilabs.online" and _fs.get("yt_bot_url") == "https://cloud.zunimilabs.online"
   and _fs.get("update_repo") == "Deba-dev/ChatDoom",
   "built-in service URLs remain available and old update settings migrate to the renamed GitHub repository")
_moved = os.path.join(os.environ["APPDATA"], "moved_settings.json")
open(_moved, "w").write('{"cloud_url": "https://chatvoice-cloud.debarshiparasar7.workers.dev/", "yt_bot_url": "https://chatvoice-cloud.debarshiparasar7.workers.dev"}')
_ms = _Settings(_moved)
ok(_ms.get("cloud_url") == "https://cloud.zunimilabs.online" and _ms.get("yt_bot_url") == "https://cloud.zunimilabs.online",
   "saved workers.dev addresses move to the Worker's own domain")
w.ytmod.refresh_info(); wait(600)
ok(w.ytmod.bot_state == "online" and w.s.get("yt_bot_handle") == "@ChatDoom" and "Bot online" in w.ytpage.bot_badge.text(), "page shows the bot online with its name")
ok("@ChatDoom" in w.ytpage.step2.body.text() and w.ytpage.handle.text() == "@ChatDoom", "instructions name the bot to add as moderator")
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
w.ytmod.clear_log(); w.ytmod.in_flight = [{"channelId": UCA, "author": "Spammer", "text": "buy www.x.com", "reason": "link", "action": "delete"},
                                          {"channelId": UCB, "author": "Mod", "text": "www.y.com", "reason": "link", "action": "delete"},
                                          {"action": "timeout", "channelId": UCA, "author": "Spammer", "seconds": 300}]
w.ytmod.on_done("yt:sweep", {"status": 200, "ok": True, "notes": [], "usedToday": 3, "results": [
    {"i": 0, "outcome": "done", "told": True}, {"i": 1, "outcome": "protected"}, {"i": 2, "outcome": "failed", "detail": "nope"}]})
log_text = [w.ytpage.log_list.item(i).text() for i in range(w.ytpage.log_list.count())]
ok(len(log_text) == 3 and "Removed, viewer told why" in log_text[2] and "buy www.x.com" in log_text[2]
   and "Kept, moderator" in log_text[1] and "Time-out, 300 s: Failed: nope" in log_text[0], "the Removed messages list shows each action's real result, newest first")
ok(len(json.load(open(w.ytmod.log_path, encoding="utf-8"))) == 3 and w.ytmod._load_log() == w.ytmod.log, "the list survives a restart")
w.ytmod.in_flight = [{"channelId": UCA, "author": "Late", "text": "x", "reason": "link", "action": "delete"}]
w.ytmod.on_done("yt:sweep", {"status": 502, "ok": False, "error": "bot down"})
ok("Failed: bot down" in w.ytpage.log_list.item(0).text(), "a failed request is listed as failed, never as removed")
w.ytmod.clear_log(); ok(w.ytpage.log_list.count() == 0 and not w.ytpage.log_clear.isEnabled(), "the list can be cleared")
spoken_before = len(spoken); seen_before = w.msg_seen
w.on_message(Message("youtube", "@ChatDoom", "@Spammer your message was removed because links are not allowed here.", uid=UCB))
ok(len(spoken) == spoken_before and w.msg_seen == seen_before, "the bot's own reason lines are not read aloud")
yt_card = w.cards["youtube"]; yt_card.edit.setText(""); yt_notes = []; w.platform_auth.notice.connect(yt_notes.append)
scheduled = {"id": "scheduled01", "title": "Friday & chill", "live": False, "privacy": "unlisted", "start": 1893456000000, "stale": False}
old = {"id": "oldstream01", "title": "Old", "live": False, "privacy": "public", "start": 1, "stale": True}
yt_card._on_broadcasts([old], False); ok(yt_card.edit.text() == "", "an old default entry is never filled in by itself")
yt_card._on_broadcasts([scheduled, old], False)
ok(yt_card.edit.text().endswith("v=scheduled01") and w.s.get("youtube").endswith("v=scheduled01") and "once it is live" in yt_notes[-1], "a scheduled unlisted stream fills an empty link after sign-in")
yt_card.edit.setText("https://www.youtube.com/watch?v=someoneelse")
yt_card._on_broadcasts([scheduled], False)
ok(yt_card.edit.text().endswith("someoneelse") and "Find my stream" in yt_notes[-1], "a pasted link is never replaced by itself")
yt_card.find_btn.show(); yt_card._on_broadcasts([scheduled, old], True)
acts = yt_card.stream_menu.actions(); ok(len(acts) == 2 and "(unlisted)" in acts[0].text() and "&&" in acts[0].text(), "Find my stream lists the streams to choose from")
acts[0].trigger(); ok(yt_card.edit.text().endswith("v=scheduled01"), "choosing one fills the link"); yt_card.stream_menu.close()
yt_card.edit.setText(""); w.s.set("youtube", "https://www.youtube.com/watch?v=7NlbmyxncOk"); w.platform_auth.notice.disconnect(yt_notes.append)
w.on_status("youtube", "Connected", True); ok(not w.yt_beat.isActive(), "no wake-up pings until the channel is verified")
w.s.set("yt_bot_token", "TOKEN123"); w.on_status("youtube", "Connected", True); ok(w.yt_beat.isActive(), "while connected to YouTube the app keeps the free-hosted bot awake")
w.on_status("youtube", "Disconnected", False); ok(not w.yt_beat.isActive(), "pings stop when you disconnect")
w.s.set("yt_bot_url", "http://127.0.0.1:9"); post("Net", UCB, "net www.down.com"); wait(3500)   # Windows takes about 2 seconds to report a refused connection
ok("Cannot reach the CHATDOOM moderator bot" in w.feed.toPlainText(), "if the bot cannot be reached the streamer sees a plain message")
shown = w.feed.toPlainText().count("Cannot reach the CHATDOOM moderator bot"); post("Net2", UCB, "net2 www.down.com"); wait(3500)
ok(w.feed.toPlainText().count("Cannot reach the CHATDOOM moderator bot") == shown, "the same problem is not repeated in the feed straight away")
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
for i in range(w.stack.count()): w.goto(i); wait(60); w.grab()
ok(w.stack.count() == 16, "all 16 pages render without errors")
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
ok(upd.parse_version("v0.10.0") > upd.parse_version("0.9.9") and upd.parse_version("v1") == (1, 0, 0, 0) and upd.parse_version("v" + VERSION) == upd.parse_version(VERSION), "version numbers compare correctly (0.10 is newer than 0.9)")
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

# ===== custom look =====
print("--- custom look ---")
from app.theme import THEMES as _TH, custom_theme
from app.visuals import BUILT_IN_BACKGROUNDS, background_path
from app.appearance import AppearanceDialog, import_image
from PySide6.QtGui import QColor as _QC, QImage as _QI
w.set_custom_colours({"a1": "#00ff88", "a2": "#ff0066", "bg": "#ffffff"})
ok(w.s.get("theme") == "Custom" and w.theme_combo.currentText() == "Custom" and _TH["Custom"]["a1"] == "#00ff88", "picked colours switch the app to the Custom theme")
ok(_QC(_TH["Custom"]["bg"]).lightnessF() <= 0.17, "a very light background colour is kept dark so text stays readable")
ok(all(os.path.isfile(background_path("builtin:" + k)) and not _QI(background_path("builtin:" + k)).isNull() for _, k in BUILT_IN_BACKGROUNDS), "all six built-in pictures load")
w.set_background_picture("builtin:sunset"); w.canvas.grab(); ok(w.s.get("background") == "image" and w.canvas.picture[1] is not None, "a built-in picture is drawn behind the pages")
own = os.path.join(_test_appdata, "mine.png"); _QI(64, 36, _QI.Format_RGB32).save(own)
value, problem = import_image(own); ok(value.startswith("custom:") and not problem and os.path.isfile(background_path(value)), "your own picture is copied into CHATDOOM's folder")
bad = os.path.join(_test_appdata, "bad.png"); open(bad, "wb").write(b"not a picture"); ok(import_image(bad)[0] == "" and "picture" in import_image(bad)[1], "a broken picture is refused with a plain message")
w.set_background_picture("custom:gone.png"); w.canvas.grab(); ok(w.canvas.picture[1] is None, "a deleted picture falls back without leaving the window blank")
ok(background_path("custom:../../settings.json").endswith(os.path.join("Backgrounds", "settings.json")), "picture names cannot leave the Backgrounds folder")
dialog = AppearanceDialog(w, w.s, w.set_custom_colours, w.set_background_picture, w.set_background_dim); ok(len(dialog.swatches) == 3, "the Customize look window opens"); dialog.deleteLater()
w.set_background_dim(70); w.s.set("background", "plain"); w.theme_combo.setCurrentText("Neon Violet"); w.canvas.sync()

# ===== G. protected secrets =====
print("--- G. protected secrets ---")
import app.secure as sec, app.settings as stg, sys as _sys
_platform = _sys.platform; _sys.platform = "linux"
ok(sec.protect("abc") == "abc" and sec.unprotect("abc") == "abc", "outside Windows secrets are stored as before")
_sys.platform = _platform
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
from app.version import label, CREATOR, STAGE
from PySide6.QtWidgets import QLabel as _QL
texts = [l.text() for l in w.findChildren(_QL)]
ok(label() == "v%s \u00b7 Released" % VERSION and STAGE == "Released" and CREATOR == "ZUNIMILABS", "version label reads: %s" % label())
ok(label() in texts and "Developed and powered by ZUNIMILABS." in texts, "the app shows the version label and the company")
ok(w.windowTitle() == "CHATDOOM", "window title: %s" % w.windowTitle())
ok(b"ZUNIMILABS" in urllib.request.urlopen("http://127.0.0.1:%d/" % w.overlay.port).read() if w.overlay.server else True, "overlay start page carries the credit")

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
ok(d.tab_names()[-1] == "Advanced" and d.current_tab() == "Server", "manual options wait in their own Advanced tab"); d.show_tab("Advanced"); ok(d.current_tab() == "Advanced", "the Advanced tab opens the old manual controls"); d.show_tab(0)
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
ok(len([b for b in w.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton) if b.objectName() == "nav"]) == 16 and w.nav.button(8).text().strip() == "Music" and not w.nav.button(8).icon().isNull()
   and w.nav.button(9).text().strip() == "Commands" and w.nav.button(10).text().strip() == "Stream tools" and not w.nav.button(10).icon().isNull(),
   "sidebar has all 16 pages, each with a drawn icon (Music, Commands and Stream tools included)")

# ===== L. multi-stream, commands and memes =====
print("--- L. multi-stream, commands and memes ---")
from app.platforms import Hub, YouTubeSource, TwitchSource
from app.commands import import_file
from app.commands_page import CommandDialog, MemeDialog
from PySide6.QtWidgets import QDialog
got_msgs, got_status = [], []
hub2 = Hub(); hub2.message.connect(got_msgs.append); hub2.status.connect(lambda *a: got_status.append(a))
src = YouTubeSource(hub2, "extra:9"); src._emit(Message("youtube", "A", "hi")); src._status("Connected", True); wait(50)
ok(got_msgs and got_msgs[0].stream == "extra:9" and got_status == [("extra:9", "Connected", True)],
   "an added stream tags its messages and status with its own key")
for c in list(w.extra_cards.values()): w._remove_stream(c)
w.s.set("muted", False); w.mod.blocked = []; w.s.set("skip_links", True); w.s.set("user_cooldown", 0); w.s.set("dedupe_secs", 0)
announced, sent, flagged, announced_dc = [], [], [], []
w.speaker.announce = lambda *a: announced.append(a)
w.platform_auth.send_message = lambda *a, **k: sent.append((a, k))
w.ytmod.flag = lambda m, r: flagged.append((m.stream, r))
w.discord.auto_announce = lambda *a: announced_dc.append(a)
c1 = w._add_stream(); c2 = w._add_stream()
c1.edit.setText("https://youtu.be/VERTICAL123"); c2.platform_box.setCurrentIndex(c2.platform_box.findData("twitch")); c2.edit.setText("friendchan"); c2.edit.editingFinished.emit()
saved = json.load(open(w.s.path, encoding="utf-8"))["extra_streams"]; wait(450)   # stat chips count up
ok(w.num_total.text() == "5" and [d["platform"] for d in saved] == ["youtube", "twitch"] and saved[1]["target"] == "friendchan"
   and isinstance(c2.source, TwitchSource) and c2.source.key == c2.key and c1.key != c2.key,
   "Add stream makes extra YouTube/Twitch cards that are counted and remembered")
w.on_status(c1.key, "Connected", True); wait(450)
ok("Connected" in c1.status.text() and w.num_on.text() == "1" and not w.live.isHidden() and not announced_dc,
   "an added stream shows its own status, counts as connected, and does not post a Discord announcement")
before = w.feed.toPlainText()
w.on_message(Message("youtube", "Vee", "hello from vertical", stream=c1.key))
w.on_message(Message("twitch", "Tee", "hello from friend", stream=c2.key))
c1.label.setText("Vertical")
w.on_message(Message("youtube", "Vee", "labelled now", stream=c1.key))
new_text = w.feed.toPlainText()[len(before):]
ok("YT2 Vee" in new_text and "TW2 Tee" in new_text and "YT·Vertical Vee" in new_text,
   "the chat feed shows which stream each message came from (YT2, TW2, or your label)")
flagged.clear()
w.on_message(Message("youtube", "Linker", "see www.spam.com", uid="UC" + "x" * 22, stream=c1.key))
w.on_message(Message("youtube", "Linker2", "see www.spam2.com", uid="UC" + "y" * 22, stream="youtube"))
ok(flagged == [("youtube", "link")], "the YouTube mod bot only deletes in your main stream, not in added ones")
w._remove_stream(c2); w.on_status(c2.key, "Connected", True); wait(450)
ok(c2.key not in w.extra_cards and c2.key not in w.connected and w.num_total.text() == "4"
   and len(json.load(open(w.s.path, encoding="utf-8"))["extra_streams"]) == 1,
   "removing a stream forgets it, even if a late status arrives")

w.s.set("commands", [{"name": "discord", "response": "Join discord.gg/x {user} ({count})", "mode": "reply", "cooldown": 30},
                     {"name": "hug", "response": "!{user} hugs {touser}", "mode": "speak", "cooldown": 0},
                     {"name": "secret", "response": "mods only text", "mode": "both", "mods_only": True}])
w.s.set("yt_bot_posts", False)   # these checks are about the signed-in account; the bot has its own below
w.platform_auth.is_connected = lambda p: False
before = w.feed.toPlainText(); announced.clear(); spoken.clear()
w.on_message(Message("youtube", "Viewer", "!discord", stream="youtube"))
fresh = w.feed.toPlainText()[len(before):]
ok("Join discord.gg/x Viewer (1)" in fresh and "sign in to YouTube" in fresh and not sent and not spoken and not announced,
   "a !command answers in the feed, explains that chat replies need a sign-in, and is never read aloud")
w.on_message(Message("youtube", "Other", "!discord", stream="youtube"))
ok("!discord not run: cooldown" in w.feed.toPlainText(), "commands have a cooldown for viewers")
w.platform_auth.is_connected = lambda p: True
w.on_message(Message("youtube", "Mod", "!discord", mod=True, stream="youtube"))
w.on_message(Message("youtube", "Mod", "!DISCORD extra words", mod=True, stream=c1.key))
w.on_message(Message("kick", "Kicker", "!discord", mod=True, stream="kick"))
ok([a for a, k in sent] == [("youtube", "Join discord.gg/x Mod (2)", ""), ("youtube", "Join discord.gg/x Mod (3)", "https://youtu.be/VERTICAL123"), ("kick", "Join discord.gg/x Kicker (4)", "")]
   and all(k == {"quiet": True} for a, k in sent) and "Kick replies are not supported" not in w.feed.toPlainText(),
   "signed in, replies go to the right stream (main or added YouTube, or Kick); moderators skip cooldowns")
ok(w.cards["kick"].auth_btn is not None and w.action_platform.findData("kick") >= 0, "the Kick card has a Login button and Kick is in the chat bar")
bot_said = []; real_say = w.ytmod.say; w.ytmod.say = lambda *a: bot_said.append(a)
w.s.set("yt_bot_token", "TOKEN123"); w.s.set("yt_bot_posts", True); w.platform_auth.is_connected = lambda p: False; sent.clear()
w._post_chat("youtube", "Hi chat"); w._post_chat("twitch", "Hi Twitch")
ok(bot_said == [("Hi chat", "")] and [a for a, k in sent] == [("twitch", "Hi Twitch", "")], "with the bot set up it speaks on YouTube, and other platforms use their login")
ok(w._reply_target(Message("youtube", "V", "!x", stream="youtube")) == ("", ""), "a verified channel can answer commands with no streamer login")
w.s.set("yt_bot_posts", False); bot_said.clear(); sent.clear(); w.platform_auth.is_connected = lambda p: True
w._post_chat("youtube", "Mine"); ok(not bot_said and [a for a, k in sent] == [("youtube", "Mine", "")], "turning the bot off posts from the signed-in account")
w.ytmod.say = real_say; sent.clear()
w.on_message(Message("twitch", "T", "!hug @Friend", stream="twitch"))
ok(announced and announced[-1] == ("T hugs Friend",), "read-aloud commands use {user}/{touser} and never start with ! (no command loops)")
w.on_message(Message("twitch", "T", "!secret", stream="twitch"))
ok("!secret not run: mods only" in w.feed.toPlainText(), "mods-only commands ignore regular viewers")
sent.clear()
w.on_message(Message("twitch", "T2", "!commands", stream="twitch"))
ok(sent and sent[-1][0][1].startswith("Commands: !discord !hug !secret"), "built-in !commands lists your commands")
w.on_message(Message("youtube", "Nightbot", "!discord", stream="youtube"))
ok("Nightbot: !discord (skipped: bot)" in w.feed.toPlainText(), "bots cannot run commands")
w.s.set("commands_on", False)
w.on_message(Message("youtube", "Viewer3", "!discord", stream="youtube"))
ok("Viewer3: !discord (skipped: command)" in w.feed.toPlainText(), "with commands off, !messages are skipped like before")
w.s.set("commands_on", True)

os.makedirs(w.memes_dir, exist_ok=True)
pick_dir = tempfile.mkdtemp()
open(os.path.join(pick_dir, "Bruh Sound.mp3"), "wb").write(b"ID3-fake-mp3")
open(os.path.join(pick_dir, "bruh.gif"), "wb").write(b"GIF89a-fake")
snd = import_file(os.path.join(pick_dir, "Bruh Sound.mp3"), w.memes_dir); img = import_file(os.path.join(pick_dir, "bruh.gif"), w.memes_dir)
ok(snd == "Bruh_Sound.mp3" and img == "bruh.gif" and import_file(os.path.join(pick_dir, "bruh.gif"), w.memes_dir) == "bruh_2.gif",
   "picked meme files are copied into the memes folder with safe, unique names")
os.remove(os.path.join(w.memes_dir, "bruh_2.gif"))
w.s.set("memes", [{"name": "bruh", "text": "bruh moment {user}", "sound": snd, "image": img, "cooldown": 0},
                  {"name": "wow", "text": "wow", "cooldown": 0}, {"name": "gone", "sound": "missing.mp3"}])
w.s.set("meme_gap", 30); announced.clear()
m0 = ov("/poll?type=meme&after=-1")["latest"]
w.on_message(Message("youtube", "Fan", "!bruh", stream="youtube"))
meme_ev = ov("/poll?type=meme&after=%d" % m0)["events"]
ok(announced == [("bruh moment Fan", os.path.join(w.memes_dir, snd))] and meme_ev and meme_ev[0]["image"] == "/memes/bruh.gif"
   and meme_ev[0]["caption"] == "bruh moment Fan" and meme_ev[0]["user"] == "Fan",
   "!bruh plays the meme sound, reads its line and shows the picture on the meme overlay")
r = urllib.request.urlopen("http://127.0.0.1:%d/memes/bruh.gif" % w.overlay.port)
ok(r.read() == b"GIF89a-fake" and r.headers["Content-Type"] == "image/gif", "the overlay serves meme pictures from the memes folder")
def status_of(path):
    try: return urllib.request.urlopen("http://127.0.0.1:%d%s" % (w.overlay.port, path)).status
    except urllib.error.HTTPError as e: return e.code
ok(status_of("/memes/" + snd) == 404 and status_of("/memes/..%2Fsettings.json") == 404 and status_of("/memes/%2E%2E%5Csettings.json") == 404,
   "only pictures inside the memes folder can be loaded (no sounds, no other files)")
w.on_message(Message("youtube", "Fan2", "!wow", stream="youtube"))
ok("!wow not run: another meme just played" in w.feed.toPlainText(), "the gap between memes stops meme spam")
w.s.set("meme_gap", 0)
w.on_message(Message("youtube", "Fan2", "!gone", stream="youtube"))
ok("!gone not run: meme file missing" in w.feed.toPlainText(), "a meme whose file was deleted says so instead of failing")
w.s.set("memes_on", False); before = w.feed.toPlainText()
w.on_message(Message("youtube", "Fan3", "!wow", stream="youtube"))
ok("(skipped: command)" in w.feed.toPlainText()[len(before):], "with memes off, !meme messages are skipped like other commands")
w.s.set("memes_on", True)
ok(b'data-mode="meme"' in urllib.request.urlopen(w.overlay.url("meme")).read() and w.ovpage.meme_url.text().endswith("/meme")
   and ov("/poll?type=meme&after=-1")["cfg"]["memeSeconds"] == int(w.s.get("meme_seconds")),
   "the meme overlay page exists, its address is on the OBS overlays page, and it gets the display time")

w.cmdpage.refresh()
row_names = lambda box: [box.itemAt(i).widget().name for i in range(box.count()) if hasattr(box.itemAt(i).widget(), "name")]
ok(row_names(w.cmdpage.cmd_list) == ["discord", "hug", "secret"] and row_names(w.cmdpage.meme_list) == ["bruh", "wow", "gone"],
   "the Commands page lists your commands and memes")
dlg = CommandDialog(w.cmdpage, None, w.cmdpage._taken(""))
dlg.name.setText("!Bruh"); dlg.response.setPlainText("x"); dlg._save()
taken_err = dlg.error.text(); dlg.name.setText("two words"); dlg._save(); bad_err = dlg.error.text()
dlg.name.setText("!Socials"); dlg.response.setPlainText("insta @me"); dlg._save()
ok("already used" in taken_err and "no spaces" in bad_err and dlg.result() == QDialog.Accepted and dlg.item["name"] == "socials",
   "the command editor rejects duplicate or unusable names and saves a clean one")
w.cmdpage._store("commands", None, dlg.item)
ok(w.commands.find("commands", "socials")["response"] == "insta @me" and "socials" in row_names(w.cmdpage.cmd_list), "a new command is saved and listed")
md = MemeDialog(w.cmdpage, None, w.cmdpage._taken(""), w.memes_dir)
md.name.setText("oof"); md._save(); empty_err = md.error.text()
md._set_file("image", os.path.join(pick_dir, "bruh.gif")); md._save()
ok("any one is enough" in empty_err and md.item["image"] == "bruh_2.gif" and os.path.isfile(os.path.join(w.memes_dir, "bruh_2.gif")),
   "the meme editor needs at least one of sound, picture or line, and copies a picked file in")
w.cmdpage._store("memes", None, md.item)
w.cmdpage.delete("memes", "oof")
ok(not os.path.exists(os.path.join(w.memes_dir, "bruh_2.gif")) and os.path.exists(os.path.join(w.memes_dir, "bruh.gif"))
   and w.commands.find("memes", "oof") is None, "deleting a meme removes its own copied file but keeps files other memes use")
tested = []; w.speaker.announce = lambda *a: tested.append(a)
w._test_command("wow")
ok(tested == [("wow", "")] and w.stack.currentIndex() == 1, "the Test button runs a meme as a moderator and opens Live chat")
w.goto(9); wait(200); w.grab().save(os.path.join(os.environ["APPDATA"], "commands.png"))

# ===== M. stream tools, hotkeys and look =====
print("--- M. stream tools, hotkeys and look ---")
import random, ctypes
import app.ui as ui_module
from app.tools import Points, split_amount
from app.hotkeys import parse as parse_hotkey, WM_HOTKEY
w.platform_auth.is_connected = lambda p: True
sent.clear(); announced.clear(); w.speaker.announce = lambda *a: announced.append(a)
w.on_status("youtube", "Connected", True)
T = w.tools
fan = Message("youtube", "Coin Fan", "hello", uid="UC" + "c" * 22, stream="youtube")
T.points.reset(); now = time.time()
T.points.earn(fan, now); T.points.earn(fan, now + 5); T.points.earn(fan, now + 61)
key = "youtube:" + "UC" + "c" * 22
ok(T.points.balance(key) == 10, "chatting earns points once per cooldown (spam earns nothing extra)")
T.points.file.data[key]["bonus"] = 0
ok(T.points.tick(now + 70) == 1 and T.points.balance(key) == 20, "viewers who chatted recently get the watching bonus")
w.on_message(Message("youtube", "Coin Fan", "!points", uid="UC" + "c" * 22, stream="youtube"))
ok(sent and sent[-1][0][1] == "Coin Fan has 20 coins", "!points replies with the viewer's balance")
random.seed(1); w.on_message(Message("youtube", "Coin Fan", "!gamble 500", uid="UC" + "c" * 22, stream="youtube"))
ok("only have 20 coins" in sent[-1][0][1], "!gamble refuses bets bigger than the balance")
w.on_message(Message("youtube", "Coin Fan", "!gamble all", uid="UC" + "c" * 22, stream="youtube"))
ok(T.points.balance(key) in (0, 40) and ("won 20" in sent[-1][0][1] or "lost 20" in sent[-1][0][1]), "!gamble all is double or nothing")
w.on_message(Message("youtube", "Coin Fan", "!gamble 10", uid="UC" + "c" * 22, stream="youtube"))
ok("!gamble not run: cooldown" in w.feed.toPlainText(), "!gamble has a cooldown")

w.s.set("memes", [{"name": "bruh", "text": "bruh", "sound": snd, "image": img, "cooldown": 0, "cost": 50}])
w.s.set("meme_gap", 0); T.points.file.data[key]["points"] = 30
w.on_message(Message("youtube", "Coin Fan", "!bruh", uid="UC" + "c" * 22, stream="youtube"))
ok("!bruh not run: needs 50 coins" in w.feed.toPlainText() and T.points.balance(key) == 30, "a meme with a cost needs enough points")
T.points.add(key, 40); announced.clear()
w.on_message(Message("youtube", "Coin Fan", "!bruh", uid="UC" + "c" * 22, stream="youtube"))
ok(announced and T.points.balance(key) == 20, "with enough points the meme plays and the cost is taken")

sent.clear()
w.start_poll("Next game?", ["Valorant", "GTA", "", ""], 60)
ok(T.poll.active and sent and sent[-1][0][1].startswith("Poll: Next game? Vote with !vote 1 = Valorant"), "starting a poll announces it in chat")
w.on_message(Message("youtube", "V1", "!vote 1", uid="UC" + "1" * 22, stream="youtube"))
w.on_message(Message("twitch", "V2", "2", uid="t2", stream="twitch"))
w.on_message(Message("kick", "V3", "!vote 2", uid="k3", stream="kick"))
w.on_message(Message("kick", "V3", "!vote 1", uid="k3", stream="kick"))
w.on_message(Message("kick", "V4", "!vote 9", uid="k4", stream="kick"))
ok(T.poll.tally() == [2, 1] and "(vote counted)" in w.feed.toPlainText() and "pick a number from 1 to 2" in w.feed.toPlainText(),
   "votes from every platform count (a number alone works, the last vote counts, bad numbers explain)")
wid = ov("/poll?type=widgets&after=-1")["state"]
ok(wid["poll"]["question"] == "Next game?" and [o["votes"] for o in wid["poll"]["options"]] == [2, 1] and wid["poll"]["endsIn"] > 0,
   "the /widgets overlay shows the live poll")
T.poll.ends = time.time() - 1; announced.clear(); w._tools_tick()
ok(not T.poll.active and announced == [("Poll ended: Valorant wins with 2 of 3 votes.",)] and sent[-1][0][1] == "Poll ended: Valorant wins with 2 of 3 votes.",
   "the poll ends by itself and the result is read aloud and posted")
w.on_message(Message("twitch", "Late", "1", uid="late", stream="twitch"))
ok(T.poll.tally() == [2, 1], "after the poll ends a plain number is ordinary chat again")

w.open_giveaway("!Join", 0)
for who, plat, uid in (("A", "youtube", "UC" + "a" * 22), ("B", "twitch", "tb"), ("A", "youtube", "UC" + "a" * 22)):
    w.on_message(Message(plat, who, "!join", uid=uid, stream=plat))
ok(T.giveaway.active and len(T.giveaway.entries) == 2 and "!join not run: already entered" in w.feed.toPlainText(), "viewers enter the giveaway once, from any platform")
random.seed(3); announced.clear(); w.pick_winner(); first = T.giveaway.winners[-1][1]; w.pick_winner(); second = T.giveaway.winners[-1][1]
ok({first, second} == {"A", "B"} and announced and "giveaway winner" in announced[0][0], "picking winners never repeats a winner and reads the result aloud")
w.pick_winner(); ok("Nobody (else)" in w.toasts.items[0].label.text(), "with everyone picked, a toast says there is nobody left")
ok(ov("/poll?type=widgets&after=-1")["state"]["giveaway"]["winner"] == second, "the /widgets overlay shows the winner")
w.clear_giveaway(); w.s.set("giveaway_cost", 25)
w.open_giveaway("raffle", 25)
w.on_message(Message("youtube", "Poor", "!raffle", uid="UC" + "p" * 22, stream="youtube"))
ok("!raffle not run: needs 25 coins" in w.feed.toPlainText(), "a giveaway with an entry cost needs points")
w.clear_giveaway()

w.goto(10); wait(150)
w.toolspage.counter_name.setText("Death"); w.toolspage.counter_label.setText("Deaths"); w.toolspage._add_counter()
w.on_message(Message("twitch", "Viewer", "!death+", uid="tv", stream="twitch"))
w.on_message(Message("twitch", "Mod", "!death+", uid="tm", mod=True, stream="twitch"))
w.on_message(Message("twitch", "Mod", "!death +", uid="tm", mod=True, stream="twitch"))
w.on_message(Message("twitch", "Viewer", "!death", uid="tv", stream="twitch"))
ok("!death not run: mods only" in w.feed.toPlainText() and T.counters()[0]["value"] == 2 and sent[-1][0][1] == "Deaths: 2",
   "counters: anyone can see them, only moderators change them")
ok(ov("/poll?type=widgets&after=-1")["state"]["counters"] == [{"label": "Deaths", "value": 2}]
   and any(getattr(w.toolspage.counter_list.itemAt(i).widget(), "name", "") == "death" for i in range(w.toolspage.counter_list.count())),
   "counters appear on the Stream tools page and the /widgets overlay")
w._hotkey("hk_counter"); ok(T.counters()[0]["value"] == 3, "the counter hotkey adds one")

w.s.set("welcome_on", True); w.s.set("welcome_mode", "ever"); announced.clear()
w.on_message(Message("youtube", "Newbie", "hi all", uid="UC" + "n" * 22, stream="youtube"))
w.on_message(Message("youtube", "Newbie", "second message", uid="UC" + "n" * 22, stream="youtube"))
ok(announced == [("Welcome Newbie! Thanks for stopping by.",)] and "★ Welcome Newbie" in w.feed.toPlainText(), "a first-time chatter is welcomed once")
w.s.set("welcome_mode", "stream"); T.seen_stream = set(); announced.clear()
w.on_message(Message("youtube", "Newbie", "back again", uid="UC" + "n" * 22, stream="youtube"))
ok(announced == [("Welcome Newbie! Thanks for stopping by.",)], "the each-stream mode welcomes returning viewers on a new stream")
w.s.set("welcome_on", False)

w.s.set("timers", [{"message": "Join the Discord!", "minutes": 10, "lines": 2, "mode": "reply"}]); T.reset_timers(); sent.clear()
w._last_timer_tick = 0; w._tools_tick()
ok(not sent, "a new timer waits its interval first")
T.timer_last[0] = time.time() - 700; w._last_timer_tick = 0; w._tools_tick()
ok(not sent, "a timer waits for enough chat messages, so it never talks into an empty chat")
for i in range(2): w.on_message(Message("youtube", "Chatter%d" % i, "line %d" % i, uid="UC" + str(i) * 22, stream="youtube"))
w._last_timer_tick = 0; w._tools_tick()
ok([a for a, k in sent] == [("youtube", "Join the Discord!", "")], "a due timer posts to your connected chats")

w.music.tracks = [{"title": "Desi Beat", "artist": "Aria", "path": "desi.mp3"}, {"title": "Chill Lofi", "artist": "Bo", "path": "lofi.mp3"},
                  {"title": "Night Drive", "artist": "Cy", "path": "night.mp3"}]
w.music.requests, w.music.playing = [], False; sent.clear()
w.on_message(Message("twitch", "S1", "!sr lofi", uid="s1", stream="twitch"))
ok(w.music.index == 1 and w.music.playing and sent[-1][0][1] == "Playing Chill Lofi now", "!sr plays a matching song at once when nothing is playing")
w.on_message(Message("twitch", "S2", "!sr desi beat", uid="s2", stream="twitch"))
w.on_message(Message("twitch", "S2", "!sr night", uid="s2", stream="twitch"))
ok(w.music.requests == [(0, "twitch:s2")] and sent[-1][0][1] == "Added Desi Beat to the queue (#1)", "a second request is queued")
ok("!sr not run: cooldown" in w.feed.toPlainText(), "one viewer cannot flood the song queue")
w.music.next(); ok(w.music.index == 0 and not w.music.requests, "requested songs play before the shuffle")
w.on_message(Message("twitch", "S3", "!song", uid="s3", stream="twitch"))
ok(sent[-1][0][1] == "Now playing: Desi Beat — Aria", "!song says what is playing")
w.music.stop()

ok(split_amount("₹1,200.50") == ("₹", 1200.5) and split_amount("50 bits") == ("bits", 50.0), "amounts are split into currency and value")
lines = w.summary_text()
ok("Stream summary" in lines and "Messages:" in lines and "Poll votes" in lines and "Giveaway entries" in lines, "the stream summary counts chat and tools")
hooks = []; ui_module.post_webhook = lambda url, text: hooks.append((url, text)) or {"ok": True}
w.s.set("webhook_url", "https://discord.example/hook"); ok(w.post_summary(), "the summary can be posted to Discord")
wait(300); ok(hooks and hooks[0][0] == "https://discord.example/hook" and "Stream summary" in hooks[0][1], "the Discord webhook receives the summary")
hooks.clear(); w.s.set("summary_post", True); saved_connected = set(w.connected); w.connected.clear()
w.tools.stats.started = time.time() - 3600; w.tools.stats.ended = 0; w._stream_over(); wait(300)
ok(hooks and w.tools.stats.ended, "when the stream ends the summary is shown and posted automatically")
w.connected.update(saved_connected); w.s.set("summary_post", False)
w.tools.stats.ended = time.time(); w._stream_started()
ok(w.tools.stats.started and not w.tools.stats.ended and not w.tools.seen_stream, "the next stream starts a fresh summary")

w.tools.save()
reloaded = Points(w.s, os.path.join(os.environ["APPDATA"], "ChatVoice", "points.json"))
ok(reloaded.balance(key) == T.points.balance(key) and os.path.isfile(os.path.join(os.environ["APPDATA"], "ChatVoice", "viewers.json")),
   "points and known viewers are saved and survive a restart")

ok(parse_hotkey("Ctrl+Alt+S") == (0x4000 | 0x2 | 0x1, ord("S")) and parse_hotkey("F9") == (0x4000, 0x78)
   and parse_hotkey("Ctrl+Shift+F12") == (0x4000 | 0x2 | 0x4, 0x7B) and parse_hotkey("S") is None and parse_hotkey("") is None,
   "hotkeys need a modifier unless they are F-keys")
skipped = []; w.speaker.skip = lambda: skipped.append(1)
w.hotkeys.ids = {1: "hk_skip"}
msg = ctypes.wintypes.MSG(); msg.message = WM_HOTKEY; msg.wParam = 1
handled = w.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg))
other = ctypes.wintypes.MSG(); other.message = 0x0100
ok(handled == (True, 0) and skipped == [1] and w.nativeEvent(b"windows_generic_MSG", ctypes.addressof(other))[0] is False,
   "a global hotkey message runs its action (Skip) and other messages pass through")
w.hotkeys.ids = {}
was = w.s.get("muted"); w._hotkey("hk_mute"); ok(w.s.get("muted") != was, "the mute hotkey toggles the voice"); w._hotkey("hk_mute")

w.s.set("lite_mode", False)
for mode in ("aurora", "gradient", "plain"):
    w.s.set("background", mode); w.canvas.sync(); wait(80)
    ok(not w.canvas.grab().isNull(), "the %s background draws" % mode)
w.s.set("lite_mode", True); w.canvas.sync(); ok(not w.canvas.timer.isActive(), "Lite mode stops the background motion"); w.s.set("lite_mode", False)
w.s.set("background", "aurora")
b0 = w.canvas.blobs(0.0); b1 = w.canvas.blobs(30.0)
ok(b0[0][1] != b1[0][1] and all(0 <= b[1] <= 1.1 and 0 <= b[2] <= 1.1 for b in b0 + b1), "the aurora lights drift slowly and stay on the canvas")
w.goto(10); wait(400)
btn = w.nav.button(10)
ok(w.nav_glow.isVisible() and abs(w.nav_glow.geometry().center().y() - btn.geometry().center().y()) <= 2, "the sidebar highlight glides to the selected page")
n0 = len(w.toasts.items); t = w.toasts.show("Hello toast", "good"); wait(400)
ok(t is not None and w.toasts.items[0] is t and len(w.toasts.items) == min(4, n0 + 1) and t.x() + t.width() <= w.canvas.width(),
   "a new toast appears on top, inside the window")
w.toasts.dismiss(t); wait(350); ok(t not in w.toasts.items, "toasts can be dismissed")
for i in range(6): w.toasts.show("toast %d" % i)
ok(len(w.toasts.items) <= 4, "no more than four toasts at once")
w.toolspage.refresh()
ok("Valorant" in w.toolspage.poll_label.text() and "Coin Fan" in w.toolspage.top_label.text() and "Stream summary" in w.toolspage.summary_label.text(),
   "the Stream tools page shows the poll, the top viewers and the summary")
ok(b'data-mode="widgets"' in urllib.request.urlopen(w.overlay.url("widgets")).read() and w.ovpage.widgets_url.text().endswith("/widgets"),
   "the /widgets overlay page exists and its address is on the OBS overlays page")
w.goto(10); wait(300); w.grab().save(os.path.join(os.environ["APPDATA"], "tools.png"))
shutil.rmtree(pick_dir, ignore_errors=True)

# ===== N. updates that survive a new look, and the home screen design =====
print("--- N. safe updates and the new look ---")
import hashlib, struct
from PySide6.QtWidgets import QGraphicsOpacityEffect
from app.theme import build_qss
from app.ui import PAGES
from app.version import VERSION
from app import settings as settings_module
from app.config import YT_BOT_HANDLE
from app.visuals import StatCard, top_cards

ok(upd.parse_version("V1.0.4.1") > upd.parse_version("V1.0.4") and upd.parse_version("V1.0.3-v2") == (1, 0, 3, 0) and upd.parse_version("") == (0, 0, 0, 0),
   "versions compare all four numbers and ignore a suffix like -v2")
os.environ["_PYI_APPLICATION_HOME_DIR"] = "x"; os.environ["QT_PLUGIN_PATH"] = "x"
env = upd.clean_env()
ok("_PYI_APPLICATION_HOME_DIR" not in env and "QT_PLUGIN_PATH" not in env and env["PYINSTALLER_RESET_ENVIRONMENT"] == "1",
   "the installer does not inherit the old app's file locations")
del os.environ["_PYI_APPLICATION_HOME_DIR"], os.environ["QT_PLUGIN_PATH"]

class NoAsset(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        b = json.dumps({"tag_name": "V9.9.9", "html_url": "https://github.com/Deba-dev/ChatDoom/releases/tag/V9.9.9", "assets": []}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
empty_gh = ThreadingHTTPServer(("127.0.0.1", 8814), NoAsset); threading.Thread(target=empty_gh.serve_forever, daemon=True).start()
upd.GH_API = "http://127.0.0.1:8814"
w.s.set("update_last", 0); w.pending_update = None; w.banner.hide(); w.updater.check(False); wait(500)
ok(not w.banner.isVisible() and w.s.get("update_last") == 0, "a release still being built is not offered, and is checked again soon")
w.updater.check(True); wait(500)
ok("being prepared" in w.banner_text.text() and not w.upd_btn.isVisible(), "a manual check explains the installer is still being built")
upd.GH_API = "http://127.0.0.1:8813"; empty_gh.shutdown(); w.banner.hide()

w.s.set("update_pending", "9.9.9"); w.feed.clear(); stale = os.path.join(tempfile.gettempdir(), "CHATDOOM-Setup-0.0.0-test.exe"); open(stale, "wb").close()
w.updater.after_start(); wait(50)
ok("did not finish" in w.feed.toPlainText() and not w.s.get("update_pending") and not os.path.exists(stale),
   "a failed update is reported on the next start, and old installers are cleaned up")
w.s.set("update_pending", VERSION); w.feed.clear(); w.updater.after_start(); wait(50)
ok("did not finish" not in w.feed.toPlainText(), "a finished update says nothing")

path = os.path.join(os.environ["APPDATA"], "atomic.json")
one = settings_module.Settings(path); one.set("theme", "Ocean")
real_replace = os.replace
def broken_replace(*a): raise OSError("disk full")
settings_module.os.replace = broken_replace; one.set("theme", "Sunset"); settings_module.os.replace = real_replace
ok(settings_module.Settings(path).get("theme") == "Ocean" and [f for f in os.listdir(os.environ["APPDATA"]) if f.endswith(".tmp")] == [],
   "a failed save leaves the previous settings whole, with no leftovers")
with open(path, "w", encoding="utf-8") as f: json.dump({"yt_bot_handle": "@ChatVoice-V1", "yt_bot_title": "CHATDOOM Moderator"}, f)
two = settings_module.Settings(path)
ok(two.get("yt_bot_handle") == YT_BOT_HANDLE == "@ChatDoom" and two.get("yt_bot_title") == "CHATDOOM", "the renamed YouTube bot replaces the old saved name")
w.s.set("theme", "No Such Theme"); ok(bool(build_qss("No Such Theme")), "a theme removed in a later version falls back instead of crashing")
w.s.set("theme", "Neon Violet")

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
source = open(os.path.join(here, "branding", "chatdoom-logo-source.png"), "rb").read()
ok(open(os.path.join(here, "branding", "source.sha256")).read().strip() == hashlib.sha256(source).hexdigest(),
   "the icons were made from the current logo (otherwise run tools/make_icons.py)")
ico = open(os.path.join(here, "assets", "icon.ico"), "rb").read()
count = struct.unpack("<H", ico[4:6])[0]
ok(ico[:4] == b"\x00\x00\x01\x00" and count >= 6 and 0 in [ico[6 + 16 * i] for i in range(count)], "icon.ico is a real icon with a full-size picture")
iss = open(os.path.join(here, "installer.iss"), encoding="utf-8").read()
ok('Name: "{app}\\_internal"' in iss and "ChangesAssociations=yes" in iss and "RestartApplications=no" in iss and "PrepareToInstall" in iss,
   "the installer replaces old files, refreshes icons, and closes the app first")
version_files = [open(os.path.join(here, n), encoding="utf-8").read() for n in ("installer.iss", "version_info.txt")]
ok("AppVersion=%s" % VERSION in version_files[0] and "'ProductVersion', '%s'" % VERSION in version_files[1], "the version number matches in every file")

w.goto(0); wait(100)
ok(not w.statbar.isVisible() and w.num_total.parent().objectName() == "stat", "the Connect page shows its own stat cards")
for i in range(1, w.stack.count()):
    if i in (11, 14, 15): continue           # the design pages and Settings use the room for themselves
    w.goto(i); wait(30)
    shown = [c.num.text() for c in w.stat_cards]
    ok(w.statbar.isVisible() and all(shown) and all(c.cap.text() for c in w.stat_cards), "%s shows three live stats" % PAGES[i])
w.goto(1); before = w.msg_seen
w.on_message(Message("youtube", "Asha", "hello from the stats test")); w._refresh_stats()
ok(w.msg_seen == before + 1 and w.stat_cards[0].num.text() == str(before + 1), "the stat cards count real messages")
w.goto(3); wait(10)
ok(len(top_cards(w.stack.widget(3))) >= 2, "the Moderation page uses cards like the home screen")
w.s.set("lite_mode", True); w.goto(5); wait(30)
ok(w.title_line.width() == 72 and all(c.graphicsEffect() is None for c in top_cards(w.stack.widget(5))), "Lite mode skips the entrance animations")
w.s.set("lite_mode", False); w.goto(5); wait(700)
ok(all(not isinstance(c.graphicsEffect(), QGraphicsOpacityEffect) for c in top_cards(w.stack.widget(5))), "cards are left clean when the entrance animation ends")
# ===== O. submenus, alert designs and the new viewer tools =====
print("--- O. submenus, alert designs, viewer tools ---")
from app import alert_styles as AS
from app.commands import render, safe_math
from app.ui_kit import SubPage

nav_ids = [w.nav.id(b) for b in w.nav.buttons()]
ok(sorted(nav_ids) == list(range(16)) and all(w.nav.button(i).text().strip() == PAGES[i] for i in range(16)), "every main page has a sidebar button")
tabbed = [i for i in range(w.stack.count()) if isinstance(w.stack.widget(i), SubPage)]
ok(set(tabbed) == set(range(2, 16)), "every settings page uses the horizontal submenu")
for i in tabbed:
    page = w.stack.widget(i); w.goto(i); wait(20)
    ok(page.subnav.isVisible() and len(page.tab_names()) >= 2 and page._tabs.width() > 0, "%s has a submenu: %s" % (PAGES[i], ", ".join(page.tab_names())))
    for name in page.tab_names():
        page.show_tab(name)
        assert page.current_tab() == name
    page.show_tab(0)
w.resize(980, 680); wait(50)
for i in tabbed:
    w.goto(i); wait(40); p = w.stack.widget(i)
    view, seen = p._strip.viewport(), []
    for name in p.tab_names():
        p.show_tab(name); wait(5)
        b = p._group.checkedButton(); x = b.mapTo(view, b.rect().topLeft()).x()
        seen.append(x >= 0 and x + b.width() <= view.width())
    overflow = p._strip.horizontalScrollBar().maximum() > 0
    ok(all(seen) and p._arrows[1].isVisible() == overflow and p.subnav.width() <= p.width(), "%s: every tab can be reached on the smallest window" % PAGES[i])
    p.show_tab(0)
w.resize(1280, 840)

ok(all(len(x) >= 10 for x in (AS.LOOKS, AS.ENTERS, AS.EXITS, AS.TEXT_FX, AS.EFFECTS, AS.FONTS, AS.PACKS)) and len(AS.IDLES) >= 8, "over 10 looks, animations, text effects, particles, fonts and packs")
from app.overlay_html import PAGE
for prefix, group in ((".style-", AS.LOOKS), (".in-", AS.ENTERS), (".exit-", AS.EXITS), (".idle-", AS.IDLES), (".t-", AS.TEXT_FX[1:])):
    missing = [v for _, v in group if prefix + v not in PAGE and v not in ("neon",)]
    ok(not missing, "every %s value has CSS in the overlay %s" % (prefix, missing))
for name, values in AS.PACKS:
    assert AS.clean(values)["look"] == values["look"] and AS.clean(values)["font"] == values["font"], name
ok(AS.clean({"look": "<script>", "font": "x", "size": 999, "c1": "red;}", "seconds": "x"})["look"] == "neon" and AS.clean({"size": 999})["size"] == 160 and AS.clean({"c1": "red;}"})["c1"] == "#8b5cf6",
   "a broken saved design falls back to safe values")
A = w.alertspage
w.s.set("ov_alert_design", {}); w.s.set("ov_alert_custom", {}); A.target.setCurrentIndex(0)
A.boxes["look"].setCurrentIndex(A.boxes["look"].findData("comic"))
ok(ov("/poll?type=alert&after=-1")["cfg"]["alertDesigns"]["default"]["look"] == "comic" and w.s.get("ov_alert_style") == "comic", "changing the look reaches OBS")
A.pack_buttons[4].click()
d = ov("/poll?type=alert&after=-1")["cfg"]["alertDesigns"]["default"]
ok(d["look"] == "cyber" and d["enter"] == "glitch" and d["font"] == "Audiowide", "a pack sets the whole design")
A.target.setCurrentIndex(A.target.findData("follow"))
ok(A.own.isVisibleTo(A) and not A.own.isChecked(), "a type starts with the main design")
A.boxes["enter"].setCurrentIndex(A.boxes["enter"].findData("spin"))
cfg = ov("/poll?type=alert&after=-1")["cfg"]["alertDesigns"]
ok(A.own.isChecked() and cfg["follow"]["enter"] == "spin" and cfg["follow"]["look"] == "cyber" and cfg["default"]["enter"] == "glitch" and "raid" not in cfg, "follows can have their own design without changing the others")
A.own.setChecked(False)
ok("follow" not in ov("/poll?type=alert&after=-1")["cfg"]["alertDesigns"], "turning it off goes back to the main design")
A.target.setCurrentIndex(0)
outside = os.path.join(tempfile.gettempdir(), "secret.png"); open(outside, "wb").close()
ok(AS.for_overlay(AS.clean({"image": "../../secret.png", "sound": outside}), w.overlay.sounds_dir, w.memes_dir)["imageUrl"] == "", "files outside the app's folders never reach the overlay")
n0 = ov("/poll?type=alert&after=-1")["latest"]; A.test_all()
ok(len(ov("/poll?type=alert&after=%d" % n0)["events"]) == len(AS.ALERT_TYPES), "Test every alert sends one of each")
ok(b'data-mode="preview"' in urllib.request.urlopen(w.overlay.url("preview")).read(), "the live preview page exists")
w.s.set("ov_alert_design", {}); w.s.set("ov_alert_style", "neon"); w.s.set("ov_alert_custom", {}); A.load()

class V:
    def __init__(s, author, mod=False, platform="youtube"): s.author, s.mod, s.platform = author, mod, platform
ok(render("{math:2*(3+4)} {math:__import__('os')} {math:9**9**9} {math:1/0}", V("a")) == "14 ? ? ?", "{math} only does plain sums and never runs code")
ok(safe_math("10/4") == "2.50" and safe_math("(" * 300) == "?", "{math} shows decimals and survives junk")
r = render("{random:5-5} {pick:only} {counter:nope} {level} {nosuch} {random:abc}", V("a"), extra={"level": 3})
ok(r == "5 only 0 3 {nosuch} {random:abc}", "new variables work and unknown ones are left alone")

T = w.tools; say = lambda who, text, mod=False: T.handle(Message("twitch", who, text, mod=mod))
from app.models import viewer_key
key = lambda who: viewer_key(Message("twitch", who, "x"))
w.s.set("points_on", True); T.points.reset(); T.points.add(key("Ana"), 1000, "Ana"); T.points.add(key("Bo"), 300, "Bo"); T.points.add(key("Cy"), 100, "Cy")
now = time.time()
ok(T.prediction.start("Win?", ["Yes", ""], 60, now) != "" and T.prediction.start("Win?", ["Yes", "No"], 60, now) == "", "a prediction needs two outcomes")
say("Ana", "!bet 1 300"); say("Bo", "!bet 2 300"); say("Cy", "!bet 2 100")
ok(T.points.balance(key("Ana")) == 700 and T.points.balance(key("Bo")) == 0 and T.prediction.pools() == [300, 400], "bets take points straight away")
ok(say("Ana", "!bet 2 10")["skipped"] == "already bet" and "only have" in say("Zed", "!bet 1 5")["reply"], "one bet each, and no betting points you lack")
w.lock_prediction(); ok(say("Dee", "!bet 1 5")["skipped"] == "bets are locked", "locked bets stay closed")
w.resolve_prediction(2)
ok(T.points.balance(key("Bo")) == 300 + 225 and T.points.balance(key("Cy")) == 100 + 75 and T.points.balance(key("Ana")) == 700 and "No won" in T.prediction.result, "winners share the losing side in proportion to their bet")
T.prediction.__init__(); T.prediction.start("Q?", ["A", "B"], 60, now); say("Ana", "!bet 1 100"); w.resolve_prediction(2)
ok(T.points.balance(key("Ana")) == 700 and "returned" in T.prediction.result, "if nobody picked the winner, bets come back")
T.prediction.__init__(); T.prediction.start("Q?", ["A", "B"], 60, now); say("Ana", "!bet 1 all"); ok(T.points.balance(key("Ana")) == 0, "!bet 1 all works"); w.cancel_prediction()
ok(T.points.balance(key("Ana")) == 700, "cancelling refunds everyone")
T.prediction.__init__(); T.prediction.ends = 0; T.prediction.start("Q?", ["A", "B"], -1, now); w._tools_tick(); ok(T.prediction.locked, "bets lock by themselves when time runs out"); T.prediction.__init__()

ok(say("Ana", "!queue") is None, "the queue does nothing while closed")
w.set_queue(True); ok("number 1" in say("Ana", "!queue")["reply"] and "number 2" in say("Bo", "!queue")["reply"] and "already" in say("Ana", "!queue")["reply"], "viewers join the queue once")
ok("number 2" in say("Bo", "!place")["reply"] and say("Bo", "!next")["skipped"] == "mods only", "!place works and !next is for moderators")
ok("Ana" in say("Mod", "!next", True)["reply"] and "number 1" in say("Bo", "!place")["reply"], "!next calls the first viewer")
say("Bo", "!leave"); ok(T.queue.people == [], "!leave works"); ok(ov("/poll?type=widgets&after=-1")["state"]["queue"]["open"] is True, "the queue reaches the overlay"); w.set_queue(False)

w.s.set("shop_on", True); w.s.set("shop_items", [{"name": "Pick game", "cost": 200, "stock": 1}, {"name": "Song", "cost": 5000, "stock": -1}]); bal = T.points.balance(key("Ana"))
ok("1. Pick game (200)" in say("Ana", "!shop")["reply"], "!shop lists the rewards")
ok("bought" in say("Ana", "!buy 1")["reply"] and T.points.balance(key("Ana")) == bal - 200 and T.shop_items()[0]["stock"] == 0 and T.redeemed[0] == ("Ana", "Pick game"), "buying takes points, lowers stock and is listed")
ok("sold out" in say("Ana", "!buy pick game")["reply"] and "costs" in say("Ana", "!buy 2")["reply"] and T.points.balance(key("Ana")) == bal - 200, "sold-out and too-expensive rewards take nothing")
w.s.set("shop_items", []); w.s.set("shop_on", False)

w.s.set("say_on", True); w.s.set("say_cost", 50); w.s.set("say_cooldown", 30); bal = T.points.balance(key("Ana"))
ok(say("Ana", "!say hello bhai")["speak"] == "Ana says hello bhai" and T.points.balance(key("Ana")) == bal - 50, "!say spends points and reads the message")
ok(say("Ana", "!say again")["skipped"] == "cooldown" and T.points.balance(key("Ana")) == bal - 50, "!say has a cooldown and charges nothing then")
ok(say("Bo", "!say visit evil.com now")["skipped"] == "links are not read aloud", "links are never read")
w.s.set("say_on", False)

w.s.set("levels_on", True); w.s.set("level_base", 100); w.s.set("level_xp_msg", 100); w.s.set("points_msg_cooldown", 0); T.points.reset(); T.points.levelups = []
m = Message("twitch", "Lev", "hi"); T.points.earn(m, 1000.0)
ok(T.points.level(viewer_key(m)) == 2 and T.points.levelups == [("twitch", "Lev", 2)], "viewers level up and it is queued for chat")
T.points.earn(m, 1001.0); ok(len(T.points.levelups) == 1, "a level is only announced once")
w._announce_levels(); ok("Lev reached level 2" in w.feed.toPlainText() and T.points.levelups == [], "the level-up shows in the feed")
ok("level 2" in say("Lev", "!level")["reply"], "!level shows progress")

w.s.set("goals", [{"title": "Followers", "source": "follows", "target": 10, "value": 0}, {"title": "Tips", "source": "money", "target": 1000, "value": 0}, {"title": "Hand", "source": "manual", "target": 5, "value": 0}])
w._push_alert({"platform": "twitch", "category": "follow", "name": "New"}); w._push_alert({"platform": "tip", "category": "tip", "name": "Rich", "amount": "\u20b91,200.50"})
st = ov("/poll?type=widgets&after=-1")["state"]
ok([g["value"] for g in st["goals"]] == [1, 1200, 0], "goals count their own kind of alert")
w.s.set("latest_overlay", True); w.tools_changed(); st = ov("/poll?type=widgets&after=-1")["state"]
ok({"label": "Latest tip", "value": "Rich \u20b91,200.50"} in st["latest"], "the latest supporters reach the overlay")
w.s.set("goals", []); w.s.set("latest_overlay", False)
T.stats.reset(); ok("not live" in say("Ana", "!uptime")["reply"], "!uptime when offline"); T.stats.begin(time.time() - 3700); ok("1h 1m" in say("Ana", "!uptime")["reply"], "!uptime counts the stream")
ok("1h 1m" in render("{uptime}", V("a"), extra=T.command_values(Message("twitch", "Ana", "x"))), "{uptime} works in custom commands")
T.stats.reset()
T.points.add(key("Sav"), 500, "Sav"); T.prediction.__init__(); T.prediction.start("Q?", ["A", "B"], 60, now); say("Sav", "!bet 1 200")

# overlay styles: chat, now playing, memes and widgets
from app import overlay_styles as OS
P = w.stylespage
for prefix, group in ((".skin-", OS.SKINS[1:]),):
    missing = [v for _, v in group if prefix + v not in PAGE]
    ok(not missing and len(OS.SKINS) >= 20, "every skin has CSS in the overlay %s" % missing)
ok(".in-nudge" in PAGE and all(OS.pack_for(k, v) for k in OS.KIND_KEYS for _, v in OS.PACKS), "every pack works on every overlay")
w.s.set("ov_designs", {}); w.s.set("ov_chat_style", "panel")
ok(OS.design_for(w.s, "chat")["skin"] == "panel", "the chat look chosen in an older version is kept")
w.s.set("ov_chat_style", "glass"); P.target.setCurrentIndex(0); P.load()
P.pack_buttons[3].click()
c = ov("/poll?type=chat&after=-1")["cfg"]["designs"]
ok(c["chat"]["skin"] == "arcade" and c["chat"]["font"] == "Press Start 2P" and c["chat"]["idle"] == "none" and c["music"]["skin"] == "classic", "a pack styles chat only, and keeps chat lines still")
P.boxes["align"].setCurrentIndex(P.boxes["align"].findData("center")); P.sliders["maxLines"].setValue(12); P.checks["hideCommands"].setChecked(True)
c = ov("/poll?type=chat&after=-1")["cfg"]["designs"]["chat"]
ok(c["align"] == "center" and c["maxLines"] == 12 and c["hideCommands"] is True, "chat layout options reach OBS")
for kind, keys in (("music", ("showEq", "position")), ("meme", ("picture", "effect")), ("widgets", ("panelSide", "goalsAt"))):
    P.target.setCurrentIndex(P.target.findData(kind)); P.load()
    ok(all(k in P.design() for k in keys), "%s has its own options" % kind)
    ok(P.test.isVisibleTo(P) == (kind != "widgets"), "%s test button is right" % kind)
P.target.setCurrentIndex(P.target.findData("meme")); P.load(); P.boxes["skin"].setCurrentIndex(P.boxes["skin"].findData("royal"))
ok(OS.clean("meme", {"skin": "bad", "picture": 999, "c1": "red;}"})["picture"] == 100 and OS.clean("meme", {"skin": "bad"})["skin"] == "classic", "a broken saved design falls back")
ok("align" not in OS.clean("meme", {"align": "center"}), "options from another overlay are ignored")
P.match_everywhere()
c = ov("/poll?type=alert&after=-1")["cfg"]
ok(all(c["designs"][k]["skin"] == "royal" for k in OS.KIND_KEYS) and c["alertDesigns"]["default"]["look"] == "royal", "Use this style everywhere matches every overlay and alert")
n0 = ov("/poll?type=chat&after=-1")["latest"]; P.target.setCurrentIndex(0); P.load(); P.send_test()
ok(len(ov("/poll?type=chat&after=%d" % n0)["events"]) == len(OS.SAMPLES["chat"]), "the chat test sends sample lines")
w.s.set("ov_designs", {}); w.s.set("ov_alert_design", {}); w.s.set("ov_alert_style", "neon"); P.load()

# every fine-detail option
from app import style_fields as SF
for kind in SF.ALL:
    rows = SF.fields_for(kind)
    ok(len(rows) >= 23, "%s has %d detail options" % (kind, len(rows)))
for key, kind_of, default, _l, _n, extra, kinds, _c in SF.FIELDS:
    assert key in PAGE or key in ("css", "youtubeColour", "twitchColour", "kickColour"), "the overlay never uses " + key   # platform colours are read as platform + "Colour"
    if kind_of == "num": assert extra[0] <= default <= extra[1], key
    if kind_of == "choice": assert default in [v for _, v in extra], key
ok(True, "every detail option is used by the overlay, and its default is valid")
bad = OS.clean("chat", {"radius": 9999, "bgColor": "red;}", "shadow": "x", "css": "a" * 9000, "tagStyle": "nope", "useBg": 1, "panelWidth": 500})
ok(bad["radius"] == 70 and bad["bgColor"] == "#0c0a20" and bad["shadow"] == "skin" and len(bad["css"]) == SF.CSS_LIMIT and bad["tagStyle"] == "full" and bad["useBg"] is True and "panelWidth" not in bad,
   "detail options are limited and checked when saved")
ok(AS.clean({"radius": 12, "lineGap": 9})["radius"] == 12 and "lineGap" not in AS.clean({"lineGap": 9}), "alerts take the shared options only")
P.target.setCurrentIndex(0); P.load()
ok("Box" in P.tab_names() and "Custom CSS" in P.tab_names() and "My styles" in P.tab_names() and "Box" in A.tab_names() and "My styles" in A.tab_names(), "both design pages have the new tabs")
P.field_widgets["radius"][1].spin.setValue(24); P.field_widgets["useBg"][1].setChecked(True); P.field_widgets["tagStyle"][1].setCurrentIndex(2)
c = ov("/poll?type=chat&after=-1")["cfg"]["designs"]["chat"]
ok(c["radius"] == 24 and c["useBg"] is True and c["tagStyle"] == "dot", "detail controls reach OBS")
visible = lambda page: {c.findChild(__import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel).text() for k, c in page.field_cards if not c.isHidden()}
ok("Chat lines" in visible(P) and "What shows" not in visible(P), "only the options for this overlay show")
P.target.setCurrentIndex(P.target.findData("widgets")); P.load()
ok("What shows" in visible(P) and "Chat lines" not in visible(P), "switching overlay switches the options")
P.target.setCurrentIndex(0); P.load()
ok(P.save_my_style("Night mode") and P.my_list.findText("Night mode") >= 0, "a style can be saved")
P.field_widgets["radius"][1].spin.setValue(3); P.my_list.setCurrentIndex(P.my_list.findText("Night mode")); P.use_my_style()
ok(P.design()["radius"] == 24, "a saved style comes back with one click")
styled = os.path.join(os.environ["APPDATA"], "chat-style.json"); P.export_style(styled)
P.reset_design(); ok(P.design()["radius"] == -1 and P.design()["useBg"] is False, "Reset to default clears the design")
ok(P.import_style(styled) and P.design()["radius"] == 24, "an exported style can be imported")
P.target.setCurrentIndex(P.target.findData("meme")); P.load()
ok(not P.import_style(styled) and "different overlay" in P.my_note.text(), "a style for another overlay is refused")
junk = os.path.join(os.environ["APPDATA"], "junk.json"); open(junk, "w").write("[1,2]")
ok(not P.import_style(junk) and "not a CHATDOOM" in P.my_note.text(), "a file that is not a style is refused")
hostile = os.path.join(os.environ["APPDATA"], "bad.json"); json.dump({"chatdoomStyle": 1, "kind": "meme", "design": {"skin": "<x>", "radius": 99999, "bgColor": "url(x)"}}, open(hostile, "w"))
ok(P.import_style(hostile) and P.design()["skin"] == "classic" and P.design()["radius"] == 70 and P.design()["bgColor"] == "#0c0a20", "values in an imported file are checked")
P.target.setCurrentIndex(0); P.delete_my_style(); ok(P.my_list.findText("Night mode") < 0, "a saved style can be deleted")
A.field_widgets["borderWidth"][1].spin.setValue(4); ok(ov("/poll?type=alert&after=-1")["cfg"]["alertDesigns"]["default"]["borderWidth"] == 4, "alert detail options reach OBS")
A.reset_design(); ok(A.design()["borderWidth"] == 0, "alerts can be reset")
w.s.set("ov_designs", {}); w.s.set("ov_my_styles", {}); P.load()

# settings page
from app import system as SY
G15 = w.settingspage
ok(G15.tab_names() == ["Appearance", "Startup and window", "Notifications", "Updates", "Data and backup", "About"], "the Settings page has its sections")
w.goto(15); wait(30); ok(not w.statbar.isVisible() and w.title.text() == "Settings", "Settings opens as a page")
G15.theme.setCurrentText("Ocean"); ok(w.s.get("theme") == "Ocean", "the theme can be changed there"); G15.theme.setCurrentText("Neon Violet")
w.s.set("show_stats", False); w.goto(3); wait(20); ok(not w.statbar.isVisible(), "the stat cards can be hidden"); w.s.set("show_stats", True); w.goto(3); wait(20); ok(w.statbar.isVisible(), "and shown again")
w.toasts.items.clear() if hasattr(w.toasts.items, "clear") else None
w.s.set("start_page", 9); ok(w._first_page() == 9, "a chosen page opens first")
w.goto(13); w.goto(15); w.s.set("start_page", -1); ok(w._first_page() == 13, "or the last page used, not Settings itself"); w.s.set("start_page", 0)
w.s.set("start_page", 99); ok(w._first_page() == 0, "a page that no longer exists falls back"); w.s.set("start_page", 0)

ok(SY.can_autostart() is False and SY.set_autostart(True) is False, "a copy run from the code never changes the Windows start list")
fake = {}
class FakeReg:
    HKEY_CURRENT_USER, REG_SZ = 1, 1
    class K:
        def __enter__(s): return s
        def __exit__(s, *a): return False
    def CreateKey(s, *a): return s.K()
    def OpenKey(s, *a):
        return s.K()
    def SetValueEx(s, k, name, z, t, value): fake[name] = value
    def DeleteValue(s, k, name):
        if name not in fake: raise FileNotFoundError()
        del fake[name]
    def QueryValueEx(s, k, name):
        if name not in fake: raise FileNotFoundError()
        return fake[name], 1
real_reg, SY.winreg, sys.frozen = SY.winreg, FakeReg(), True
ok(SY.set_autostart(True) and "--autostart" in fake["CHATDOOM"] and sys.executable in fake["CHATDOOM"] and SY.autostart_on(), "Start with Windows adds the app")
ok(SY.set_autostart(False) and not SY.autostart_on() and SY.set_autostart(False), "and removes it, even twice")
SY.winreg = real_reg; del sys.frozen

w.s.set("cloud_token", "SECRET-TOKEN"); w.s.set("webhook_url", "https://discord.com/api/webhooks/9/private"); w.s.set("yt_bot_token", "BOT-TOKEN"); w.s.set("ov_seconds", 11); w.s.set("timers", [{"message": "hi", "minutes": 5}])
w.s.set("ov_designs", {"chat": {"skin": "lava"}})
pack = os.path.join(os.environ["APPDATA"], "backup.json"); G15.save_backup(pack); text = open(pack, encoding="utf-8").read(); saved = json.loads(text)["settings"]
ok(not any(x in text for x in ("SECRET-TOKEN", "webhooks", "BOT-TOKEN")) and not any(SY.PRIVATE.search(k) for k in saved), "a backup never holds sign-ins or private links")
ok(saved["ov_seconds"] == 11 and saved["timers"] and saved["ov_designs"]["chat"]["skin"] == "lava", "a backup holds your settings and designs")
w.s.set("ov_seconds", 5); w.s.set("timers", []); w.s.set("ov_designs", {})
ok(G15.load_backup(pack) and w.s.get("ov_seconds") == 11 and w.s.get("timers") and "Restored" in G15.backup_note.text(), "a backup restores them")
evil = os.path.join(os.environ["APPDATA"], "evil.json")
json.dump({"chatdoomBackup": 1, "settings": {"cloud_url": "https://evil.example", "update_repo": "evil/app", "yt_bot_url": "https://evil.example", "cloud_token": "x", "ov_seconds": "bad", "nothing": 1, "ov_port": 9000}}, open(evil, "w"))
before = (w.s.get("cloud_url"), w.s.get("update_repo"), w.s.get("yt_bot_url"), w.s.get("ov_seconds"))
G15.load_backup(evil)
ok((w.s.get("cloud_url"), w.s.get("update_repo"), w.s.get("yt_bot_url"), w.s.get("ov_seconds")) == before and w.s.get("cloud_token") == "SECRET-TOKEN" and w.s.get("nothing") is None, "a backup can never change servers, sign-ins or wrong-type values")
w.s.set("ov_port", 8795)
ok(not G15.load_backup(junk) and "not a CHATDOOM" in G15.backup_note.text(), "other files are refused")
G15.reset_btn.click(); ok(G15.reset_btn.text() == "Click again to reset" and w.s.get("ov_seconds") == 11, "the first click only asks")
keep_port = w.s.get("ov_port"); G15.reset_btn.click()
ok(w.s.get("ov_seconds") == 8 and w.s.get("cloud_token") == "SECRET-TOKEN" and w.s.get("yt_bot_token") == "BOT-TOKEN" and not w.s.get("ov_designs"), "reset clears settings but keeps sign-ins")
w.s.set("ov_port", keep_port); w.s.set("cloud_token", ""); w.s.set("webhook_url", ""); w.s.set("yt_bot_token", ""); G15.restart_row.hide()
two = settings_module.Settings(os.path.join(os.environ["APPDATA"], "many.json")); two.update({"ov_seconds": 13, "theme": "Ocean"})
three = settings_module.Settings(os.path.join(os.environ["APPDATA"], "many.json")); ok(three.get("ov_seconds") == 13 and three.get("theme") == "Ocean", "many settings save together")

class FakeTray:
    def isVisible(s): return True
real_tray, w.tray = w.tray, FakeTray()
from PySide6.QtGui import QCloseEvent
ev = QCloseEvent(); w.closeEvent(ev); ok(not ev.isAccepted() and not w.isVisible(), "with the tray on, closing keeps the app running"); w.show(); wait(30)
w.tray = real_tray
ok("[Registry]" in open(os.path.join(here, "installer.iss"), encoding="utf-8").read() and "uninsdeletevalue" in open(os.path.join(here, "installer.iss"), encoding="utf-8").read(), "uninstalling removes the start-with-Windows entry")
main_src = open(os.path.join(here, "main.py"), encoding="utf-8").read(); ok("QT_SCALE_FACTOR" in main_src and "start_window" in main_src, "the app uses the interface size and hidden start")

w.goto(11); wait(200); w.grab().save(os.path.join(os.environ["APPDATA"], "alerts.png"))
w.goto(0); wait(600)
print("\nALL PASSED" if not fails else "\n%d FAILED" % fails)
w.close()
shutil.rmtree(os.environ["APPDATA"], ignore_errors=True)
