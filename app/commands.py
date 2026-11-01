"""Chat commands: custom !commands that answer in chat or aloud, and !memes that play a clip, show a picture or read a line."""
import os
import re
import shutil
import time

from .models import viewer_key

NAME_RX = re.compile(r"[\w-]{1,30}")
MEME_SOUNDS = (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus")
MEME_IMAGES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
BUILTIN = ("commands", "memes")                 # used only when you have not made a command with the same name
PLATFORM_NAMES = {"youtube": "YouTube", "twitch": "Twitch", "kick": "Kick", "tip": "Payment", "test": "Test"}
VARIABLES = (("{user}", "the viewer who typed the command"),
             ("{touser}", "the first word after the command (like @friend), or the viewer"),
             ("{args}", "everything typed after the command"),
             ("{count}", "how many times the command has been used"),
             ("{platform}", "YouTube, Twitch or Kick"))


def clean_name(name):
    """'!Bruh' -> 'bruh'. Returns '' for names that cannot be typed as one chat word."""
    name = (name or "").strip().lstrip("!").lower()
    return name if NAME_RX.fullmatch(name) else ""


def render(template, m, args="", count=0):
    words = args.split()
    values = {"user": m.author, "touser": words[0].lstrip("@") if words else m.author, "args": args,
              "count": str(count), "platform": PLATFORM_NAMES.get(m.platform, m.platform.title())}
    text = re.sub(r"\{(\w+)\}", lambda x: values.get(x.group(1).lower(), x.group(0)), template or "")
    return text.strip().lstrip("!").strip()        # a reply that starts with ! could set off another command


def import_file(path, folder):
    """Copy a picked sound or picture into the memes folder and return its new file name."""
    os.makedirs(folder, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(path))
    base = re.sub(r"[^\w-]+", "_", base).strip("_")[:60] or "meme"
    name, n = base + ext.lower(), 2
    while os.path.exists(os.path.join(folder, name)):
        name, n = "%s_%d%s" % (base, n, ext.lower()), n + 1
    shutil.copyfile(path, os.path.join(folder, name))
    return name


class Commands:
    def __init__(self, settings, memes_dir):
        self.s, self.memes_dir = settings, memes_dir
        self.last_used = {}          # ("command" | "meme", name) -> time
        self.last_meme = -1e9        # any meme, for the gap between two memes
        self.points = None           # loyalty points (set by the main window) for memes that cost points

    def items(self, kind):
        """kind is 'commands' or 'memes'; always a fresh list, so callers can edit and save it."""
        return [dict(x) for x in self.s.get(kind) or [] if isinstance(x, dict) and clean_name(x.get("name"))]

    def find(self, kind, name):
        return next((x for x in self.items(kind) if clean_name(x.get("name")) == name), None)

    def file(self, name, kinds):
        """Full path of a meme file, only if it is inside the memes folder and has an allowed type."""
        name = os.path.basename(name or "")
        path = os.path.join(self.memes_dir, name)
        return path if name and os.path.splitext(name)[1].lower() in kinds and os.path.isfile(path) else ""

    def handle(self, m, now=None):
        """Return what to do for a chat message that is a known !command or !meme, or None for anything else.

        The result is a dict: type ('command' | 'meme' | 'list'), name, skipped (why nothing happens, or ''),
        reply (text for chat), speak (text to read aloud), sound (file path) and image (file name for the overlay)."""
        text = (m.text or "").strip()
        if not text.startswith("!") or m.kind != "chat":
            return None
        word, _, args = text[1:].partition(" ")
        name, args = clean_name(word), args.strip()
        if not name:
            return None
        now = time.time() if now is None else now
        cmd = self.find("commands", name) if self.s.get("commands_on") else None
        if cmd:
            return self._command(cmd, name, m, args, now)
        meme = self.find("memes", name) if self.s.get("memes_on") else None
        if meme:
            return self._meme(meme, name, m, args, now)
        if name in BUILTIN and self.s.get("commands_on"):
            return self._list(name, m, now)
        return None

    def _result(self, kind, name, skipped="", reply="", speak="", sound="", image=""):
        return {"type": kind, "name": name, "skipped": skipped, "reply": reply, "speak": speak, "sound": sound, "image": image}

    def _blocked(self, kind, item, name, m, now):
        if item.get("mods_only") and not m.mod:
            return "mods only"
        if m.mod:                                  # moderators and the streamer skip cooldowns
            return ""
        if now - self.last_used.get((kind, name), -1e9) < float(item.get("cooldown") or 0):
            return "cooldown"
        if kind == "meme" and now - self.last_meme < float(self.s.get("meme_gap") or 0):
            return "another meme just played"
        return ""

    def _command(self, cmd, name, m, args, now):
        why = self._blocked("command", cmd, name, m, now)
        if why:
            return self._result("command", name, why)
        self.last_used[("command", name)] = now
        count = self._count("commands", name)
        text = render(cmd.get("response"), m, args, count)
        mode = cmd.get("mode") or "reply"
        return self._result("command", name, "" if text else "empty reply",
                            reply=text if mode in ("reply", "both") else "", speak=text if mode in ("speak", "both") else "")

    def _meme(self, meme, name, m, args, now):
        why = self._blocked("meme", meme, name, m, now)
        if why:
            return self._result("meme", name, why)
        sound, image = self.file(meme.get("sound"), MEME_SOUNDS), self.file(meme.get("image"), MEME_IMAGES)
        speak = render(meme.get("text"), m, args, 0)
        if not (sound or image or speak):
            return self._result("meme", name, "meme file missing")
        cost = int(meme.get("cost") or 0)
        if cost and self.points is not None and self.s.get("points_on") and not m.mod and not self.points.spend(viewer_key(m), cost):
            return self._result("meme", name, "needs %d %s" % (cost, self.points.name))
        self.last_used[("meme", name)] = self.last_meme = now
        self._count("memes", name)
        return self._result("meme", name, sound=sound, image=os.path.basename(image), speak=speak)

    def _list(self, name, m, now):
        if not m.mod and now - self.last_used.get(("command", name), -1e9) < 10:
            return self._result("list", name, "cooldown")
        self.last_used[("command", name)] = now
        cmds = " ".join("!" + clean_name(c["name"]) for c in self.items("commands"))
        memes = " ".join("!" + clean_name(x["name"]) for x in self.items("memes")) if self.s.get("memes_on") else ""
        if name == "memes":
            reply = ("Memes: " + memes) if memes else ""
        else:
            reply = " | ".join(p for p in (("Commands: " + cmds) if cmds else "", ("Memes: " + memes) if memes else "") if p)
        return self._result("list", name, "" if reply else "nothing to list", reply=reply[:400])

    def _count(self, kind, name):
        items = self.items(kind)
        for x in items:
            if clean_name(x.get("name")) == name:
                x["uses"] = int(x.get("uses") or 0) + 1
                self.s.set(kind, items)
                return x["uses"]
        return 0
