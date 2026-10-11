"""Platform OAuth and authenticated chat actions through the CHATDOOM cloud service."""
import json
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from .discord import run_bg
from .oauth_local import Loopback
from .platforms import youtube_id


def _request(url, method="GET", body=None, token=""):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": "CHATDOOM/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as error:
        try:
            result = json.loads(error.read())
        except Exception:
            result = {}
        result.setdefault("error", "Cloud server answered with HTTP %d" % error.code)
        result["status"] = error.code
        return result
    except Exception as error:
        return {"error": "Cannot reach CHATDOOM cloud (%s)" % str(error)[:80]}


class PlatformAuth(QObject):
    changed = Signal(str)
    notice = Signal(str)
    subscribers = Signal(object)

    SUPPORTED = ("youtube", "twitch")

    def __init__(self, settings, bridge):
        super().__init__()
        self.s, self.bridge = settings, bridge
        self.loops = {}
        bridge.done.connect(self.on_done)

    def _base(self):
        base = self.s.get("cloud_url").strip().rstrip("/")
        try:
            url = urllib.parse.urlsplit(base)
        except ValueError:
            return ""
        if url.scheme == "https" and url.netloc:
            return base
        if url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost"):
            return base
        return ""

    def _session_key(self, platform):
        return "platform_%s_session" % platform

    def _cancel_loop(self, platform):
        loop = self.loops.pop(platform, None)
        if loop:
            loop.cancel()

    def is_connected(self, platform):
        return bool(self.s.get(self._session_key(platform)))

    def display_name(self, platform):
        return self.s.get("platform_%s_name" % platform) or ""

    def refresh(self, platform):
        token = self.s.get(self._session_key(platform))
        if not token:
            self.changed.emit(platform)
            return
        if not self._base():
            self.notice.emit("Platform sign-in requires an HTTPS CHATDOOM cloud address.")
            return
        run_bg(self.bridge, "platform:account:%s" % platform,
               lambda: _request(self._base() + "/platform-auth/account", token=token))

    def login(self, platform):
        if platform not in self.SUPPORTED:
            self.notice.emit("Login is not supported for %s." % platform.title())
            return
        if not self._base():
            self.notice.emit("Platform sign-in requires an HTTPS CHATDOOM cloud address.")
            return
        loop = Loopback(self.bridge, "platform:return:%s" % platform)
        self.loops[platform] = loop
        return_url = loop.start()
        query = urllib.parse.urlencode({"platform": platform, "return": return_url})
        run_bg(self.bridge, "platform:start:%s" % platform,
               lambda: _request(self._base() + "/platform-auth/start?" + query))

    def disconnect(self, platform):
        token = self.s.get(self._session_key(platform))
        if not token:
            self.changed.emit(platform)
            return
        if not self._base():
            self.notice.emit("Platform sign-in requires an HTTPS CHATDOOM cloud address.")
            return
        run_bg(self.bridge, "platform:disconnect:%s" % platform,
               lambda: _request(self._base() + "/platform-auth/account", "DELETE", token=token))

    def send_message(self, platform, text):
        self._action(platform, "message", {
            "platform": platform,
            "text": text,
            "videoId": youtube_id(self.s.get("youtube") or "") if platform == "youtube" else "",
        })

    def create_poll(self, platform, question, options, duration):
        self._action(platform, "poll", {
            "platform": platform,
            "question": question,
            "options": options,
            "duration": duration,
            "videoId": youtube_id(self.s.get("youtube") or "") if platform == "youtube" else "",
        })

    def subscribe_eventsub(self, session_id):
        token = self.s.get(self._session_key("twitch"))
        if not token:
            return {"error": "Sign in to Twitch before starting alert subscriptions."}
        if not self._base():
            return {"error": "Twitch alert subscriptions require an HTTPS CHATDOOM cloud address."}
        return _request(self._base() + "/platform-auth/eventsub", "POST", {"sessionId": session_id}, token)

    def poll_youtube_subscribers(self, since):
        token = self.s.get(self._session_key("youtube"))
        if not token:
            return {"error": "Sign in to YouTube before checking subscriber alerts."}
        if not self._base():
            return {"error": "YouTube subscriber alerts require an HTTPS CHATDOOM cloud address."}
        run_bg(self.bridge, "platform:youtube-subscribers",
               lambda: _request(self._base() + "/platform-auth/youtube-subscribers", "POST", {"since": since}, token))

    def _action(self, platform, action, body):
        if platform not in self.SUPPORTED:
            self.notice.emit("Chat actions are not available for %s." % platform.title())
            return
        token = self.s.get(self._session_key(platform))
        if not token:
            self.notice.emit("Sign in to %s on the Connect page before sending." % platform.title())
            return
        if not self._base():
            self.notice.emit("Platform sign-in requires an HTTPS CHATDOOM cloud address.")
            return
        run_bg(self.bridge, "platform:action", lambda: _request(
            self._base() + "/platform-auth/" + action, "POST", body, token))

    def on_done(self, tag, result):
        if tag.startswith("platform:start:"):
            platform = tag.rsplit(":", 1)[1]
            auth_url = result.get("authorizeUrl")
            if result.get("error") or not auth_url:
                self._cancel_loop(platform)
                self.notice.emit("Could not start %s login: %s" % (platform.title(), result.get("error", "no login URL returned")))
            elif not QDesktopServices.openUrl(QUrl(auth_url)):
                self._cancel_loop(platform)
                self.notice.emit("Could not open your browser for %s login." % platform.title())
            return

        if tag.startswith("platform:return:"):
            platform = tag.rsplit(":", 1)[1]
            self._cancel_loop(platform)
            if result.get("ok") != "1" or not result.get("ticket"):
                self.notice.emit("%s login was not completed%s." % (
                    platform.title(), ": " + result.get("error", "") if result.get("error") else ""))
                return
            run_bg(self.bridge, "platform:redeem:%s" % platform,
                   lambda: _request(self._base() + "/platform-auth/redeem", "POST", {"ticket": result["ticket"]}))
            return

        if tag.startswith("platform:redeem:"):
            platform = tag.rsplit(":", 1)[1]
            if result.get("error") or not result.get("session"):
                self.notice.emit("%s login failed: %s" % (platform.title(), result.get("error", "invalid login response")))
                return
            self.s.set(self._session_key(platform), result["session"])
            self.s.set("platform_%s_name" % platform, result.get("displayName", ""))
            self.changed.emit(platform)
            self.notice.emit("Connected %s as %s." % (platform.title(), result.get("displayName", "your account")))
            return

        if tag.startswith("platform:account:"):
            platform = tag.rsplit(":", 1)[1]
            if result.get("status") == 401:
                self.s.set(self._session_key(platform), "")
                self.s.set("platform_%s_name" % platform, "")
                self.notice.emit("%s login expired. Sign in again to send chat or polls." % platform.title())
            elif result.get("error"):
                self.notice.emit("%s account check failed: %s" % (platform.title(), result["error"]))
            else:
                self.s.set("platform_%s_name" % platform, result.get("displayName", ""))
            self.changed.emit(platform)
            return

        if tag.startswith("platform:disconnect:"):
            platform = tag.rsplit(":", 1)[1]
            if result.get("error") and result.get("status") != 401:
                self.notice.emit("Could not disconnect %s: %s" % (platform.title(), result["error"]))
                return
            self.s.set(self._session_key(platform), "")
            self.s.set("platform_%s_name" % platform, "")
            self.changed.emit(platform)
            self.notice.emit("Disconnected %s." % platform.title())
            return

        if tag == "platform:action":
            if result.get("error"):
                self.notice.emit("Chat action failed: %s" % result["error"])
            else:
                self.notice.emit("Chat action sent.")
            return

        if tag == "platform:youtube-subscribers":
            if result.get("status") == 401:
                self.s.set(self._session_key("youtube"), "")
                self.s.set("platform_youtube_name", "")
                self.changed.emit("youtube")
                self.notice.emit("YouTube login expired. Sign in again to restore subscriber alerts.")
            self.subscribers.emit(result)
