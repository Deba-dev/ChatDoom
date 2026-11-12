"""Basic chat moderation for the reader: decides what is allowed to be spoken."""
import os
import re
import time
from collections import deque

from .wordguard import WordGuard

KNOWN_BOTS = {"nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot",
              "botrix", "kickbot", "sery_bot", "soundalerts", "serybot", "commanderroot",
              "deepbot", "coebot", "phantombot", "vivbot", "stay_hydrated_bot", "streamlabsbot",
              "ankhbot", "botisimo", "twitchbot", "pretzelrocks", "streamstickers", "frostytoolsdotcom",
              "own3d", "lumiastream", "blerp", "kofistreambot", "tangiabot", "songlistbot", "creatisbot",
              "playwithviewersbot", "pokemoncommunitygame", "dixperbro", "streamholics", "rainmaker", "stream_elements",
              "streamerbot", "botrixoficial", "kicklet", "chatdoom"}
BOT_TAIL = re.compile(r"(?:^|[_\-.\s\d])bot$", re.I)       # sery_bot, my-bot, Chat 2 Bot
CAMEL_BOT = re.compile(r"[a-z0-9]Bot$")                     # MooBot, ChannelBot (but not Abbot)
TTS_RX = re.compile(r"^\s*!tts\b[\s:,-]*", re.I)
NOT_PAID, NOT_TTS = "normal messages off", "not a !tts message"
BLOCKED_NAME = "blocked name"
SAFE_MODE = "safe mode"
SHOW_ONLY = (NOT_PAID, NOT_TTS)                             # read mode reasons: the message is fine, it is just not spoken
SENT = deque(maxlen=60)                                     # (time, text) of what CHATDOOM itself posted in chat
ECHO_SECS = 180
LINK_RX = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|in|net|org|tv|gg|io|me|co)\b", re.I)

BLOCKED_HELP = """# One word or phrase per line. Messages containing them are NOT read aloud.
# Lines starting with # are ignored. Add words in English letters and/or Devanagari.
# Tricks like b.c, bhennnn, bh3n, fancy letters and the other script are caught automatically.
"""
ALLOWED_HELP = """# Words and phrases that are never blocked, even if they contain a blocked word. One per line.
# Use this when a blocked word catches normal chat, e.g. a phrase like "chod de" if you blocked "chod".
"""


def read_list(path, help_text):
    """Lines of a word list file (created with its help text on first run), without comments."""
    words = []
    try:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(help_text)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    words.append(line)
    except Exception:
        pass
    return words


def plain_name(name):
    """@Nightbot, Sery_Bot and nightbot all become nightbot / serybot."""
    return re.sub(r"[^a-z0-9]", "", (name or "").strip().lstrip("@").lower())


KNOWN_PLAIN = {plain_name(b) for b in KNOWN_BOTS}


def looks_like_bot(m, extra=()):
    """Chat bots (Nightbot, StreamElements, names ending in bot) and any name the streamer listed. YouTube now sends @handles."""
    if m.bot:
        return True
    raw = (m.author or "").strip().lstrip("@")
    plain = plain_name(raw)
    if not plain:
        return False
    if plain in KNOWN_PLAIN or plain in {plain_name(x) for x in extra or ()}:
        return True
    return bool(BOT_TAIL.search(raw) or CAMEL_BOT.search(raw))


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"^@\S+\s+", "", (text or "").strip())).lower()


def remember_sent(text, now=None):
    """Called for every line CHATDOOM posts (command answers, timers, giveaways), so its echo in chat is not read aloud."""
    if (text or "").strip():
        SENT.append((time.time() if now is None else now, _norm(text)))


def is_echo(text, now=None):
    now = time.time() if now is None else now
    got = _norm(text)
    if not got:
        return False
    for when, sent in SENT:
        if now - when > ECHO_SECS:
            continue
        if got == sent or (len(got) >= 20 and (sent.startswith(got) or got.startswith(sent[:len(got)]))):
            return True
    return False


def tts_text(text):
    """The words after !tts, or None when the message is not a !tts message."""
    found = TTS_RX.match(text or "")
    return (text[found.end():].strip()) if found else None


def spoken_text(text):
    """What is read aloud: a !tts message without the !tts."""
    asked = tts_text(text)
    return text if asked is None else asked


