"""Chat readers for YouTube (no login), Twitch (anonymous read) and Kick (public chat)."""
import asyncio
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import deque

from PySide6.QtCore import QObject, Signal

from . import logs
from .models import Message
from .yt_innertube import InnerTubeChat, parse_actions

PUSHER_URL = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"

CHAT_LOG = logs.get("chat")
GAVE_UP = ("Could not", "Enter a", "Error", "Kick blocked")   # a reader stopped by itself with this status: keep it on the card


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


def twitch_emotes(text, emotes_tag):
    """{"Kappa": image address} for the emotes Twitch marked in a message."""
    found = {}
    for group in (emotes_tag or "").split("/"):
        emote, _, spots = group.partition(":")
        first = spots.split(",")[0]
        a, _, b = first.partition("-")
        if emote and a.isdigit() and b.isdigit():
            word = text[int(a):int(b) + 1]
            if word:
                found[word] = "https://static-cdn.jtvnw.net/emoticons/v2/%s/default/dark/1.0" % urllib.parse.quote(emote, safe="")
    return found


def youtube_text(chat):
    """pytchat turns every emoji into its :name:. The real emoji is in messageEx, so the chat shows what the viewer sent.
    YouTube's own picture emotes have no emoji character: they stay as :name: with their image address."""
    parts = getattr(chat, "messageEx", None)
    if not isinstance(parts, list) or not parts:
        return chat.message or "", {}
    text, emotes = "", {}
    for part in parts:
        if isinstance(part, str):
            text += part
        elif isinstance(part, dict):
            emoji = str(part.get("id") or "")
            if emoji and not emoji.isascii() and len(emoji) <= 12:
                text += emoji
                continue
            word = str(part.get("txt") or "")
            url = str(part.get("url") or "")
            text += word
            if word and url.startswith("https://"):
                emotes[word] = url
    return text, emotes


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
    emotes = twitch_emotes(text, tags.get("emotes", ""))
    if bits:
        return Message("twitch", author, text, "super", "%s bits" % bits, mod, tags.get("user-id", ""),
                       event_id=tags.get("id", ""), emotes=emotes)
    return Message("twitch", author, text, "chat", "", mod, tags.get("user-id", ""),
                   event_id=tags.get("id", ""), emotes=emotes)


def kick_text(content):
    """Kick writes emotes as [emote:37:KEKW]: the text keeps the name, and the picture address is kept for the feed."""
    content = content or ""
    emotes = {name: "https://files.kick.com/emotes/%s/fullsize" % eid
              for eid, name in re.findall(r"\[emote:(\d+):([^\]]*)\]", content) if name}
    return re.sub(r"\[emote:\d+:([^\]]*)\]", r"\1", content).strip(), emotes


def kick_cloud_message(item):
    """A chat message from the cloud's Kick webhook queue (Kick's official chat.message.sent event)."""
    text, emotes = kick_text(item.get("text"))
    return Message("kick", item.get("name") or "?", text, "chat", "", bool(item.get("mod")), str(item.get("uid") or ""),
                   False, str(item.get("id") or ""), emotes=emotes)


def parse_kick_event(event, raw):
    if not event.endswith("ChatMessageEvent"):
        return None
    d = json.loads(raw) if isinstance(raw, str) else raw
    text, emotes = kick_text(d.get("content", ""))
    sender = d.get("sender") or {}
    badges = [b.get("type", "") for b in (sender.get("identity") or {}).get("badges", [])]
    mod = any(b in ("moderator", "broadcaster") for b in badges)
    return Message("kick", sender.get("username", "?"), text, "chat", "", mod, str(sender.get("id", "")),
                   bool(sender.get("is_bot")), str(d.get("id", "") or ""), emotes=emotes)


