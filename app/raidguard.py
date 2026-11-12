"""Hate-raid shield: spots a flood of new accounts or copy-pasted spam and turns on safe mode by itself.

Safe mode never edits the streamer's settings. The Moderator reads it as an extra rule on top of them,
so switching it off (or the app closing mid-raid) always leaves the original settings in place.
"""
import re
import time
from collections import deque

from .wordguard import canonical

WINDOW = 30            # seconds of chat that are looked at
SAME_MSGS = 8          # this many copies of one message in the window is a spam raid
SAME_MIN_LEN = 8       # shorter lines (gg, W, LUL, 2-word hype) are normal chat floods, not raids


def spam_key(text):
    """Near-identical messages share this key: same letters after canonical(), ignoring spaces, emoji and punctuation."""
    return re.sub(r"[\W_]+", "", canonical(text or ""))


class RaidGuard:
    def __init__(self, settings):
        self.s = settings
        self.on = False
        self.reason = ""
        self.manual = False     # turned on by the streamer: stays on until they turn it off
        self.new = deque()      # (time, viewer key) of first-time chatters
        self.texts = deque()    # (time, spam key)
        self.counted = set()    # viewer keys already counted as new in this window
        self.last_hot = 0.0     # last time chat still looked like a raid

    def _trim(self, now):
        while self.new and now - self.new[0][0] > WINDOW:
            self.counted.discard(self.new.popleft()[1])
        while self.texts and now - self.texts[0][0] > WINDOW:
            self.texts.popleft()

    def feed(self, key, text, first_time, now=None):
        """One chat message from a normal viewer (not mods, paid messages or tips). Returns the reason when safe mode just turned on."""
        now = time.time() if now is None else now
        if not self.s.get("raid_on") and not self.on:
            return ""
        self._trim(now)
        if first_time and key not in self.counted:
            self.counted.add(key)
            self.new.append((now, key))
        same = spam_key(text)
        copies = 0
        if len(same) >= SAME_MIN_LEN:
            self.texts.append((now, same))
            copies = sum(1 for _, t in self.texts if t == same)
        reason = ""
        if len(self.new) >= int(self.s.get("raid_new_chatters") or 15):
            reason = "%d new chatters in %ds" % (len(self.new), WINDOW)
        elif copies >= SAME_MSGS:
            reason = "%d copies of the same message" % copies
        if not reason:
            return ""
        self.last_hot = now
        if self.on or not self.s.get("raid_on"):
            return ""
        self.on, self.reason, self.manual = True, reason, False
        return reason

    def tick(self, now=None):
        """Called every few seconds while on. True when safe mode just turned off after the quiet minutes."""
        now = time.time() if now is None else now
        if not self.on or self.manual:
            return False
        if now - self.last_hot >= float(self.s.get("raid_cooldown_min") or 3) * 60:
            self.stop()
            return True
        return False

    def start(self, now=None):
        """The streamer turned it on by hand."""
        self.on, self.reason, self.manual = True, "turned on by you", True
        self.last_hot = time.time() if now is None else now

    def stop(self):
        self.on, self.reason, self.manual = False, "", False
        self.new.clear()
        self.texts.clear()
        self.counted.clear()
