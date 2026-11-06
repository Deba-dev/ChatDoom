"""Stream tools: loyalty points, chat polls, giveaways, counters, first-time welcomes, timers, song requests and the
stream summary. Plain Python (no Qt) so every rule can be tested; the main window feeds it chat and acts on the results."""
import json
import math
import os
import random
import re
import time

from .commands import PLATFORM_NAMES, clean_name, render
from .models import viewer_key

ACTIVE_WINDOW = 600            # a viewer who chatted in the last 10 minutes counts as watching for the points bonus


LINK_RX = re.compile(r"https?://|www\.|\b[\w-]+\.(com|net|org|in|gg|tv|io|xyz|ru)\b", re.I)
GOAL_SOURCES = {"follow": "follows", "subscription": "subs", "gift": "subs", "subscriber": "subs", "membership": "members", "tip": "money", "superchat": "money"}
LATEST_LABELS = {"follow": "Latest follower", "subscription": "Latest sub", "gift": "Latest gift", "subscriber": "Latest subscriber",
                 "membership": "Latest member", "tip": "Latest tip", "superchat": "Latest Super Chat"}


def action(kind, name, skipped="", reply="", speak="", toast=""):
    """Same shape as a Commands result, plus an optional toast for the app window."""
    return {"type": kind, "name": name, "skipped": skipped, "reply": reply, "speak": speak, "sound": "", "image": "", "toast": toast}


class JsonFile:
    """A small JSON file that is written only when something changed (save() is called on a timer and on exit)."""

    def __init__(self, path, empty):
        self.path, self.dirty = path, False
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
            if not isinstance(self.data, type(empty)):
                self.data = empty
        except Exception:
            self.data = empty

    def save(self):
        if not self.dirty or not self.path:
            return
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
            self.dirty = False
        except Exception:
            pass


# ---------------------------------------------------------------- loyalty points
def level_of(xp, base):
    """Each level takes more than the last: level 2 at base, level 3 at 4x base, level 4 at 9x base."""
    return int(math.sqrt(max(0, xp) / max(1, base))) + 1