def youtube_id(s):
    s = s.strip()
    m = re.search(r"(?:v=|youtu\.be/|live/|embed/)([\w-]{11})", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[\w-]{11}", s) else None


# ---------- sources ----------
class Hub(QObject):
    message = Signal(object)            # Message
    status = Signal(str, str, bool)     # stream key ("youtube", or "extra:N" for an added stream), text, connected


class Source:
    name = "?"

    def __init__(self, hub, key=None):
        self.hub = hub
        self.key = key or self.name     # status and messages are tagged with this, so several streams of one platform can run
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
        if text != getattr(self, "_last_status", None):
            self._last_status = text
            CHAT_LOG.log(logging.WARNING if text.startswith(("Error", "Could not")) else logging.INFO, "%s %s: %s", type(self).__name__, self.key, text)
        self.hub.status.emit(self.key, text, ok)

    def _emit(self, m):
        m.stream = self.key
        self.hub.message.emit(m)

    def _safe(self, *args):
        try:
            self._run(*args)
        except Exception as e:
            CHAT_LOG.warning("%s %s stopped with an error", type(self).__name__, self.key, exc_info=True)
            self._status("Error: %s" % str(e)[:90])
        else:
            last = getattr(self, "_last_status", "") or ""
            if not self.stop_evt.is_set() and last.startswith(GAVE_UP):
                self._status(last)               # sent last, so the card keeps the reason (and its Retry button)
            else:
                self._status("Disconnected")


def pytchat_message(c):
    """A pytchat chat item as a Message, or None for item types we don't read."""
    if c.type not in ("textMessage", "superChat", "superSticker", "newSponsor", "memberMilestoneChat",
                      "membershipGiftingEvent", "giftMembershipReceivedEvent"):
        return None
    member = c.type in ("newSponsor", "memberMilestoneChat", "membershipGiftingEvent", "giftMembershipReceivedEvent")
    paid = c.type in ("superChat", "superSticker")
    a = c.author
    words, emotes = youtube_text(c)
    return Message(
        "youtube", a.name, words or ("became a channel member" if member else ""),
        "member" if member else ("super" if paid else "chat"),
        getattr(c, "amountString", "") if paid else "",
        bool(getattr(a, "isChatModerator", False) or getattr(a, "isChatOwner", False)),
        str(getattr(a, "channelId", "") or ""),
        bool(getattr(a, "isChatBot", False)),
        str(getattr(c, "id", "") or getattr(c, "messageId", "") or ""), emotes=emotes)


class InnerTubeReader:
    """Reader A (default): our own youtube.com poller."""
    label = "A"

    def __init__(self, vid):
        self.chat = InnerTubeChat(vid)

    @property
    def wait(self):
        return self.chat.wait

    def open(self):
        self.chat.open()

    def poll(self):
        return parse_actions(self.chat.poll(), youtube_text)

    def close(self):
        pass


class PytchatReader:
    """Reader C (last resort): pytchat, archived in 2022, kept only as a backup."""
    label = "C"
    wait = 1

    def __init__(self, vid):
        self.vid, self.chat = vid, None

    def open(self):
        import pytchat
        self.chat = pytchat.create(video_id=self.vid, interruptable=False)

    def poll(self):
        if not self.chat.is_alive():
            raise ConnectionError("pytchat stopped")
        out = []
        for c in self.chat.get().sync_items():
            m = pytchat_message(c)
            if m is not None:
                ts = getattr(c, "timestamp", None)
                out.append((m, int(ts) * 1000 if isinstance(ts, (int, float)) and ts else None))
        return out

    def close(self):
        try:
            if self.chat is not None:
                self.chat.terminate()
        except Exception:
            pass


class YouTubeSource(Source):
    """Tries the readers in order and moves to the next one when a reader keeps failing or goes silent.
    Reader B (the official streamList API) would slot in between A and C; it needs grpcio, so it is not added yet."""
    name = "youtube"
    READERS = (InnerTubeReader, PytchatReader)
    FAILS = 3              # failures in a row before switching
    QUIET = 90             # seconds without a single message before trying the next reader
    SEEN = 3000            # message ids remembered, so a reader switch never repeats a message
    RETRY = 2              # first wait before reconnecting, doubled up to 30 s

    def __init__(self, hub, key=None):
        super().__init__(hub, key)
        self.reader = ""

    def _run(self, target):
        vid = youtube_id(target)
        if not vid:
            return self._status("Enter a valid live link or video ID")
        readers, idx = self.READERS, 0
        seen, order = set(), deque()
        newest = [0]                     # newest message time seen, in microseconds
        state = {"connected": False}
        fails, quiet_rounds, first_errors = 0, 0, []
        retry_delay = self.RETRY

        def take(items, opening):
            """Emits new messages. A reader's first batch is chat history: on the very first connect it is only
            remembered; after a switch, anything newer than what was already read is passed on."""
            got = 0
            for m, ts in items:
                mid = m.event_id
                if mid and mid in seen:
                    continue
                if not opening or (state["connected"] and ts is not None and ts > newest[0]):
                    self._emit(m)
                    got += 1
                if mid:
                    seen.add(mid)
                    order.append(mid)
                    if len(order) > self.SEEN:
                        seen.discard(order.popleft())
                if ts:
                    newest[0] = max(newest[0], ts)
            return got

        while not self.stop_evt.is_set():
            reader = readers[idx](vid)
            self.reader = reader.label
            self._status("Reconnecting..." if state["connected"] else "Connecting...")
            try:
                reader.open()
                take(reader.poll(), True)
            except Exception as e:
                reader.close()
                CHAT_LOG.info("YouTube reader %s could not connect: %s", reader.label, e)
                if not state["connected"]:
                    first_errors.append(str(e))
                    if len(first_errors) >= len(readers):
                        return self._status("Could not connect (is it live?) %s" % first_errors[0][:60])
                    idx = (idx + 1) % len(readers)
                    continue
                fails += 1
                if fails >= self.FAILS:
                    idx, fails = self._switch(idx, "%d failures" % fails), 0
                self._status("Reconnecting... (%s)" % str(e)[:40])
                self.stop_evt.wait(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
                continue

            state["connected"], first_errors = True, []
            connected_at = last_msg = time.monotonic()
            self._status("Connected (reader %s)" % reader.label, True)
            CHAT_LOG.info("YouTube reader %s connected", reader.label)
            switched = False
            try:
                while not self.stop_evt.is_set():
                    if take(reader.poll(), False):
                        last_msg, quiet_rounds = time.monotonic(), 0
                    elif time.monotonic() - last_msg >= self.QUIET and quiet_rounds < len(readers):
                        quiet_rounds += 1                 # one round through the readers per quiet spell; after that chat is just quiet
                        idx, switched = self._switch(idx, "no messages for %ds" % self.QUIET), True
                        break
                    self.stop_evt.wait(reader.wait)
                fails = 0
            except Exception as e:
                if not self.stop_evt.is_set():
                    fails += 1
                    CHAT_LOG.info("YouTube reader %s failed (%d in a row): %s", reader.label, fails, e)
                    self._status("Reconnecting... (%s)" % str(e)[:40])
                    if fails >= self.FAILS:
                        idx, fails = self._switch(idx, "%d failures" % fails), 0
            finally:
                reader.close()

            if self.stop_evt.is_set():
                break
            if switched:
                continue
            if time.monotonic() - connected_at >= 60:
                retry_delay = self.RETRY
            self.stop_evt.wait(retry_delay)
            retry_delay = min(retry_delay * 2, 30)

    def _switch(self, idx, why):
        nxt = (idx + 1) % len(self.READERS)
        if nxt != idx:
            CHAT_LOG.warning("YouTube reader %s -> %s (%s)", self.READERS[idx].label, self.READERS[nxt].label, why)
        return nxt


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
                                    self._emit(m)
            except Exception as e:
                self._status("Reconnecting... (%s)" % str(e)[:40])
            await self._sleep(3)


class KickSource(_AsyncSource):
    """Kick chat. When you are signed in to Kick and this is your own channel, it reads through Kick's official webhooks
    (via the CHATDOOM cloud). Otherwise, or when that fails, it uses Kick's unofficial Pusher chat as before."""
    name = "kick"
    POLL = 2              # seconds between reads of the cloud queue
    FAILS = 3             # failed reads in a row before falling back to Pusher

    def __init__(self, hub, key=None, cloud=None):
        super().__init__(hub, key)
        self.cloud = cloud    # PlatformAuth, or None (added streams of other channels)
        self.reader = ""
        self.hint = ""        # added to the backup reader's Connected status

    async def _official(self, slug):
        """Reads through the cloud. True when the streamer disconnected, False to fall back to Pusher."""
        run = lambda f, *a: asyncio.get_running_loop().run_in_executor(None, f, *a)
        self._status("Connecting...")
        res = await run(self.cloud.kick_subscribe, slug) or {}
        if not res.get("ok"):
            why = "not the signed-in channel" if res.get("notMine") else (res.get("error") or "no answer")
            CHAT_LOG.info("Kick official chat not used for %s: %s", slug, why)
            if res.get("needsLogin"):
                self.hint = " (sign in to Kick again for official chat)"
            return False
        after, fails, resubscribed = int(res.get("latest") or 0), 0, False
        self.reader = "official"
        self._status("Connected (official)", True)
        CHAT_LOG.info("Kick official chat connected for %s", slug)
        try:
            while not self.stop_evt.is_set():
                data = await run(self.cloud.kick_chat, after) or {}
                if data.get("resubscribe") and not resubscribed:       # the subscription lapsed: renew it once
                    resubscribed = True
                    again = await run(self.cloud.kick_subscribe, slug) or {}
                    if again.get("ok"):
                        continue
                if data.get("error"):
                    fails += 1
                    CHAT_LOG.info("Kick official chat read failed (%d in a row): %s", fails, data.get("error"))
                    if fails >= self.FAILS:
                        CHAT_LOG.warning("Kick official chat -> Pusher backup (%s)", data.get("error"))
                        return False
                else:
                    fails, resubscribed = 0, False
                    for item in data.get("messages") or ():
                        m = kick_cloud_message(item)
                        if m.text:
                            self._emit(m)
                    after = int(data.get("latest") or after)
                await self._sleep(self.POLL)
            return True
        finally:
            if self.stop_evt.is_set():
                try:
                    await run(self.cloud.kick_unsubscribe)          # stop Kick sending this chat to the cloud
                except Exception:
                    pass

    def _lookup_room(self, slug):
        req = urllib.request.Request(
            "https://kick.com/api/v2/channels/" + slug,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                     "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return str(json.load(r)["chatroom"]["id"])

    async def _loop(self, slug, room=""):
        slug = slug.strip().lower()
        room = (room or "").strip()
        if not slug and not room:
            return self._status("Enter a channel name")
        if slug and self.cloud is not None and self.cloud.is_connected("kick"):
            try:
                if await self._official(slug):
                    return
            except Exception as e:
                CHAT_LOG.warning("Kick official chat failed, using Pusher: %s", e)
        if not self.stop_evt.is_set():
            self.reader = "backup"
            await self._pusher(slug, room)

    async def _pusher(self, slug, room):
        """The backup: Kick's website chat feed (unofficial, may change without notice)."""
        import websockets
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
                            self._status("Connected" + self.hint, True)
                        elif ev == "pusher:ping":
                            await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                        else:
                            m = parse_kick_event(ev, msg.get("data", "{}"))
                            if m:
                                self._emit(m)
            except Exception as e:
                self._status("Reconnecting... (%s)" % str(e)[:40])
            await self._sleep(3)


SOURCES = {"youtube": YouTubeSource, "twitch": TwitchSource, "kick": KickSource}
