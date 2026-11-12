"""Viewer memory: what a streamer would remember about a regular, shown on a private card when they come back.

Only public chat facts (name, when they chatted, how many streams) and the streamer's own notes are kept, in viewers.json.
The card is for the streamer's screen only; it never goes to the OBS overlay.
"""
import time
from collections import deque

CARD_GAP = 10           # seconds between two cards
REGULAR_STREAMS = 5     # "regulars only" means this many streams or more
QUEUE = 5               # cards waiting their turn; more than this during a rush are dropped
MAX_VIEWERS = 50000     # oldest (by last chat) are forgotten past this
NOTE_MAX = 200
MODES = (("Regulars only (5+ streams)", "regulars"), ("Everyone who comes back", "returning"), ("Off", "off"))


def ordinal(n):
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "%d%s" % (n, suffix)


def short_date(ts, now=None):
    """4 Aug, or 4 Aug 2025 when it was another year."""
    when, today = time.localtime(ts), time.localtime(time.time() if now is None else now)
    text = "%d %s" % (when.tm_mday, time.strftime("%b", when))
    return text if when.tm_year == today.tm_year else "%s %d" % (text, when.tm_year)


def blank(now=None):
    return {"name": "", "first_seen": now, "streams": 0, "messages": 0, "last_seen": now, "note": ""}


class ViewerMemory:
    def __init__(self, file):
        """file: a JsonFile. Old viewers.json files are a plain list of viewer keys; they are kept and filled in from now on."""
        self.file = file
        data = file.data
        if isinstance(data, list):
            data = {str(k): dict(blank(None), streams=1) for k in data}    # seen before, but when and how often is unknown
            file.dirty = True
        elif not isinstance(data, dict):
            data = {}
        file.data = data
        self.waiting = deque(maxlen=QUEUE)
        self.last_card = -1e9
        self.unsaved = False    # only message counts changed: written with the next real change, or on exit

    @property
    def data(self):
        return self.file.data

    def record(self, key):
        return self.data.get(key)

    def saw(self, key, name, new_stream, now=None):
        """One allowed chat message. Counts the stream once per stream (new_stream). Returns the viewer's record."""
        now = time.time() if now is None else now
        r = self.data.get(key)
        new = r is None
        if new:
            r = self.data[key] = blank(now)
        r["name"] = (name or r.get("name") or "")[:80]
        r["messages"] = int(r.get("messages") or 0) + 1
        r["last_seen"] = now
        if new_stream:
            r["streams"] = int(r.get("streams") or 0) + 1
        if new or new_stream:
            self.file.dirty = True
        else:
            self.unsaved = True               # a big viewers.json is not rewritten every minute for message counts
        return r

    def wants_card(self, record, mode):
        streams = int(record.get("streams") or 0)
        if mode == "returning":
            return streams >= 2
        if mode == "regulars":
            return streams >= REGULAR_STREAMS
        return False

    def queue(self, key):
        if key not in self.waiting:
            self.waiting.append(key)

    def next_card(self, now=None):
        """The next card's text, at most one every CARD_GAP seconds, or ''."""
        now = time.time() if now is None else now
        if now - self.last_card < CARD_GAP:
            return ""
        while self.waiting:
            r = self.data.get(self.waiting.popleft())
            if r is not None:                     # forgotten while waiting: skip it
                self.last_card = now
                return self.card_text(r, now)
        return ""

    def card_text(self, r, now=None):
        parts = ["%s stream" % ordinal(max(1, int(r.get("streams") or 1)))]
        if r.get("first_seen"):
            parts.append("first seen %s" % short_date(r["first_seen"], now))
        if r.get("note"):
            parts.append('note: "%s"' % r["note"])
        return "%s: %s" % (r.get("name") or "Viewer", " · ".join(parts))

    def note(self, key):
        return (self.data.get(key) or {}).get("note", "")

    def set_note(self, key, text, name="", now=None):
        r = self.data.get(key)
        if r is None:
            r = self.data[key] = blank(time.time() if now is None else now)
            r["name"] = name or ""
        r["note"] = (text or "").strip()[:NOTE_MAX]
        self.file.dirty = True

    def forget(self, key):
        if self.data.pop(key, None) is not None:
            self.file.dirty = True
        try:
            self.waiting.remove(key)
        except ValueError:
            pass

    def clear(self):
        self.file.data = {}
        self.waiting.clear()
        self.file.dirty = True

    def trim(self):
        if len(self.data) > MAX_VIEWERS:
            keep = sorted(self.data.items(), key=lambda kv: kv[1].get("last_seen") or 0)[-MAX_VIEWERS:]
            self.file.data = dict(keep)
            self.file.dirty = True