class Points:
    def __init__(self, settings, path):
        self.s, self.file = settings, JsonFile(path, {})
        self.gambled = {}
        self.levelups = []           # (platform, viewer, level) waiting to be announced

    @property
    def name(self):
        return (self.s.get("points_name") or "points").strip()

    def _row(self, key, name=""):
        row = self.file.data.setdefault(key, {"name": name or key.split(":", 1)[-1], "points": 0, "msg": 0, "bonus": 0, "active": 0})
        if name:
            row["name"] = name
        return row

    def balance(self, key):
        return int(self.file.data.get(key, {}).get("points", 0))

    def add(self, key, amount, name=""):
        row = self._row(key, name)
        row["points"] = max(0, int(row["points"]) + int(amount))
        self.file.dirty = True
        return row["points"]

    def level(self, key):
        return level_of(int(self.file.data.get(key, {}).get("xp", 0)), int(self.s.get("level_base") or 100))

    def _gain_xp(self, row, amount):
        row["xp"] = int(row.get("xp", 0)) + amount

    def _check_level(self, row, m):
        now_level = level_of(int(row.get("xp", 0)), int(self.s.get("level_base") or 100))
        if now_level > int(row.get("lvl", 1)):
            row["lvl"] = now_level
            self.levelups.append((m.platform, m.author, now_level))

    def spend(self, key, amount):
        if self.balance(key) < amount:
            return False
        self.add(key, -amount)
        return True

    def earn(self, m, now):
        """Points for chatting, at most once per cooldown so spamming earns nothing extra."""
        if not self.s.get("points_on") or m.platform in ("test", "tip"):
            return
        row = self._row(viewer_key(m), m.author)
        row["active"] = now
        if now - row.get("msg", 0) >= float(self.s.get("points_msg_cooldown") or 0):
            row["msg"] = now
            row["points"] = int(row["points"]) + int(self.s.get("points_per_msg") or 0)
            if self.s.get("levels_on"):
                self._gain_xp(row, int(self.s.get("level_xp_msg") or 0))
        if self.s.get("levels_on"):
            self._check_level(row, m)
        self.file.dirty = True

    def tick(self, now):
        """Watching bonus for everyone who chatted recently (CHATDOOM cannot see silent viewers)."""
        if not self.s.get("points_on"):
            return 0
        every, amount, given = float(self.s.get("points_bonus_minutes") or 10) * 60, int(self.s.get("points_bonus") or 0), 0
        for row in self.file.data.values():
            if now - row.get("active", 0) <= ACTIVE_WINDOW and now - row.get("bonus", 0) >= every:
                row["bonus"] = now
                row["points"] = int(row["points"]) + amount
                if self.s.get("levels_on"):
                    self._gain_xp(row, int(self.s.get("level_xp_bonus") or 0))
                given += 1
        if given:
            self.file.dirty = True
        return given

    def top(self, n=10):
        rows = sorted(self.file.data.values(), key=lambda r: -int(r.get("points", 0)))
        return [(r["name"], int(r["points"])) for r in rows[:n] if int(r.get("points", 0)) > 0]

    def reset(self):
        self.file.data = {}
        self.file.dirty = True

    def handle(self, m, word, args, now):
        if word == "points":
            return action("points", word, reply="%s has %d %s" % (m.author, self.balance(viewer_key(m)), self.name))
        if word == "top":
            top = self.top(5)
            return action("points", word, "" if top else "nobody has points yet",
                          reply="Top %s: " % self.name + ", ".join("%s %d" % t for t in top))
        if word == "level" and self.s.get("levels_on"):
            key = viewer_key(m)
            level, base = self.level(key), int(self.s.get("level_base") or 100)
            left = level * level * base - int(self.file.data.get(key, {}).get("xp", 0))
            return action("points", word, reply="%s is level %d (%d XP to level %d)" % (m.author, level, left, level + 1))
        if word == "gamble" and self.s.get("gamble_on"):
            key, have = viewer_key(m), self.balance(viewer_key(m))
            bet_text = (args.split() or [""])[0].lower()
            bet = have if bet_text == "all" else int(bet_text) if bet_text.isdigit() else 0
            low = int(self.s.get("gamble_min") or 1)
            if not m.mod and now - self.gambled.get(key, -1e9) < float(self.s.get("gamble_cooldown") or 0):
                return action("points", word, "cooldown")
            if bet < low:
                return action("points", word, reply="%s, bet at least %d %s: !gamble %d" % (m.author, low, self.name, low))
            if bet > have:
                return action("points", word, reply="%s, you only have %d %s" % (m.author, have, self.name))
            self.gambled[key] = now
            won = random.random() < 0.5
            total = self.add(key, bet if won else -bet, m.author)
            return action("points", word, reply="%s %s %d %s and now has %d" % (m.author, "won" if won else "lost", bet, self.name, total))
        return None


