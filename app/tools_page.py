"""Three main pages that share the stream tools: Loyalty (points, levels, shop), Engage (polls, predictions, giveaways, queue,
counters, goals) and Stream tools (timers, welcomes, song requests, paid read-aloud, hotkeys, summary)."""
import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QPlainTextEdit,
                               QSpinBox, QVBoxLayout, QWidget)

from .commands import clean_name
from .commands_page import MODES, _button, _combo
from .hotkeys import ACTIONS
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import SubPage, bind_switch, field_row, hrow, info_box, option_switch_row, section_card


def _spin(settings, key, lo, hi, suffix=""):
    sp = QSpinBox()
    sp.setRange(lo, hi)
    sp.setSuffix(suffix)
    sp.setValue(int(settings.get(key) or 0))
    sp.valueChanged.connect(lambda v: settings.set(key, v))
    return sp


def _text(settings, key, placeholder="", max_len=200):
    edit = QLineEdit(settings.get(key) or "")
    edit.setMaxLength(max_len)
    edit.setPlaceholderText(placeholder)
    edit.editingFinished.connect(lambda: settings.set(key, edit.text().strip()))
    return edit


def _note(text=""):
    lab = QLabel(text)
    lab.setObjectName("settingNote")
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def _clear(layout):
    while layout.count():
        w = layout.takeAt(0).widget()
        if w is not None:
            w.deleteLater()


GOAL_CHOICES = (("Counts follows", "follows"), ("Counts subs", "subs"), ("Counts members", "members"), ("Adds up money", "money"), ("I move it by hand", "manual"))


class TimerDialog(QDialog):
    def __init__(self, parent, item):
        super().__init__(parent)
        self.setWindowTitle("Edit timer" if item else "New timer")
        self.setMinimumWidth(520)
        self.item = dict(item or {})
        lay = QVBoxLayout(self)
        self.message = QPlainTextEdit(self.item.get("message", ""))
        self.message.setPlaceholderText("Follow on Instagram @me and join the Discord: discord.gg/...")
        self.message.setFixedHeight(80)
        lay.addWidget(field_row("Message", "Posted again and again while you are live.", self.message))
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 240)
        self.minutes.setSuffix(" min")
        self.minutes.setValue(int(self.item.get("minutes", 15)))
        lay.addWidget(field_row("Every", "How often it is posted.", self.minutes))
        self.lines = QSpinBox()
        self.lines.setRange(0, 500)
        self.lines.setValue(int(self.item.get("lines", 5)))
        lay.addWidget(field_row("Only after this many chat messages", "Stops it repeating into an empty chat.", self.lines))
        self.mode = _combo(MODES, self.item.get("mode") or "reply")
        lay.addWidget(field_row("Post by", "Chat posts need the account signed in on the Connect page.", self.mode))
        self.error = QLabel("")
        self.error.setStyleSheet("color:#ff8fa3;")
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        need = self.layout().totalHeightForWidth(self.width())
        if need > self.height():
            self.resize(self.width(), need)

    def _save(self):
        text = self.message.toPlainText().strip()
        if not text:
            return self.error.setText("Type the message.")
        if len(text) > 400:
            return self.error.setText("Keep it under 400 characters.")
        self.item.update(message=text, minutes=self.minutes.value(), lines=self.lines.value(), mode=self.mode.currentData())
        self.accept()


