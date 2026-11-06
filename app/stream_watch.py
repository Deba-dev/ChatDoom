"""Finds what the signed-in accounts are streaming, like OBS's Manage Broadcast: fills in the cards, adds a card for a second stream
(a Shorts stream beside the long one) and connects them, so the streamer only has to go live."""
from PySide6.QtCore import QTimer

from .platforms import youtube_id

FAST_CHECK_MS = 120000      # Twitch and Kick lookups are free
YOUTUBE_CHECK_MS = 300000   # every YouTube lookup comes out of the shared daily allowance
WATCH_LINK = "https://www.youtube.com/watch?v="
FORMATS = (("Long format", "long"), ("Shorts", "shorts"))
FORMAT_NAMES = {"long": "Long", "shorts": "Shorts"}


def plan_youtube(live, main_id, main_auto_id, main_running, main_text, extras):
    """Where each live stream goes. extras: [(video id, card key, added by detection, connected)].
    A link typed by hand is never replaced: it may be someone else's stream. Returns (stream for the main card or None, streams to add,
    card keys to remove)."""
    ids = {s["id"] for s in live}
    taken = {main_id} | {video for video, *_ in extras}
    waiting = sorted((s for s in live if s["id"] not in taken), key=lambda s: s.get("format") == "shorts")   # long format takes the main card
    main_free = not main_running and main_id not in ids and (not main_text or main_id == main_auto_id)
    main = waiting.pop(0) if main_free and waiting else None
    gone = [key for video, key, auto, running in extras if auto and video not in ids and not running]
    return main, waiting, gone


def stream_format(settings, info):
    """The streamer's own choice wins over the guess."""
    saved = settings.get("yt_stream_formats")
    chosen = saved.get(info.get("id")) if isinstance(saved, dict) else ""
    return chosen or info.get("format") or "long"


class StreamWatch:
    """Mixed into the main window."""

    def _start_stream_watch(self):
        self._auto_connected = set()
        self._told_kick_login = False
        self.fast_watch = QTimer(self)
        self.fast_watch.setInterval(FAST_CHECK_MS)
        self.fast_watch.timeout.connect(lambda: self.check_streams(("twitch", "kick")))
        self.fast_watch.start()
        self.youtube_watch = QTimer(self)
        self.youtube_watch.setInterval(YOUTUBE_CHECK_MS)
        self.youtube_watch.timeout.connect(lambda: self.check_streams(("youtube",)))
        self.youtube_watch.start()
        self.platform_auth.streams.connect(self.on_live_streams)
        QTimer.singleShot(2500, self.check_streams)

    def check_streams(self, platforms=("youtube", "twitch", "kick")):
        if self.s.get("auto_detect_streams"):
            for platform in platforms:
                self.platform_auth.check_streams(platform)

    def on_live_streams(self, platform, result):
        if result.get("error"):
            return                                # the next check tries again; a sign-in problem is reported by the account check
        if platform == "youtube":
            self._sync_youtube(result)
        else:
            self._sync_channel(platform, result)
        self._streams_changed()

    # ----- YouTube: one account, any number of streams -----
    def _sync_youtube(self, result):
        live = [s for s in result.get("streams") or [] if s.get("id") and s.get("live")]
        card = self.cards["youtube"]
        extras = [(youtube_id(c.edit.text()) or "", c.key, c.auto, c.source.running) for c in self.extra_cards.values() if c.platform() == "youtube"]
        main, added, gone = plan_youtube(live, youtube_id(card.edit.text()) or "", self.s.get("youtube_auto_id") or "", card.source.running,
                                         card.edit.text().strip(), extras)
        for key in gone:
            self._remove_stream(self.extra_cards[key])
        if main:
            link = WATCH_LINK + main["id"]
            card.edit.setText(link)
            self.s.set("youtube", link)
            self.s.set("youtube_auto_id", main["id"])
        for stream in added:
            self._add_stream({"id": self._next_stream_id(), "platform": "youtube", "target": WATCH_LINK + stream["id"], "auto": True})
        account = result.get("account") or self.platform_auth.display_name("youtube")
        by_id = {s["id"]: s for s in live}
        for c in [card] + [c for c in self.extra_cards.values() if c.platform() == "youtube"]:
            stream = by_id.get(youtube_id(c.edit.text()) or "")
            c.set_detected(dict(stream, account=account) if stream else None)
            if stream:
                self._connect_once(c, "youtube:" + stream["id"])

    # ----- Twitch and Kick: the account is the channel -----
    def _sync_channel(self, platform, result):
        if result.get("needsLogin"):
            if not self._told_kick_login:
                self._told_kick_login = True
                self.platform_auth.notice.emit("Sign out and sign in to %s again so CHATDOOM can see when you go live." % platform.title())
            return
        channel = result.get("channel") or ""
        if not channel:
            return
        self.s.set("platform_%s_login" % platform, channel)
        card = self.cards[platform]
        typed = card.edit.text().strip().lstrip("#")
        if not typed and not card.source.running:
            card.edit.setText(channel)
            self.s.set(platform, channel)
            typed = channel
        own = typed.lower() == channel.lower()
        live = (result.get("streams") or [None])[0]
        card.set_detected(dict(live, account=result.get("account") or channel) if own and live else None)
        if own and live:
            self._connect_once(card, "%s:%s" % (platform, live.get("id") or channel))

    def _connect_once(self, card, stream):
        """Each stream connects by itself once. After that a Disconnect press stays pressed."""
        if self.s.get("auto_connect_live") and not card.source.running and stream not in self._auto_connected:
            self._auto_connected.add(stream)
            card.toggle()

    def _next_stream_id(self):
        return max([c.id for c in self.extra_cards.values()] + [1]) + 1

    # ----- names -----
    def stream_name(self, key):
        """"Drxshi · Shorts" for a stream found through a signed-in account, "" for one added by link."""
        card = self.cards.get(key) or self.extra_cards.get(key)
        info = getattr(card, "detected", None)
        if not info:
            return ""
        account = info.get("account") or ""
        if card not in self._youtube_cards():
            return account
        name = "%s · %s" % (account, FORMAT_NAMES[stream_format(self.s, info)])
        twins = [c for c in self._youtube_cards() if c.detected and stream_format(self.s, c.detected) == stream_format(self.s, info)]
        return "%s %d" % (name, twins.index(card) + 1) if len(twins) > 1 and card in twins else name

    def _youtube_cards(self):
        return [self.cards["youtube"]] + [c for c in self.extra_cards.values() if c.platform() == "youtube"]

    def set_stream_format(self, video, chosen):
        saved = self.s.get("yt_stream_formats")
        saved = dict(saved) if isinstance(saved, dict) else {}
        saved[video] = chosen
        self.s.set("yt_stream_formats", dict(list(saved.items())[-30:]))
        self._streams_changed()