# ---------------------------------------------------------------- poll
class Poll:
    def __init__(self):
        self.question, self.options, self.votes, self.ends, self.active, self.result = "", [], {}, 0.0, False, ""

    def start(self, question, options, seconds, now):
        options = [o.strip() for o in options if o and o.strip()][:5]
        if not question.strip() or len(options) < 2:
            return "Type a question and at least two options."
        self.question, self.options, self.votes = question.strip(), options, {}
        self.ends, self.active, self.result = now + max(10, int(seconds)), True, ""
        return ""

    def vote(self, key, number):
        if not self.active or not 1 <= number <= len(self.options):
            return False
        self.votes[key] = number - 1            # changing your mind is allowed; the last vote counts
        return True

    def tally(self):
        counts = [0] * len(self.options)
        for i in self.votes.values():
            counts[i] += 1
        return counts

    def close(self):
        if not self.active:
            return ""
        self.active = False
        counts, total = self.tally(), len(self.votes)
        best = max(counts) if counts else 0
        winners = [self.options[i] for i, c in enumerate(counts) if c == best and best]
        if not total:
            self.result = "Poll ended with no votes."
        elif len(winners) > 1:
            self.result = "Poll ended in a tie: %s (%d votes each)." % (" / ".join(winners), best)
        else:
            self.result = "Poll ended: %s wins with %d of %d votes." % (winners[0], best, total)
        return self.result

    def state(self, now):
        if not self.options:
            return None
        counts = self.tally()
        return {"question": self.question, "active": self.active, "total": len(self.votes), "result": self.result,
                "endsIn": max(0, int(self.ends - now)) if self.active else 0,
                "options": [{"text": o, "votes": c} for o, c in zip(self.options, counts)]}

    def summary(self, now):
        if not self.options:
            return "No poll yet."
        counts, total = self.tally(), max(1, len(self.votes))
        lines = ["%d. %s — %d (%d%%)" % (i + 1, o, c, round(100 * c / total)) for i, (o, c) in enumerate(zip(self.options, counts))]
        head = ("Open, %d s left" % max(0, int(self.ends - now))) if self.active else (self.result or "Closed")
        return "%s\n%s\n%s" % (self.question, "\n".join(lines), head)


# ---------------------------------------------------------------- giveaway
class Giveaway:
    def __init__(self):
        self.keyword, self.cost, self.active, self.entries, self.winners = "join", 0, False, {}, []

    def start(self, keyword, cost):
        keyword = clean_name(keyword)
        if not keyword:
            return "Type a one-word keyword, like join."
        self.keyword, self.cost, self.active, self.entries, self.winners = keyword, max(0, int(cost)), True, {}, []
        return ""

    def pick(self):
        """Random winner among entries that have not won yet. Returns (key, name, platform) or None."""
        left = [(k, v) for k, v in self.entries.items() if k not in {w[0] for w in self.winners}]
        if not left:
            return None
        key, (name, platform) = random.choice(left)
        self.winners.append((key, name, platform))
        return key, name, platform

    def state(self):
        if not self.entries and not self.active and not self.winners:
            return None
        return {"keyword": self.keyword, "open": self.active, "entries": len(self.entries),
                "winner": self.winners[-1][1] if self.winners else "", "platform": self.winners[-1][2] if self.winners else ""}


# ---------------------------------------------------------------- stream summary
AMOUNT_RX = re.compile(r"\d[\d,]*(?:\.\d+)?")


def split_amount(text):
    """'₹1,200.00' -> ('₹', 1200.0); '50 bits' -> ('bits', 50.0). ('', 0) when there is no number."""
    m = AMOUNT_RX.search(text or "")
    if not m:
        return "", 0.0
    return (text[:m.start()] + text[m.end():]).strip(), float(m.group(0).replace(",", ""))