class ToolsPage(SubPage):
    def __init__(self, settings, tools, host):
        super().__init__()
        self.s, self.tools, self.host = settings, tools, host
        self._winner_names = ()
        self.loyalty, self.engage = SubPage(), SubPage()
        self.pages = (self, self.loyalty, self.engage)
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]
        sw = lambda key: bind_switch(self.s, key, accent)

        # ---------- points ----------
        points, pl = section_card("Loyalty points", "Viewers earn points by chatting and spend them on memes, giveaways and !gamble.")
        pl.addWidget(option_switch_row("Points", "Viewers can use !points, !top and !gamble.", sw("points_on")))
        pl.addWidget(field_row("Name of the points", "Shown in chat replies, like coins or bhai-points.", _text(self.s, "points_name", "coins", 20)))
        pl.addWidget(field_row("For chatting", "Given at most once per cooldown, so spam earns nothing extra.",
                               hrow(_spin(self.s, "points_per_msg", 0, 1000, " pts"), QLabel("every"), _spin(self.s, "points_msg_cooldown", 0, 3600, " s"))))
        pl.addWidget(field_row("Watching bonus", "For everyone who chatted in the last 10 minutes.",
                               hrow(_spin(self.s, "points_bonus", 0, 1000, " pts"), QLabel("every"), _spin(self.s, "points_bonus_minutes", 1, 120, " min"))))
        pl.addWidget(option_switch_row("!gamble", "Double or nothing, 50/50.", sw("gamble_on")))
        pl.addWidget(field_row("Smallest bet and cooldown", "", hrow(_spin(self.s, "gamble_min", 1, 100000, " pts"), _spin(self.s, "gamble_cooldown", 0, 3600, " s"))))
        self.top_label = _note()
        pl.addWidget(field_row("Top viewers", "", self.top_label))
        self.reset_btn = _button("Reset all points", "danger")
        self.reset_btn.clicked.connect(self._reset_points)
        pl.addWidget(hrow(self.reset_btn))

        # ---------- levels ----------
        levels, ll = section_card("Levels", "Viewers level up by chatting and staying. Each level takes more XP than the last. !level shows their progress.")
        ll.addWidget(option_switch_row("Levels", "Needs Points to be on.", sw("levels_on")))
        ll.addWidget(field_row("XP for level 2", "Level 3 takes 4 times this, level 4 takes 9 times.", _spin(self.s, "level_base", 10, 100000, " XP")))
        ll.addWidget(field_row("XP for chatting and for the watching bonus", "Given at the same times as points.",
                               hrow(_spin(self.s, "level_xp_msg", 0, 1000, " XP"), _spin(self.s, "level_xp_bonus", 0, 1000, " XP"))))
        ll.addWidget(option_switch_row("Post level-ups in chat", "Needs the account signed in on the Connect page.", sw("level_announce")))
        ll.addWidget(field_row("Level-up message", "{user} is the viewer, {level} is the new level.", _text(self.s, "level_text", "{user} reached level {level}!", 200)))

        # ---------- shop ----------
        shop, hl = section_card("Points shop", "Viewers see your rewards with !shop and buy with !buy 1. You deliver the reward yourself; purchases are listed here.")
        hl.addWidget(option_switch_row("Shop", "Needs Points to be on.", sw("shop_on")))
        self.shop_list = QVBoxLayout()
        hl.addLayout(self.shop_list)
        self.shop_name, self.shop_cost, self.shop_stock = QLineEdit(), QSpinBox(), QSpinBox()
        self.shop_name.setMaxLength(40)
        self.shop_name.setPlaceholderText("Pick my next game")
        self.shop_cost.setRange(1, 10000000)
        self.shop_cost.setValue(500)
        self.shop_cost.setSuffix(" pts")
        self.shop_stock.setRange(-1, 9999)
        self.shop_stock.setValue(-1)
        self.shop_stock.setSpecialValueText("Unlimited")
        add_item = _button("Add reward", "primary")
        add_item.clicked.connect(self._add_shop_item)
        hl.addWidget(hrow(self.shop_name, self.shop_cost, self.shop_stock, add_item))
        self.shop_log = _note()
        hl.addWidget(field_row("Recent purchases", "", self.shop_log))
        clear_log = _button("Clear purchases")
        clear_log.clicked.connect(self._clear_shop_log)
        hl.addWidget(hrow(clear_log))

        # ---------- poll ----------
        poll, ql = section_card("Chat poll", "One poll for every connected chat at once. Viewers vote with !vote 2, or just 2. Shows on the /widgets overlay.")
        self.poll_q = QLineEdit()
        self.poll_q.setMaxLength(120)
        self.poll_q.setPlaceholderText("Which game next?")
        ql.addWidget(field_row("Question", "", self.poll_q))
        self.poll_opts = []
        for i in range(5):
            o = QLineEdit()
            o.setMaxLength(60)
            o.setPlaceholderText("Option %d%s" % (i + 1, "" if i < 2 else " (optional)"))
            o.setMaximumWidth(420)
            self.poll_opts.append(o)
            ql.addWidget(o)
        self.poll_secs = QSpinBox()
        self.poll_secs.setRange(10, 3600)
        self.poll_secs.setSuffix(" s")
        self.poll_secs.setValue(90)
        ql.addWidget(field_row("Open for", "", self.poll_secs))
        ql.addWidget(option_switch_row("A number alone counts as a vote", "While a poll is open, a message like 2 is a vote and is not read aloud.", sw("poll_numbers")))
        start, end = _button("Start poll", "primary"), _button("End now")
        start.clicked.connect(lambda: self.host.start_poll(self.poll_q.text(), [o.text() for o in self.poll_opts], self.poll_secs.value()))
        end.clicked.connect(self.host.end_poll)
        ql.addWidget(hrow(start, end))
        self.poll_label = _note()
        ql.addWidget(self.poll_label)

        # ---------- prediction ----------
        guess, bl = section_card("Prediction", "Viewers bet points with !bet 1 100. Winners get their bet back plus a fair share of the losing side. Shows on the /widgets overlay.")
        self.bet_q = QLineEdit()
        self.bet_q.setMaxLength(120)
        self.bet_q.setPlaceholderText("Will I win this match?")
        bl.addWidget(field_row("Question", "", self.bet_q))
        self.bet_opts = []
        for i in range(4):
            o = QLineEdit()
            o.setMaxLength(60)
            o.setPlaceholderText("Outcome %d%s" % (i + 1, "" if i < 2 else " (optional)"))
            o.setMaximumWidth(420)
            self.bet_opts.append(o)
            bl.addWidget(o)
        self.bet_secs = QSpinBox()
        self.bet_secs.setRange(15, 1800)
        self.bet_secs.setSuffix(" s")
        self.bet_secs.setValue(120)
        bl.addWidget(field_row("Bets stay open for", "Locks by itself after this time.", self.bet_secs))
        start_bet, lock_bet, cancel_bet = _button("Start", "primary"), _button("Lock bets"), _button("Cancel and refund", "danger")
        start_bet.clicked.connect(lambda: self.host.start_prediction(self.bet_q.text(), [o.text() for o in self.bet_opts], self.bet_secs.value()))
        lock_bet.clicked.connect(self.host.lock_prediction)
        cancel_bet.clicked.connect(self.host.cancel_prediction)
        bl.addWidget(hrow(start_bet, lock_bet, cancel_bet))
        self.bet_label = _note()
        bl.addWidget(self.bet_label)
        self.bet_winners = QVBoxLayout()
        bl.addLayout(self.bet_winners)

        # ---------- giveaway ----------
        give, gl = section_card("Giveaway", "Viewers type the keyword to enter, from any platform. Pick as many winners as you like.")
        self.give_kw = _text(self.s, "giveaway_keyword", "join", 30)
        gl.addWidget(field_row("Keyword", "Viewers type it with !, like !join.", self.give_kw))
        gl.addWidget(field_row("Entry cost", "Loyalty points needed to enter (0 = free).", _spin(self.s, "giveaway_cost", 0, 1000000, " pts")))
        open_, close, pick, clear = _button("Open", "primary"), _button("Close entries"), _button("Pick winner"), _button("Clear")
        open_.clicked.connect(lambda: self.host.open_giveaway(self.give_kw.text(), int(self.s.get("giveaway_cost") or 0)))
        close.clicked.connect(self.host.close_giveaway)
        pick.clicked.connect(self.host.pick_winner)
        clear.clicked.connect(self.host.clear_giveaway)
        gl.addWidget(hrow(open_, close, pick, clear))
        self.give_label = _note()
        gl.addWidget(self.give_label)

        # ---------- viewer queue ----------
        line, vl = section_card("Viewer queue", "Viewers join with !queue, check with !place and go with !leave. Moderators can use !next and !clearqueue. Shows on the /widgets overlay.")
        vl.addWidget(field_row("Longest queue", "", _spin(self.s, "queue_limit", 1, 500)))
        self.queue_toggle = _button("Open queue", "primary")
        self.queue_toggle.clicked.connect(lambda: self.host.set_queue(not self.tools.queue.open))
        next_person, empty = _button("Next viewer"), _button("Clear", "danger")
        next_person.clicked.connect(self.host.next_in_queue)
        empty.clicked.connect(self.host.clear_queue)
        vl.addWidget(hrow(self.queue_toggle, next_person, empty))
        self.queue_label = _note()
        vl.addWidget(self.queue_label)

        # ---------- goals ----------
        goals, ol = section_card("Goals", "Progress bars on the /widgets overlay. They count by themselves from your alerts, or you can move them by hand.")
        ol.addWidget(option_switch_row("Show goals on stream", "", sw("goals_overlay")))
        ol.addWidget(option_switch_row("Show the latest supporters on stream", "Latest follower, sub and tip, in the bottom-right corner.", sw("latest_overlay")))
        self.goal_list = QVBoxLayout()
        ol.addLayout(self.goal_list)
        self.goal_title, self.goal_target = QLineEdit(), QSpinBox()
        self.goal_title.setMaxLength(40)
        self.goal_title.setPlaceholderText("Road to 1000 followers")
        self.goal_target.setRange(1, 100000000)
        self.goal_target.setValue(100)
        self.goal_source = _combo(GOAL_CHOICES, "follows")
        add_goal = _button("Add goal", "primary")
        add_goal.clicked.connect(self._add_goal)
        ol.addWidget(hrow(self.goal_title, self.goal_target, self.goal_source, add_goal))
        ol.addWidget(_note("Money goals add up the numbers as they arrive and do not convert between currencies."))

        # ---------- counters ----------
        counters, cl = section_card("Counters", "Deaths, wins, push-ups... !death shows it; moderators use !death+ and !death- . Shown on the /widgets overlay.")
        self.counter_list = QVBoxLayout()
        cl.addLayout(self.counter_list)
        self.counter_name, self.counter_label = QLineEdit(), QLineEdit()
        self.counter_name.setPlaceholderText("death")
        self.counter_label.setPlaceholderText("Deaths")
        self.counter_name.setToolTip("The chat command, without !")
        self.counter_label.setToolTip("The name shown in chat and on stream")
        add_counter = _button("Add counter", "primary")
        add_counter.clicked.connect(self._add_counter)
        cl.addWidget(hrow(self.counter_name, self.counter_label, add_counter))
        self.counter_error = _note()
        cl.addWidget(self.counter_error)

        # ---------- welcome ----------
        welcome, wl = section_card("Welcome new chatters", "Greets a viewer the first time they chat.")
        wl.addWidget(option_switch_row("Welcome messages", "", sw("welcome_on")))
        mode = _combo((("First time ever in your chat", "ever"), ("First message of each stream", "stream")), self.s.get("welcome_mode"))
        mode.currentIndexChanged.connect(lambda _: self.s.set("welcome_mode", mode.currentData()))
        wl.addWidget(field_row("Who gets welcomed", "", mode))
        wl.addWidget(field_row("Message", "{user} is the viewer's name.", _text(self.s, "welcome_text", "Welcome {user}!", 200)))
        wl.addWidget(option_switch_row("Read it aloud", "", sw("welcome_speak")))
        wl.addWidget(option_switch_row("Reply in chat", "Needs the account signed in on the Connect page.", sw("welcome_reply")))
        forget = _button("Forget who has chatted before")
        forget.clicked.connect(lambda: (self.tools.forget_viewers(), forget.setText("Forgotten")))
        wl.addWidget(hrow(forget))

        # ---------- timers ----------
        timers, tl = section_card("Timers", "Messages posted every few minutes while you are live, like Nightbot timers.")
        tl.addWidget(option_switch_row("Timers", "", sw("timers_on")))
        self.timer_list = QVBoxLayout()
        tl.addLayout(self.timer_list)
        add_timer = _button("Add timer", "primary")
        add_timer.clicked.connect(lambda: self._edit_timer(None))
        tl.addWidget(hrow(add_timer))

        # ---------- song requests ----------
        songs, sl = section_card("Song requests", "Viewers type !sr and part of a song name from your Music page library. !song shows what is playing.")
        sl.addWidget(option_switch_row("Song requests", "", sw("sr_on")))
        sl.addWidget(field_row("Queue size and songs per viewer", "Moderators skip these limits.",
                               hrow(_spin(self.s, "sr_max", 1, 50), _spin(self.s, "sr_per_viewer", 1, 10))))
        self.song_label = _note()
        sl.addWidget(self.song_label)
        clear_songs = _button("Clear requests")
        clear_songs.clicked.connect(self.host.clear_song_requests)
        sl.addWidget(hrow(clear_songs))

        # ---------- paid read-aloud ----------
        say, yl = section_card("Paid read-aloud", "Viewers spend points on !say hello to have a message read aloud. Links and blocked words are never read.")
        yl.addWidget(option_switch_row("!say", "Needs Points to be on.", sw("say_on")))
        yl.addWidget(field_row("Cost and cooldown per viewer", "Moderators skip both.", hrow(_spin(self.s, "say_cost", 0, 1000000, " pts"), _spin(self.s, "say_cooldown", 0, 3600, " s"))))

        # ---------- hotkeys ----------
        keys, kl = section_card("Hotkeys", "Work everywhere, even in a fullscreen game. Click a box and press the keys; Backspace clears it.")
        self.key_edits = {}
        for key, label in ACTIONS:
            edit = QKeySequenceEdit(self.s.get(key) or "")
            edit.setMaximumSequenceLength(1)
            edit.setClearButtonEnabled(True)
            self.key_edits[key] = edit
            kl.addWidget(field_row(label, "", edit))
        apply_keys = _button("Save hotkeys", "primary")
        apply_keys.clicked.connect(self._save_keys)
        kl.addWidget(hrow(apply_keys))
        self.key_status = _note()
        kl.addWidget(self.key_status)

        # ---------- summary ----------
        summary, ml = section_card("Stream summary", "Counts this stream's chat, supporters and tools. Starts when a stream connects.")
        self.summary_label = _note()
        ml.addWidget(self.summary_label)
        ml.addWidget(option_switch_row("Post to Discord when the stream ends", "Uses the webhook from the Discord page.", sw("summary_post")))
        post, reset = _button("Post to Discord now", "primary"), _button("Start a new summary")
        post.clicked.connect(self.host.post_summary)
        reset.clicked.connect(self.host.reset_summary)
        ml.addWidget(hrow(post, reset))

        for page, tabs in ((self.loyalty, (("Points", points), ("Levels", levels), ("Shop", shop))),
                           (self.engage, (("Polls", poll), ("Predictions", guess), ("Giveaways", give), ("Queue", line), ("Counters", counters), ("Goals", goals))),
                           (self, (("Timers", timers), ("Welcome", welcome), ("Song requests", songs), ("Paid read-aloud", say), ("Hotkeys", keys), ("Summary", summary)))):
            for title, card in tabs:
                page.add_tab(title).addWidget(card)
            page.finish()
        self.refresh()

    # ---------- refresh ----------
    def refresh(self):
        self.refresh_lists()
        self.refresh_live()

    def refresh_lists(self):
        _clear(self.counter_list)
        for c in self.tools.counters():
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            text = QLabel("<b>!%s</b> &nbsp;%s: <b>%d</b>" % (html.escape(c["name"]), html.escape(c.get("label") or c["name"].title()), int(c.get("value") or 0)))
            rl.addWidget(text, 1)
            for label, change in (("−", -1), ("+", 1)):
                b = _button(label)
                b.setFixedWidth(36)
                b.clicked.connect(lambda _=False, n=c["name"], d=change: (self.tools.bump_counter(n, d), self.host.tools_changed()))
                rl.addWidget(b)
            reset = _button("0")
            reset.setToolTip("Reset to zero")
            reset.clicked.connect(lambda _=False, n=c["name"], v=int(c.get("value") or 0): (self.tools.bump_counter(n, -v), self.host.tools_changed()))
            delete = _button("Delete", "danger")
            delete.clicked.connect(lambda _=False, n=c["name"]: self._delete_counter(n))
            rl.addWidget(reset)
            rl.addWidget(delete)
            row.name = c["name"]
            self.counter_list.addWidget(row)
        if not self.tools.counters():
            self.counter_list.addWidget(_note("No counters yet."))
        _clear(self.timer_list)
        for i, t in enumerate(self.s.get("timers") or []):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            mode = dict((v, k) for k, v in MODES).get(t.get("mode") or "reply", "")
            text = QLabel("<b>every %d min</b> &nbsp;<span style='opacity:.75'>%s · after %d messages · %s</span>"
                          % (int(t.get("minutes") or 15), html.escape((t.get("message") or "")[:90]), int(t.get("lines") or 0), html.escape(mode)))
            text.setWordWrap(True)
            rl.addWidget(text, 1)
            edit, delete = _button("Edit"), _button("Delete", "danger")
            edit.clicked.connect(lambda _=False, n=i: self._edit_timer(n))
            delete.clicked.connect(lambda _=False, n=i: self._delete_timer(n))
            rl.addWidget(edit, 0, Qt.AlignTop)
            rl.addWidget(delete, 0, Qt.AlignTop)
            self.timer_list.addWidget(row)
        if not self.s.get("timers"):
            self.timer_list.addWidget(_note("No timers yet."))
        _clear(self.shop_list)
        for i, item in enumerate(self.tools.shop_items()):
            stock = int(item.get("stock", -1))
            delete = _button("Delete", "danger")
            delete.clicked.connect(lambda _=False, n=i: self._delete_shop_item(n))
            self.shop_list.addWidget(self._line("<b>%d. %s</b> &nbsp;%d pts · %s" % (i + 1, html.escape(item["name"]), int(item.get("cost") or 0),
                                                                                     "unlimited" if stock < 0 else "%d left" % stock), delete))
        if not self.tools.shop_items():
            self.shop_list.addWidget(_note("No rewards yet."))
        _clear(self.goal_list)
        for i, g in enumerate(self.tools.goals()):
            minus, plus, delete = _button("\u2212"), _button("+"), _button("Delete", "danger")
            for b in (minus, plus):
                b.setFixedWidth(36)
            minus.clicked.connect(lambda _=False, n=i: (self.tools.bump_goal(n, -1), self.host.tools_changed(lists=True)))
            plus.clicked.connect(lambda _=False, n=i: (self.tools.bump_goal(n, 1), self.host.tools_changed(lists=True)))
            delete.clicked.connect(lambda _=False, n=i: self._delete_goal(n))
            self.goal_list.addWidget(self._line("<b>%s</b> &nbsp;%d / %d" % (html.escape(g["title"]), int(float(g.get("value") or 0)), int(g.get("target") or 1)), minus, plus, delete))
        if not self.tools.goals():
            self.goal_list.addWidget(_note("No goals yet."))

    def _line(self, text, *buttons):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 2, 0, 2)
        label = QLabel(text)
        label.setWordWrap(True)
        rl.addWidget(label, 1)
        for b in buttons:
            rl.addWidget(b)
        return row

    def refresh_live(self, now=None):
        import time
        now = time.time() if now is None else now
        top = self.tools.points.top(5)
        self.top_label.setText(", ".join("%s %d" % t for t in top) if top else "Nobody has points yet.")
        self.poll_label.setText(self.tools.poll.summary(now))
        g = self.tools.giveaway
        if g.active or g.entries or g.winners:
            state = "Open: type !%s" % g.keyword if g.active else "Entries closed"
            won = ("\nWinners: " + ", ".join("%s (%s)" % (w[1], w[2].title()) for w in g.winners)) if g.winners else ""
            self.give_label.setText("%s · %d entered%s" % (state, len(g.entries), won))
        else:
            self.give_label.setText("No giveaway running.")
        music = self.tools.music
        if music is not None and music.requests:
            self.song_label.setText("Queue: " + ", ".join(music.tracks[i]["title"] for i, _ in music.requests if 0 <= i < len(music.tracks)))
        else:
            self.song_label.setText("No song requests waiting." if music is None or music.tracks else "Add music on the Music page first.")
        self.summary_label.setText("\n".join(self.tools.stats.lines(now)) if self.tools.stats.started else "Connect a stream to start counting.")
        p = self.tools.prediction
        if p.active:
            pools = p.pools()
            self.bet_label.setText("%s\n%s" % ("Bets open" if p.open else "Bets locked: choose what happened", " | ".join("%s: %d" % (o, n) for o, n in zip(p.options, pools))))
        else:
            self.bet_label.setText(p.result or "No prediction running.")
        names = tuple(p.options) if p.active else ()
        if names != self._winner_names:
            self._winner_names = names
            _clear(self.bet_winners)
            for i, option in enumerate(names):
                b = _button("%s won" % option, "primary")
                b.clicked.connect(lambda _=False, n=i + 1: self.host.resolve_prediction(n))
                self.bet_winners.addWidget(hrow(b))
        q = self.tools.queue
        self.queue_toggle.setText("Close queue" if q.open else "Open queue")
        self.queue_label.setText("Waiting: " + ", ".join("%d. %s" % (i + 1, x[1]) for i, x in enumerate(q.people[:12])) if q.people else ("Queue open, nobody waiting." if q.open else "Queue closed."))
        self.shop_log.setText(", ".join("%s: %s" % r for r in self.tools.redeemed[:8]) or "Nothing bought yet.")

    # ---------- actions ----------
    def _reset_points(self):
        if self.reset_btn.text() != "Click again to reset":       # a second click confirms, no popup needed
            self.reset_btn.setText("Click again to reset")
            return
        self.tools.points.reset()
        self.reset_btn.setText("Reset all points")
        self.refresh_live()

    def _add_counter(self):
        name = clean_name(self.counter_name.text())
        items = self.tools.counters()
        if not name:
            return self.counter_error.setText("Type a one-word command name, like death.")
        if any(c["name"] == name for c in items):
            return self.counter_error.setText("!%s already exists." % name)
        items.append({"name": name, "label": self.counter_label.text().strip()[:30] or name.title(), "value": 0, "overlay": True})
        self.s.set("counters", items)
        self.counter_name.clear()
        self.counter_label.clear()
        self.counter_error.setText("")
        self.host.tools_changed()

    def _add_shop_item(self):
        name = self.shop_name.text().strip()
        if not name:
            return
        self.s.set("shop_items", self.tools.shop_items() + [{"name": name, "cost": self.shop_cost.value(), "stock": self.shop_stock.value()}])
        self.shop_name.clear()
        self.refresh_lists()

    def _delete_shop_item(self, index):
        items = self.tools.shop_items()
        del items[index]
        self.s.set("shop_items", items)
        self.refresh_lists()

    def _clear_shop_log(self):
        self.tools.redeemed = []
        self.refresh_live()

    def _add_goal(self):
        title = self.goal_title.text().strip()
        if not title:
            return
        self.s.set("goals", self.tools.goals() + [{"title": title, "target": self.goal_target.value(), "source": self.goal_source.currentData(), "value": 0}])
        self.goal_title.clear()
        self.host.tools_changed(lists=True)

    def _delete_goal(self, index):
        items = self.tools.goals()
        del items[index]
        self.s.set("goals", items)
        self.host.tools_changed(lists=True)

    def _delete_counter(self, name):
        self.s.set("counters", [c for c in self.tools.counters() if c["name"] != name])
        self.host.tools_changed()

    def _edit_timer(self, index):
        items = [dict(t) for t in self.s.get("timers") or []]
        dialog = TimerDialog(self, items[index] if index is not None else None)
        if dialog.exec() != QDialog.Accepted:
            return
        if index is None:
            items.append(dialog.item)
        else:
            items[index] = dialog.item
        self.s.set("timers", items)
        self.tools.reset_timers()
        self.refresh_lists()

    def _delete_timer(self, index):
        items = [dict(t) for t in self.s.get("timers") or []]
        del items[index]
        self.s.set("timers", items)
        self.tools.reset_timers()
        self.refresh_lists()

    def _save_keys(self):
        for key, edit in self.key_edits.items():
            self.s.set(key, edit.keySequence().toString())
        problems = self.host.apply_hotkeys()
        self.key_status.setText("\n".join(problems) if problems else "Hotkeys saved and active.")