class Moderator:
    def __init__(self, settings, blocked_path, allowed_path=None):
        self.s = settings
        self.blocked_path = blocked_path
        self.allowed_path = allowed_path or os.path.join(os.path.dirname(blocked_path), "allowed_words.txt")
        self._blocked, self._allowed = [], []
        self.guard = WordGuard()
        self.safe = ""          # raid safe mode: "" off, "paid" read paid only, "mods" read paid and mods
        self.recent = {}        # (author, text) -> time
        self.last_spoken = {}   # author -> time
        self.reload_blocked()

    @property
    def blocked(self):
        return self._blocked

    @blocked.setter
    def blocked(self, words):
        self._blocked = list(words)
        self.guard = WordGuard(self._blocked, self._allowed)

    @property
    def allowed(self):
        return self._allowed

    @allowed.setter
    def allowed(self, words):
        self._allowed = list(words)
        self.guard = WordGuard(self._blocked, self._allowed)

    def reload_blocked(self):
        """Read both lists again (blocked words and the allow list)."""
        self._allowed = read_list(self.allowed_path, ALLOWED_HELP)
        self.blocked = read_list(self.blocked_path, BLOCKED_HELP)

    def _blocked_hit(self, text):
        return self.guard.hit(text)

    def name_blocked(self, m):
        """True when the viewer's name contains a blocked word."""
        return m.platform != "test" and bool(self.blocked) and self._blocked_hit((m.author or "").lstrip("@"))

    def masked_name(self):
        """What a blocked name becomes: Hindi wording with a Hindi voice, English otherwise."""
        return "Ek viewer" if (self.s.get("en_voice") or "").lower().startswith("hi-") else "A viewer"

    def shown_name(self, m):
        """The name to speak and show on stream: the real one, or a stand-in when it has a blocked word."""
        return self.masked_name() if self.name_blocked(m) else m.author

    def check(self, m, now=None):
        """Return (allowed, reason). Reason is shown in the feed when a message is skipped."""
        now = time.time() if now is None else now
        if m.platform == "test":
            return True, ""
        s, text = self.s, m.text.strip()
        paid = m.kind in ("super", "member")
        if not text and not paid:
            return False, "empty"
        name = m.author.lower()
        if s.get("ignore_bots") and looks_like_bot(m, s.get("bot_names")):
            return False, "bot"
        if not paid and is_echo(text, now):
            return False, "CHATDOOM's own message"
        if self._blocked_hit(text):
            return False, "blocked word"
        if s.get("blocked_name_action") == "skip" and self.name_blocked(m):
            return False, BLOCKED_NAME
        if self.safe:                    # raid shield: on top of the settings, which stay untouched
            if LINK_RX.search(text):
                return False, "link (" + SAFE_MODE + ")"
            if not paid and not (m.mod and self.safe == "mods"):
                return False, SAFE_MODE
        mode = s.get("read_mode") or "all"
        if paid:
            return (True, "") if s.get("read_super") else (False, "paid messages off")
        quiet = ""                       # shown in the feed and the OBS chat box, but not spoken
        asked = tts_text(text)
        if mode == "paid":
            quiet = NOT_PAID
        elif asked is not None:
            if not asked:
                return False, "empty !tts"
            text = asked
        elif mode == "tts" and not m.mod:
            quiet = NOT_TTS
        if s.get("mods_only") and not m.mod:
            return False, "mods only"
        if s.get("skip_cmds") and text.startswith("!"):
            return False, "command"
        if s.get("skip_links") and LINK_RX.search(text):
            return False, "link"
        if len(text) > 8 and len(set(text.replace(" ", ""))) <= 2:
            return False, "spam"
        key = (name, text.lower())
        if now - self.recent.get(key, -1e9) < s.get("dedupe_secs"):
            return False, "repeat"
        self.recent[key] = now
        if len(self.recent) > 500:
            self.recent = {k: t for k, t in self.recent.items() if now - t < 60}
        if quiet:
            return False, quiet
        if not m.mod and now - self.last_spoken.get(name, -1e9) < s.get("user_cooldown"):
            return False, "too fast"
        self.last_spoken[name] = now
        return True, ""
