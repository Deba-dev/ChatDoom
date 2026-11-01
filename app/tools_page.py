"""Stream tools page: loyalty points, chat polls, giveaways, counters, welcomes, timers, song requests, hotkeys, summary."""
import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QPlainTextEdit,
                               QSpinBox, QVBoxLayout, QWidget)

from .commands import clean_name
from .commands_page import MODES, _button, _combo
from .hotkeys import ACTIONS
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import FormScrollArea, TwoColumnBoard, bind_switch, field_row, hrow, info_box, option_switch_row, section_card


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


class ToolsPage(FormScrollArea):
    def __init__(self, settings, tools, host):
        super().__init__()
        self.s, self.tools, self.host = settings, tools, host
        inner = QWidget()
        inner.setObjectName("page")
        self.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 8, 12, 12)
        lay.setSpacing(14)
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

        for card_layout in (pl, ql, gl, cl, wl, tl, sl, kl, ml):
            card_layout.addStretch(1)                  # cards in a row share a height; keep their contents at the top
        board = TwoColumnBoard()
        board.set_cards([(points, poll), (give, counters), (welcome, timers), (songs, keys)], summary)
        lay.addWidget(info_box("Overlays for OBS: <b>/widgets</b> (counters, poll, giveaway) is on the OBS overlays page.", "Show it on stream"))
        lay.addWidget(board)
        lay.addStretch(1)
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
