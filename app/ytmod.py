"""YouTube auto-moderation through the CHATDOOM moderator bot.

CHATDOOM keeps reading your chat itself (free, no sign-in). When a message breaks one of your rules it asks the
moderator bot, which you added as a moderator of your channel, to remove it. You never sign in to Google.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import date

from PySide6.QtCore import QObject, QTimer, Signal

from .discord import run_bg
from .platforms import youtube_id
from .settings import data_dir

RULES = {"blocked word": "mod_del_blocked", "link": "mod_del_links", "spam": "mod_del_spam", "repeat": "mod_del_spam"}
UC = re.compile(r"^UC[\w-]{20,30}$")
LOG_MAX = 200
OUTCOMES = {"done": "Removed", "test": "Test mode, not removed", "missing": "Not found, it may be too old",
            "protected": "Kept, moderator", "limit": "Not removed, daily limit reached", "failed": "Failed"}


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
        self.in_flight = []               # the items of the request the bot is working on
        self.log_path = os.path.join(data_dir(), "moderation_log.json")
        self.log = self._load_log()       # what the bot did, newest last
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

    def can_post(self):
        """The bot answers in chat itself, like Nightbot, once the channel is verified."""
        return self.verified and bool(self.s.get("yt_bot_posts"))

    def say(self, text, video=""):
        vid = youtube_id(video or self.s.get("youtube") or "")
        if not vid:
            self.notice.emit("The bot needs your live link on the Connect page to post in chat.")
            return
        body = {"videoId": vid, "text": text, "limit": int(self.s.get("mod_budget"))}
        token = self.s.get("yt_bot_token")
        run_bg(self.bridge, "yt:say", lambda: bot_call(self.s, "POST", "/v1/say", body, token))

    def video_id(self):
        return youtube_id(self.s.get("youtube") or "")

    def forget(self):
        self.s.set("yt_bot_token", "")
        self.s.set("yt_channel_id", "")
        self.s.set("yt_channel_title", "")
        self.code, self.message = "", ""
        self.changed.emit()

    def is_bot(self, m):
        """The bot's own chat lines (the reasons it posts) must not be read aloud or moderated."""
        if m.platform != "youtube":
            return False
        channel = ((self.bot or {}).get("bot") or {}).get("channelId")
        handle = str(self.s.get("yt_bot_handle") or "").lstrip("@").lower()
        return bool(m.uid and m.uid == channel) or bool(handle and m.author.lstrip("@").lower() == handle)

    # ----- what was removed -----
    def _load_log(self):
        try:
            with open(self.log_path, encoding="utf-8") as f:
                entries = json.load(f)
            return entries[-LOG_MAX:] if isinstance(entries, list) else []
        except Exception:
            return []

    def _save_log(self):
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(self.log, f, ensure_ascii=False)
        except Exception:
            pass

    def clear_log(self):
        self.log = []
        self._save_log()
        self.changed.emit()

    def _record(self, items, res):
        """Keep the bot's real result for each item. An older cloud sends no per-item results."""
        results = {r.get("i"): r for r in res.get("results") or [] if isinstance(r, dict)}
        for i, it in enumerate(items):
            r = results.get(i, {})
            if not res.get("ok"):
                outcome = "Failed: %s" % str(res.get("error") or "unknown error")[:80]
            elif "results" not in res:
                outcome = "Sent to the bot"
            elif not r:
                outcome = "Not processed"
            else:
                outcome = OUTCOMES.get(r.get("outcome"), "Unknown")
                if r.get("detail"):
                    outcome += ": %s" % r["detail"]
            self.log.append({"at": time.time(), "author": it.get("author", ""), "text": it.get("text", ""),
                             "reason": it.get("reason", ""), "action": it.get("action", "delete"),
                             "seconds": it.get("seconds", 0), "outcome": outcome, "told": bool(r.get("told"))})
        self.log = self.log[-LOG_MAX:]
        self._save_log()

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
        body = {"videoId": vid, "items": items, "dryRun": bool(self.s.get("mod_dry_run")), "limit": int(self.s.get("mod_budget")),
                "explain": bool(self.s.get("mod_explain"))}
        self.in_flight = items
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
        elif tag == "yt:say":
            if status == 401:
                self.forget()
                self.notice.emit("Your channel verification expired. Verify it again on the YouTube mod page.")
            elif res.get("ok"):
                self.s.set("yt_used_day", str(date.today()))
                self.s.set("yt_used", int(res.get("usedToday", 0)))
                self.changed.emit()
            elif time.time() - self._last_error_note > 60:
                self._last_error_note = time.time()
                self.notice.emit("The bot could not post in chat: %s" % res.get("error", "unknown error"))
        elif tag == "yt:sweep":
            self.busy = False
            self._record(self.in_flight, res)
            self.in_flight = []
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
            self.changed.emit()
            if self.pending:
                self.timer.start()
