"""YouTube auto-moderation through the CHATDOOM moderator bot.

CHATDOOM keeps reading your chat itself (free, no sign-in). When a message breaks one of your rules it asks the
moderator bot, which you added as a moderator of your channel, to remove it. You never sign in to Google.
"""
import json
import re
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import date

from PySide6.QtCore import QObject, QTimer, Signal

from .discord import run_bg
from .platforms import youtube_id

RULES = {"blocked word": "mod_del_blocked", "link": "mod_del_links", "spam": "mod_del_spam", "repeat": "mod_del_spam"}
UC = re.compile(r"^UC[\w-]{20,30}$")


def bot_call(settings, method, path, body=None, token=None, timeout=75):
    """Calls the hosted bot. Returns a dict that always has 'status'. A sleeping free host can take ~50 s to wake."""
    url = settings.get("yt_bot_url").strip().rstrip("/") + path
    headers = {"User-Agent": "CHATDOOM-app", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read() or b"{}")
            out["status"] = r.status
            return out
    except urllib.error.HTTPError as e:
        try:
            out = json.loads(e.read())
        except Exception:
            out = {}
        out["status"] = e.code
        out.setdefault("error", "The bot answered with error %d" % e.code)
        return out
    except Exception as e:
        return {"status": 0, "ok": False, "error": "Cannot reach the CHATDOOM moderator bot (%s)" % str(e)[:60]}


class YtModerator(QObject):
    notice = Signal(str)
    changed = Signal()                    # the page refreshes itself when this fires

    def __init__(self, settings, bridge):
        super().__init__()
        self.s, self.bridge = settings, bridge
        self.pending = []
        self.busy = False
        self.offences = {}
        self.timed_out = {}
        self.bot = None                   # last answer of /v1/info
        self.bot_state = "unknown"        # unknown | waking | online | offline
        self.code = ""                    # verification code being shown
        self.code_exp = 0.0
        self.message = ""                 # last short status line for the page
        self._last_error_note = 0.0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.sweep)
        bridge.done.connect(self.on_done)

    # ----- state -----
    @property
    def verified(self):
        return bool(self.s.get("yt_bot_token"))

    def used_today(self):
        return int(self.s.get("yt_used")) if self.s.get("yt_used_day") == str(date.today()) else 0

    def video_id(self):
        return youtube_id(self.s.get("youtube") or "")

    def forget(self):
        self.s.set("yt_bot_token", "")
        self.s.set("yt_channel_id", "")
        self.s.set("yt_channel_title", "")
        self.code, self.message = "", ""
        self.changed.emit()

    # ----- talking to the bot -----
    def refresh_info(self):
        """Also wakes the bot if the free host put it to sleep."""
        if self.bot_state != "waking":
            self.bot_state = "waking"
            self.changed.emit()
        run_bg(self.bridge, "yt:info", lambda: bot_call(self.s, "GET", "/v1/info"))

    def start_verify(self):
        vid = self.video_id()
        if not vid:
            self.message = "Paste your YouTube live link on the Connect page first, then come back."
            self.changed.emit()
            return
        self.message = "Asking the bot for a code..."
        self.changed.emit()
        run_bg(self.bridge, "yt:vstart", lambda: bot_call(self.s, "POST", "/v1/verify/start", {"videoId": vid}))

    def check_verify(self):
        vid = self.video_id()
        if not vid or not self.code:
            return
        run_bg(self.bridge, "yt:vcheck", lambda: bot_call(self.s, "POST", "/v1/verify/check", {"videoId": vid}))

    # ----- called by the main window for every skipped message -----
    def flag(self, m, reason):
        key = RULES.get(reason)
        if not key or not self.s.get(key) or not self.verified or not self.s.get("yt_mod_on"):
            return False
        if not UC.match(m.uid or "") or m.kind != "chat":
            return False
        self.pending.append({"channelId": m.uid, "author": m.author, "text": m.text[:300], "reason": reason, "action": "delete"})
        if not self.timer.isActive():
            self.timer.start()
        return True

    def sweep(self):
        if self.busy:
            self.timer.start()
            return
        vid = self.video_id()
        if not self.pending or not vid or not self.verified:
            self.pending = []
            return
        items, self.pending = self.pending[:20], self.pending[20:]
        now = time.time()
        for it in list(items):                                   # repeat offenders get a time-out after the deletion
            ch = it["channelId"]
            dq = self.offences.setdefault(ch, deque())
            dq.append(now)
            while dq and now - dq[0] > 600:
                dq.popleft()
            if len(dq) >= int(self.s.get("mod_timeout_after")) and now >= self.timed_out.get(ch, 0):
                secs = int(self.s.get("mod_timeout_secs"))
                self.timed_out[ch] = now + secs
                items.append({"action": "timeout", "channelId": ch, "author": it["author"], "seconds": secs})
        body = {"videoId": vid, "items": items, "dryRun": bool(self.s.get("mod_dry_run")), "limit": int(self.s.get("mod_budget"))}
        token = self.s.get("yt_bot_token")
        self.busy = True
        run_bg(self.bridge, "yt:sweep", lambda: bot_call(self.s, "POST", "/v1/moderate", body, token))

    # ----- answers -----
    def on_done(self, tag, res):
        if not tag.startswith("yt:"):
            return
        status = res.get("status", 0)
        if tag == "yt:info":
            if status == 200 and res.get("ok"):
                self.bot_state = "online" if res.get("authorized") else "offline"
                self.bot = res
                bot = res.get("bot") or {}
                if bot.get("handle"):
                    self.s.set("yt_bot_handle", bot["handle"] if bot["handle"].startswith("@") else "@" + bot["handle"])
            else:
                self.bot_state = "offline"
            self.changed.emit()
        elif tag == "yt:vstart":
            if res.get("ok"):
                self.code = res["code"]
                self.code_exp = time.time() + int(res.get("expiresIn", 900))
                self.message = "Type the code in your live chat. CHATDOOM checks automatically."
            else:
                self.code = ""
                self.message = res.get("error", "Could not start verification.")
            self.changed.emit()
        elif tag == "yt:vcheck":
            if res.get("ok") and res.get("token"):
                self.s.set("yt_bot_token", res["token"])
                self.s.set("yt_channel_id", res.get("channelId", ""))
                self.s.set("yt_channel_title", res.get("channelTitle", ""))
                self.code = ""
                self.message = "Verified. The bot may now remove messages in your chat."
                self.notice.emit("Channel verified: %s" % (res.get("channelTitle") or "your channel"))
            elif status == 410:
                self.code = ""
                self.message = res.get("error", "The code expired. Press Verify again.")
            elif not res.get("waiting") and res.get("error"):
                self.message = res["error"]
            self.changed.emit()
        elif tag == "yt:sweep":
            self.busy = False
            if status == 401:
                self.forget()
                self.notice.emit("Your channel verification expired. Verify it again on the YouTube mod page.")
            elif res.get("ok"):
                for line in res.get("notes", []):
                    self.notice.emit(line)
                self.s.set("yt_used_day", str(date.today()))
                self.s.set("yt_used", int(res.get("usedToday", 0)))
                self.changed.emit()
            elif time.time() - self._last_error_note > 60:
                self._last_error_note = time.time()
                self.notice.emit("YouTube moderation problem: %s" % res.get("error", "unknown error"))
            if self.pending:
                self.timer.start()