class Prediction:
    """Viewers bet points on what happens next. Winners get their bet back plus a fair share of what the losers bet."""

    def __init__(self):
        self.question, self.options, self.bets = "", [], {}
        self.open = self.locked = False
        self.ends, self.result = 0, ""

    @property
    def active(self):
        return self.open or self.locked

    def start(self, question, options, seconds, now):
        question, options = (question or "").strip(), [o.strip() for o in options if o.strip()]
        if self.active:
            return "A prediction is already running."
        if not question or len(options) < 2:
            return "A prediction needs a question and at least two outcomes."
        self.__init__()
        self.question, self.options, self.open, self.ends = question, options, True, now + seconds
        return ""

    def lock(self):
        if self.open:
            self.open, self.locked = False, True

    def pools(self):
        totals = [0] * len(self.options)
        for number, amount, _ in self.bets.values():
            totals[number - 1] += amount
        return totals

    def resolve(self, number):
        """Returns [(key, name, points back)], and the sentence for chat."""
        if not self.active or not 1 <= number <= len(self.options):
            return [], ""
        pools = self.pools()
        winners, losers = pools[number - 1], sum(pools) - pools[number - 1]
        if not winners:
            paid, _ = self.refund("Nobody bet on %s, so all bets were returned." % self.options[number - 1])
            return paid, self.result
        paid = [(key, name, amount + losers * amount // winners) for key, (pick, amount, name) in self.bets.items() if pick == number]
        self.open = self.locked = False
        self.bets = {}
        self.result = "%s won! %d viewer%s shared %d points." % (self.options[number - 1], len(paid), "" if len(paid) == 1 else "s", winners + losers)
        return paid, self.result

    def refund(self, text="The prediction was cancelled and all bets were returned."):
        paid = [(key, name, amount) for key, (_, amount, name) in self.bets.items()]
        self.open = self.locked = False
        self.bets, self.result = {}, text
        return paid, text

    def state(self, now):
        if not (self.active or self.result):
            return None
        pools = self.pools()
        return {"question": self.question, "open": self.open, "locked": self.locked, "result": self.result, "total": sum(pools),
                "endsIn": max(0, int(self.ends - now)), "options": [{"text": o, "pool": p} for o, p in zip(self.options, pools)]}


class ViewerQueue:
    """A line of viewers waiting for their turn, like joining your next game."""

    def __init__(self):
        self.open, self.people = False, []          # people: [(key, name, platform)]

    def place(self, key):
        return next((i + 1 for i, p in enumerate(self.people) if p[0] == key), 0)

    def next(self):
        return self.people.pop(0) if self.people else None

    def state(self):
        return {"open": self.open, "count": len(self.people), "names": [p[1] for p in self.people[:5]]}


class SessionStats:
    def __init__(self):
        self.reset()

    def reset(self):
        self.started, self.ended = 0.0, 0.0
        self.platforms, self.chatters, self.paid, self.events = {}, {}, {}, {}
        self.paid_count = 0

    def begin(self, now):
        if not self.started or self.ended:
            if self.ended:
                self.reset()
            self.started = now

    def finish(self, now):
        if self.started and not self.ended:
            self.ended = now

    def add_message(self, m):
        if m.platform == "test":
            return
        if m.platform != "tip":
            self.platforms[m.platform] = self.platforms.get(m.platform, 0) + 1
            row = self.chatters.setdefault(viewer_key(m), [m.author, 0])
            row[1] += 1
        if m.kind in ("super", "member") and m.amount:
            cur, value = split_amount(m.amount)
            self.paid[cur] = self.paid.get(cur, 0.0) + value
        if m.kind == "super" or m.platform == "tip":
            self.paid_count += 1

    def count(self, event, n=1):
        self.events[event] = self.events.get(event, 0) + n

    def lines(self, now):
        end = self.ended or now
        mins = int((end - self.started) // 60) if self.started else 0
        total = sum(self.platforms.values())
        out = ["Stream summary — %dh %02dm" % (mins // 60, mins % 60)]
        by = " · ".join("%s %d" % (PLATFORM_NAMES.get(p, p.title()), n) for p, n in sorted(self.platforms.items(), key=lambda x: -x[1]))
        out.append("Messages: %d%s" % (total, " (%s)" % by if by else ""))
        out.append("Chatters: %d (%d new)" % (len(self.chatters), self.events.get("new_viewer", 0)))
        top = sorted(self.chatters.values(), key=lambda r: -r[1])[:3]
        if top:
            out.append("Top chatters: " + ", ".join("%s (%d)" % (n, c) for n, c in top))
        if self.paid_count or self.paid:
            money = " · ".join(("%s%s" % (c, ("%.2f" % v).rstrip("0").rstrip(".")) if len(c) <= 1 else "%s %s" % (("%.2f" % v).rstrip("0").rstrip("."), c))
                                    for c, v in self.paid.items() if v)
            out.append("Super Chats, bits and tips: %d%s" % (self.paid_count, " (%s)" % money if money else ""))
        extras = [(label, self.events.get(key, 0)) for key, label in (("command", "Commands"), ("meme", "Memes"), ("vote", "Poll votes"),
                                                                      ("entry", "Giveaway entries"), ("song", "Song requests"))]
        extras = [("%s %d" % e) for e in extras if e[1]]
        if extras:
            out.append(" · ".join(extras))
        return out


# ---------------------------------------------------------------- everything together
class Tools:
    def __init__(self, settings, folder, music=None):
        self.s, self.music = settings, music
        self.points = Points(settings, os.path.join(folder, "points.json") if folder else "")
        self.viewers = JsonFile(os.path.join(folder, "viewers.json") if folder else "", [])
        self.seen_ever = set(self.viewers.data)
        self.seen_stream = set()
        self.poll, self.giveaway, self.stats = Poll(), Giveaway(), SessionStats()
        self.prediction, self.queue = Prediction(), ViewerQueue()
        self.redeemed, self.latest = [], {}
        self.timer_last, self.lines_since = {}, {}
        self.cooldowns = {}

    def save(self):
        self.points.file.save()
        self.viewers.data = sorted(self.seen_ever)[-50000:]
        self.viewers.save()

    # ----- every chat message that was allowed (or was a command) -----
    def observe(self, m, now=None):
        """Points, timer line counts and first-time welcomes. Returns the welcome line to use, or ''."""
        now = time.time() if now is None else now
        if m.platform in ("test", "tip"):
            return ""
        self.points.earn(m, now)
        for i in self.lines_since:
            self.lines_since[i] += 1
        key = viewer_key(m)
        new_ever, new_stream = key not in self.seen_ever, key not in self.seen_stream
        self.seen_stream.add(key)
        if new_ever:
            self.seen_ever.add(key)
            self.viewers.dirty = True
            self.stats.count("new_viewer")
        if not self.s.get("welcome_on") or m.mod:
            return ""
        if (self.s.get("welcome_mode") == "stream" and new_stream) or (self.s.get("welcome_mode") != "stream" and new_ever):
            return render(self.s.get("welcome_text") or "Welcome {user}!", m)
        return ""

    def forget_viewers(self):
        self.seen_ever, self.seen_stream = set(), set()
        self.viewers.dirty = True

    # ----- chat commands owned by the tools -----
    def handle(self, m, now=None):
        now = time.time() if now is None else now
        text = (m.text or "").strip()
        if m.kind != "chat" or not text:
            return None
        if self.poll.active and self.s.get("poll_numbers") and text.isdigit() and len(text) == 1:
            return self._vote(m, int(text))
        if not text.startswith("!"):
            return None
        word, _, args = text[1:].partition(" ")
        word, args = word.lower(), args.strip()
        if word == "vote" and self.poll.active:
            return self._vote(m, int(args.split()[0]) if args.split() and args.split()[0].isdigit() else 0)
        if self.giveaway.active and clean_name(word) == self.giveaway.keyword:
            return self._enter(m)
        counter = self._counter(m, word, args)
        if counter:
            return counter
        if word == "uptime":
            return action("info", word, reply="Live for %s" % self.uptime(now) if self.live(now) else "The stream is not live right now")
        if word == "bet" and self.prediction.active and self.s.get("points_on"):
            return self._bet(m, args)
        if word in ("queue", "place", "leave", "next", "clearqueue") and (self.queue.open or self.queue.people):
            return self._queue(m, word)
        if self.s.get("points_on") and self.s.get("shop_on") and word in ("shop", "buy"):
            return self._shop(m, word, args)
        if self.s.get("points_on") and self.s.get("say_on") and word == "say":
            return self._say(m, args, now)
        if self.s.get("points_on") and word in ("points", "top", "gamble", "level"):
            return self.points.handle(m, word, args, now)
        if self.s.get("sr_on") and self.music is not None and word in ("sr", "songrequest", "song"):
            return self._song(m, word, args, now)
        return None

    def _vote(self, m, number):
        if not self.poll.vote(viewer_key(m), number):
            return action("vote", "vote", "pick a number from 1 to %d" % len(self.poll.options))
        self.stats.count("vote")
        return action("vote", "vote")

    def _enter(self, m):
        g, key = self.giveaway, viewer_key(m)
        if key in g.entries:
            return action("entry", g.keyword, "already entered")
        if g.cost and self.s.get("points_on") and not self.points.spend(key, g.cost):
            return action("entry", g.keyword, "needs %d %s" % (g.cost, self.points.name))
        g.entries[key] = (m.author, m.platform)
        self.stats.count("entry")
        return action("entry", g.keyword)

    # ----- predictions, queue, shop and paid read-aloud -----
    def _bet(self, m, args):
        p, key, words = self.prediction, viewer_key(m), args.split()
        name = self.points.name
        if not p.open:
            return action("bet", "bet", "bets are locked")
        if key in p.bets:
            return action("bet", "bet", "already bet")
        have = self.points.balance(key)
        amount_text = words[1].lower() if len(words) > 1 else ""
        amount = have if amount_text == "all" else int(amount_text) if amount_text.isdigit() else 0
        number = int(words[0]) if words and words[0].isdigit() else 0
        if not 1 <= number <= len(p.options) or amount < 1:
            return action("bet", "bet", reply="%s, bet like this: !bet 1 100" % m.author)
        if not self.points.spend(key, amount):
            return action("bet", "bet", reply="%s, you only have %d %s" % (m.author, have, name))
        p.bets[key] = (number, amount, m.author)
        return action("bet", "bet")

    def settle_prediction(self, paid):
        for key, name, amount in paid:
            self.points.add(key, amount, name)

    def _queue(self, m, word):
        q, key = self.queue, viewer_key(m)
        if word == "queue":
            if not q.open:
                return action("queue", word, "the queue is closed")
            if q.place(key):
                return action("queue", word, reply="%s, you are already number %d" % (m.author, q.place(key)))
            if len(q.people) >= int(self.s.get("queue_limit") or 50):
                return action("queue", word, reply="The queue is full right now.")
            q.people.append((key, m.author, m.platform))
            return action("queue", word, reply="%s joined the queue at number %d" % (m.author, len(q.people)))
        if word == "place":
            spot = q.place(key)
            return action("queue", word, reply=("%s is number %d in the queue" % (m.author, spot)) if spot else "%s is not in the queue. Type !queue to join." % m.author)
        if word == "leave":
            if not q.place(key):
                return action("queue", word, "not in the queue")
            q.people = [p for p in q.people if p[0] != key]
            return action("queue", word, reply="%s left the queue" % m.author)
        if not m.mod:
            return action("queue", word, "mods only")
        if word == "clearqueue":
            q.people = []
            return action("queue", word, reply="The queue is empty.")
        person = q.next()
        return action("queue", word, "" if person else "the queue is empty", reply="Next up: %s" % person[1] if person else "", toast="Next up: %s" % person[1] if person else "")

    def shop_items(self):
        return [dict(i) for i in self.s.get("shop_items") or [] if isinstance(i, dict) and (i.get("name") or "").strip()]

    def _shop(self, m, word, args):
        items, name = self.shop_items(), self.points.name
        if word == "shop":
            listed = " | ".join("%d. %s (%d)" % (i + 1, x["name"], int(x.get("cost") or 0)) for i, x in enumerate(items) if int(x.get("stock", -1)) != 0)
            return action("shop", word, "" if listed else "the shop is empty", reply=("Shop, buy with !buy 1: " + listed)[:400] if listed else "")
        pick = args.strip().lower()
        index = int(pick) - 1 if pick.isdigit() else next((i for i, x in enumerate(items) if x["name"].lower() == pick), -1)
        if not 0 <= index < len(items):
            return action("shop", word, reply="%s, type !shop to see what you can buy" % m.author)
        item, key = items[index], viewer_key(m)
        stock, cost = int(item.get("stock", -1)), int(item.get("cost") or 0)
        if stock == 0:
            return action("shop", word, reply="%s is sold out" % item["name"])
        if not self.points.spend(key, cost):
            return action("shop", word, reply="%s, %s costs %d %s and you have %d" % (m.author, item["name"], cost, name, self.points.balance(key)))
        if stock > 0:
            item["stock"] = stock - 1
            items[index] = item
            self.s.set("shop_items", items)
        self.redeemed = ([(m.author, item["name"])] + self.redeemed)[:30]
        self.stats.count("redeem")
        return action("shop", word, reply="%s bought %s!" % (m.author, item["name"]), toast="%s bought %s" % (m.author, item["name"]))

    def _say(self, m, args, now):
        key, cost = viewer_key(m), int(self.s.get("say_cost") or 0)
        text = args.strip()[:200]
        if not text:
            return action("say", "say", reply="%s, type !say and your message (%d %s)" % (m.author, cost, self.points.name))
        if LINK_RX.search(text):
            return action("say", "say", "links are not read aloud")
        if not m.mod and now - self.cooldowns.get(("say", key), -1e9) < float(self.s.get("say_cooldown") or 0):
            return action("say", "say", "cooldown")
        if not m.mod and not self.points.spend(key, cost):
            return action("say", "say", reply="%s, !say costs %d %s" % (m.author, cost, self.points.name))
        self.cooldowns[("say", key)] = now
        return action("say", "say", speak="%s says %s" % (m.author, text))

    # ----- live time and {variables} for custom commands -----
    def live(self, now):
        return bool(self.stats.started and not self.stats.ended)

    def uptime(self, now):
        minutes = max(0, int(now - self.stats.started)) // 60
        return "%dh %dm" % (minutes // 60, minutes % 60) if minutes >= 60 else "%d minutes" % minutes

    def command_values(self, m):
        now, key = time.time(), viewer_key(m)
        return {"points": self.points.balance(key), "level": self.points.level(key), "uptime": self.uptime(now) if self.live(now) else "not live",
                "counters": {c["name"]: int(c.get("value") or 0) for c in self.counters()}}

    # ----- goals and the latest supporters -----
    def goals(self):
        return [dict(g) for g in self.s.get("goals") or [] if isinstance(g, dict) and (g.get("title") or "").strip()]

    def note_alert(self, alert):
        """Every alert moves the goals that count it, and becomes the latest of its kind."""
        category, name, amount = alert.get("category") or "", alert.get("name") or "Someone", alert.get("amount") or ""
        source = GOAL_SOURCES.get(category)
        label = LATEST_LABELS.get(category)
        if label:
            self.latest[label] = (name + " " + amount).strip() if category in ("tip", "superchat") else name
        if not source:
            return
        items = self.goals()
        add = split_amount(amount)[1] if source == "money" else 1
        for g in items:
            if g.get("source") == source:
                g["value"] = round(float(g.get("value") or 0) + add, 2)
        self.s.set("goals", items)

    def bump_goal(self, index, change):
        items = self.goals()
        if 0 <= index < len(items):
            items[index]["value"] = max(0, float(items[index].get("value") or 0) + change)
            self.s.set("goals", items)

    # counters: !death shows it; !death+ / !death + adds one; !death- / !death - removes one (moderators only)
    def _counter(self, m, word, args):
        change = 0
        if word.endswith(("+", "-")):
            word, change = word[:-1], (1 if word.endswith("+") else -1)
        elif args[:1] in ("+", "-"):
            change = 1 if args[:1] == "+" else -1
        items = self.counters()
        item = next((c for c in items if c["name"] == clean_name(word)), None)
        if item is None:
            return None
        if change:
            if not m.mod:
                return action("counter", item["name"], "mods only")
            item["value"] = int(item.get("value") or 0) + change
            self.s.set("counters", items)
        return action("counter", item["name"], reply="%s: %d" % (item.get("label") or item["name"].title(), int(item.get("value") or 0)))

    def counters(self):
        return [dict(c) for c in self.s.get("counters") or [] if isinstance(c, dict) and clean_name(c.get("name"))]

    def bump_counter(self, name, change):
        items = self.counters()
        for c in items:
            if c["name"] == name:
                c["value"] = int(c.get("value") or 0) + change
        self.s.set("counters", items)

    # song requests come from the Music page library
    def _song(self, m, word, args, now):
        music = self.music
        if word == "song":
            t = music.current()
            return action("song", word, reply=("Now playing: %s%s" % (t["title"], " — " + t["artist"] if t.get("artist") else "")) if t and music.playing
                          else "No music is playing right now.")
        if not args:
            return action("song", word, reply="%s, type !sr and part of a song name" % m.author)
        if not music.tracks:
            return action("song", word, reply="Song requests need music on the streamer's Music page.")
        key = viewer_key(m)
        if not m.mod and now - self.cooldowns.get(("sr", key), -1e9) < 30:
            return action("song", word, "cooldown")
        mine = sum(1 for _, who in music.requests if who == key)
        if not m.mod and mine >= int(self.s.get("sr_per_viewer") or 1):
            return action("song", word, reply="%s, your song is already in the queue" % m.author)
        if len(music.requests) >= int(self.s.get("sr_max") or 10):
            return action("song", word, reply="The song queue is full right now.")
        words = [w for w in re.findall(r"\w+", args.lower()) if len(w) > 1] or [args.lower()]
        best, score = None, 0
        for i, t in enumerate(music.tracks):
            hay = ("%s %s %s" % (t.get("title", ""), t.get("artist", ""), os.path.basename(t.get("path", "")))).lower()
            hit = sum(1 for w in words if w in hay)
            if hit > score:
                best, score = i, hit
        if best is None:
            return action("song", word, reply="%s, no song matches \"%s\"" % (m.author, args[:40]))
        self.cooldowns[("sr", key)] = now
        self.stats.count("song")
        place = music.request(best, key)
        title = music.tracks[best]["title"]
        return action("song", word, reply=("Playing %s now" % title) if place == 0 else "Added %s to the queue (#%d)" % (title, place),
                      toast="Song request: %s (%s)" % (title, m.author))

    # ----- timers: messages posted every few minutes, only when chat is active -----
    def due_timers(self, now):
        if not self.s.get("timers_on"):
            return []
        out = []
        for i, t in enumerate(self.s.get("timers") or []):
            if not isinstance(t, dict) or not (t.get("message") or "").strip():
                continue
            self.timer_last.setdefault(i, now)
            self.lines_since.setdefault(i, 0)
            if now - self.timer_last[i] >= max(1, float(t.get("minutes") or 10)) * 60 and self.lines_since[i] >= int(t.get("lines") or 0):
                self.timer_last[i], self.lines_since[i] = now, 0
                out.append(t)
        return out

    def reset_timers(self):
        self.timer_last, self.lines_since = {}, {}

    # ----- overlay -----
    def widgets(self, now):
        return {"counters": [{"label": c.get("label") or c["name"].title(), "value": int(c.get("value") or 0)}
                             for c in self.counters() if c.get("overlay", True)],
                "poll": self.poll.state(now), "giveaway": self.giveaway.state(),
                "prediction": self.prediction.state(now), "queue": self.queue.state(),
                "goals": [{"title": g["title"], "value": int(float(g.get("value") or 0)), "target": int(g.get("target") or 1)}
                          for g in self.goals()] if self.s.get("goals_overlay") else [],
                "latest": [{"label": k, "value": v} for k, v in self.latest.items()] if self.s.get("latest_overlay") else [],
                "pointsName": self.points.name}
