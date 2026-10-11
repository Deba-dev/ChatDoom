"""Chat readers for YouTube (no login), Twitch (anonymous read) and Kick (public chat)."""
import asyncio
import json
import re
import threading
import time
import urllib.request

from PySide6.QtCore import QObject, Signal

from .models import Message

PUSHER_URL = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"


# ---------- pure parsers (easy to test) ----------
def strip_twitch_emotes(text, emotes_tag):
    """Remove Twitch emote words (Kappa, LUL ...) using the positions Twitch sends in the 'emotes' tag."""
    chars = list(text)
    for group in emotes_tag.split("/"):
        for r in group.partition(":")[2].split(","):
            a, _, b = r.partition("-")
            if a.isdigit() and b.isdigit():
                for i in range(int(a), min(int(b), len(chars) - 1) + 1):
                    chars[i] = ""
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def parse_twitch_line(line):
    m = re.match(r"^(?:@(?P<tags>\S+) )?:(?P<nick>[^!\s]+)![^ ]+ PRIVMSG #\S+ :(?P<msg>.*)$", line)
    if not m:
        return None
    tags = {}
    for part in (m.group("tags") or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            tags[k] = v.replace("\\s", " ").replace("\\:", ";")
    text = m.group("msg")
    if text.startswith("\x01ACTION ") and text.endswith("\x01"):
        text = text[8:-1]
    # Twitch emote names are useful speech text; keep them instead of dropping them.
    badges = tags.get("badges", "")
    mod = tags.get("mod") == "1" or "broadcaster/" in badges or "moderator/" in badges
    author = tags.get("display-name") or m.group("nick")
    bits = tags.get("bits")
    if bits:
        return Message("twitch", author, text, "super", "%s bits" % bits, mod, tags.get("user-id", ""),
                       event_id=tags.get("id", ""))
    return Message("twitch", author, text, "chat", "", mod, tags.get("user-id", ""),
                   event_id=tags.get("id", ""))


def parse_kick_event(event, raw):
    if not event.endswith("ChatMessageEvent"):
        return None
    d = json.loads(raw) if isinstance(raw, str) else raw
    text = re.sub(r"\[emote:\d+:([^\]]*)\]", r"\1", d.get("content", "")).strip()
    sender = d.get("sender") or {}
    badges = [b.get("type", "") for b in (sender.get("identity") or {}).get("badges", [])]
    mod = any(b in ("moderator", "broadcaster") for b in badges)
    return Message("kick", sender.get("username", "?"), text, "chat", "", mod, str(sender.get("id", "")),
                   bool(sender.get("is_bot")))


def youtube_id(s):
    s = s.strip()
    m = re.search(r"(?:v=|youtu\.be/|live/|embed/)([\w-]{11})", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[\w-]{11}", s) else None


# ---------- sources ----------
class Hub(QObject):
    message = Signal(object)            # Message
    status = Signal(str, str, bool)     # platform, text, connected


class Source:
    name = "?"

    def __init__(self, hub):
        self.hub = hub
        self.stop_evt = threading.Event()
        self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, *args):
        if self.running:
            return
        self.stop_evt = threading.Event()
        self.thread = threading.Thread(target=self._safe, args=args, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_evt.set()

    def _status(self, text, ok=False):
        self.hub.status.emit(self.name, text, ok)

    def _safe(self, *args):
        try:
            self._run(*args)
        except Exception as e:
            self._status("Error: %s" % str(e)[:90])
        else:
            self._status("Disconnected")


class YouTubeSource(Source):
    name = "youtube"

    def _run(self, target):
        vid = youtube_id(target)
        if not vid:
            return self._status("Enter a valid live link or video ID")
        try:
            import pytchat
        except Exception as e:
            return self._status("Could not load YouTube chat support: %s" % str(e)[:60])

        retry_delay = 2
        connected_once = False
        while not self.stop_evt.is_set():
            self._status("Reconnecting..." if connected_once else "Connecting...")
            try:
                chat = pytchat.create(video_id=vid, interruptable=False)
            except Exception as e:
                if not connected_once:
                    return self._status("Could not connect (is it live?) %s" % str(e)[:60])
                self._status("Reconnecting... (%s)" % str(e)[:40])
                self.stop_evt.wait(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
                continue

            connected_once = True
            connected_at = time.monotonic()
            self._status("Connected", True)
            first = True
            try:
                while not self.stop_evt.is_set() and chat.is_alive():
                    items = chat.get().sync_items()
                    if first:
                        first = False
                    else:
                        for c in items:
                            if c.type in ("textMessage", "superChat", "superSticker", "newSponsor",
                                          "memberMilestoneChat", "membershipGiftingEvent", "giftMembershipReceivedEvent"):
                                member = c.type in ("newSponsor", "memberMilestoneChat", "membershipGiftingEvent",
                                                    "giftMembershipReceivedEvent")
                                paid = c.type in ("superChat", "superSticker")
                                a = c.author
                                self.hub.message.emit(Message(
                                    "youtube", a.name, c.message or ("became a channel member" if member else ""),
                                    "member" if member else ("super" if paid else "chat"),
                                    getattr(c, "amountString", "") if paid else "",
                                    bool(getattr(a, "isChatModerator", False) or getattr(a, "isChatOwner", False)),
                                    str(getattr(a, "channelId", "") or ""),
                                    bool(getattr(a, "isChatBot", False)),
                                    str(getattr(c, "id", "") or getattr(c, "messageId", "") or "")))
                    self.stop_evt.wait(1)
            except Exception as e:
                if not self.stop_evt.is_set():
                    self._status("Reconnecting... (%s)" % str(e)[:40])
            finally:
                try:
                    chat.terminate()
                except Exception:
                    pass

            if self.stop_evt.is_set():
                break
            if time.monotonic() - connected_at >= 60:
                retry_delay = 2
            self._status("Reconnecting...")
            self.stop_evt.wait(retry_delay)
            retry_delay = min(retry_delay * 2, 30)


class _AsyncSource(Source):
    def _run(self, *args):
        asyncio.run(self._loop(*args))

    async def _sleep(self, secs):
        for _ in range(int(secs * 10)):
            if self.stop_evt.is_set():
                return
            await asyncio.sleep(0.1)


class TwitchSource(_AsyncSource):
    name = "twitch"

    async def _loop(self, channel):
        import websockets
        channel = channel.strip().lstrip("#").lower()
        if not channel:
            return self._status("Enter a channel name")
        while not self.stop_evt.is_set():
            self._status("Connecting...")
            try:
                async with websockets.connect("wss://irc-ws.chat.twitch.tv:443") as ws:
                    await ws.send("CAP REQ :twitch.tv/tags")
                    await ws.send("PASS SCHMOOPIIE")
                    await ws.send("NICK justinfan%d" % (10000 + id(self) % 80000))
                    await ws.send("JOIN #" + channel)
                    self._status("Connected", True)
                    while not self.stop_evt.is_set():
                        try:
                            data = await asyncio.wait_for(ws.recv(), 1)
                        except asyncio.TimeoutError:
                            continue
                        for line in data.split("\r\n"):
                            if line.startswith("PING"):
                                await ws.send("PONG :tmi.twitch.tv")
                            else:
                                m = parse_twitch_line(line)
                                if m:
                                    self.hub.message.emit(m)
            except Exception as e:
                self._status("Reconnecting... (%s)" % str(e)[:40])
            await self._sleep(3)


class KickSource(_AsyncSource):
    name = "kick"

    def _lookup_room(self, slug):
        req = urllib.request.Request(
            "https://kick.com/api/v2/channels/" + slug,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                     "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return str(json.load(r)["chatroom"]["id"])

    async def _loop(self, slug, room=""):
        import websockets
        slug = slug.strip().lower()
        room = (room or "").strip()
        if not slug and not room:
            return self._status("Enter a channel name")
        if not room:
            self._status("Looking up chat room...")
            try:
                room = await asyncio.get_running_loop().run_in_executor(None, self._lookup_room, slug)
            except Exception:
                return self._status("Kick blocked the lookup - paste the chatroom ID below")
        while not self.stop_evt.is_set():
            self._status("Connecting...")
            try:
                async with websockets.connect(PUSHER_URL) as ws:
                    while not self.stop_evt.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), 1)
                        except asyncio.TimeoutError:
                            continue
                        msg = json.loads(raw)
                        ev = msg.get("event", "")
                        if ev == "pusher:connection_established":
                            await ws.send(json.dumps({"event": "pusher:subscribe",
                                                      "data": {"auth": "", "channel": "chatrooms.%s.v2" % room}}))
                        elif ev == "pusher_internal:subscription_succeeded":
                            self._status("Connected", True)
                        elif ev == "pusher:ping":
                            await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                        else:
                            m = parse_kick_event(ev, msg.get("data", "{}"))
                            if m:
                                self.hub.message.emit(m)
            except Exception as e:
                self._status("Reconnecting... (%s)" % str(e)[:40])
            await self._sleep(3)
