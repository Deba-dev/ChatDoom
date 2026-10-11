"""YouTube auto-moderation page: add the ChatVoice bot to your channel, verify it is yours, choose the rules."""
import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from .theme import DEFAULT_THEME, THEMES
from .ui_kit import (FormScrollArea, bind_switch, copy_row, field_row, hrow, info_box, make_badge, option_switch_row,
                     section_card, set_badge, status_row, step_row)

BOT_STATES = {"online": ("pillOn", "\u25cf  Bot online"), "waking": ("pillWait", "\u25cf  Waking up..."),
              "offline": ("pillBad", "\u25cf  Bot offline"), "unknown": ("pill", "\u25cf  Checking...")}


class YtModPage(FormScrollArea):
    def __init__(self, settings, moderator):
        super().__init__()
        self.s, self.mod = settings, moderator
        self._last_info = 0.0
        inner = QWidget()
        inner.setObjectName("page")
        self.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 8, 12, 12)
        lay.setSpacing(14)
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]

        # ---------- master switch ----------
        c, cl = section_card("YouTube auto-moderation",
                             "A moderator bot that removes spam, links and blocked words from your live chat, like Nightbot. "
                             "Set it up once in three steps.")
        self.status = make_badge("\u25cf  Not set up", "pill")
        cl.addWidget(status_row(self.status))
        cl.addWidget(option_switch_row("Auto-moderation", "Turn the bot's clean-up on or off without removing your setup.",
                                       bind_switch(self.s, "yt_mod_on", accent)))
        lay.addWidget(c)

        # ---------- step 1: add the bot ----------
        c, cl = section_card("Step 1 \u2014 Add the bot to your channel",
                             "The bot needs to be a moderator of your channel, so YouTube lets it remove messages. You do this once, in YouTube Studio.")
        self.bot_badge = make_badge("\u25cf  Checking...", "pill")
        self.bot_title = QLabel(self.s.get("yt_bot_title"))
        self.bot_title.setObjectName("settingName")
        cl.addWidget(status_row(self.bot_badge, self.bot_title))
        wrap, self.handle = copy_row(self.s.get("yt_bot_handle"), "", "Copy bot name")
        cl.addWidget(wrap)
        cl.addWidget(step_row(1, "Open YouTube Studio", "Go to studio.youtube.com and open <b>Settings \u2192 Community</b>."))
        self.step2 = step_row(2, "Add the bot as a moderator", "")
        cl.addWidget(self.step2)
        cl.addWidget(step_row(3, "Come back here", "YouTube can take a minute to apply it. Then do Step 2 below."))
        studio = QPushButton("Open YouTube Studio")
        studio.setObjectName("primary")
        studio.setCursor(Qt.PointingHandCursor)
        studio.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://studio.youtube.com/")))
        cl.addWidget(hrow(studio))
        cl.addWidget(info_box("Moderators can only remove chat messages and time people out. They cannot see anything private or change your channel.",
                              "Safe to add"))
        lay.addWidget(c)

        # ---------- step 2: verify ----------
        c, cl = section_card("Step 2 \u2014 Verify your channel",
                             "This proves the stream is yours, so nobody else can use the bot on your chat. You need to be live. "
                             "Paste your live link on the Connect page first.")
        self.v_badge = make_badge("\u25cf  Not verified", "pill")
        self.v_text = QLabel("")
        self.v_text.setObjectName("sub")
        self.v_text.setWordWrap(True)
        cl.addWidget(status_row(self.v_badge, self.v_text))
        self.code_box = info_box("", "Type this code in your own YouTube live chat")
        self.code_label = QLabel("")
        self.code_label.setObjectName("pageTitle")
        self.code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.code_box.layout().addWidget(self.code_label)
        self.code_box.hide()
        cl.addWidget(self.code_box)
        self.verify_btn = QPushButton("Verify my channel")
        self.verify_btn.setObjectName("primary")
        self.verify_btn.setCursor(Qt.PointingHandCursor)
        self.verify_btn.clicked.connect(self.verify)
        self.remove_btn = QPushButton("Remove verification")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.clicked.connect(self.mod.forget)
        cl.addWidget(hrow(self.verify_btn, self.remove_btn))
        lay.addWidget(c)

        # ---------- step 3: rules ----------
        c, cl = section_card("Step 3 \u2014 What the bot removes",
                             "Moderators and you are never touched. Start in test mode: CHATDOOM only tells you what it WOULD remove.")
        for title, note, key in (("Messages with blocked words", "The list on the Moderation page.", "mod_del_blocked"),
                                 ("Messages with links", "Links from viewers who are not moderators.", "mod_del_links"),
                                 ("Spam and repeated messages", "Walls of the same letter, copy-pasted spam.", "mod_del_spam"),
                                 ("Test mode", "Only show what would be removed. Turn off to really remove.", "mod_dry_run")):
            cl.addWidget(option_switch_row(title, note, bind_switch(self.s, key, accent)))
        for title, note, key, lo, hi, suffix in (("Daily action limit", "Most removals or time-outs per day. Keeps your share of YouTube's daily allowance safe.", "mod_budget", 1, 150, ""),
                                                 ("Time out after", "Time out a viewer after this many removals in 10 minutes.", "mod_timeout_after", 2, 20, " removals"),
                                                 ("Time-out length", "How long a timed-out viewer cannot chat.", "mod_timeout_secs", 10, 3600, " s")):
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setSuffix(suffix)
            sp.setValue(int(self.s.get(key)))
            sp.valueChanged.connect(lambda v, k=key: (self.s.set(k, v), self.refresh()))
            cl.addWidget(field_row(title, note, sp))
        self.used = QLabel("")
        self.used.setObjectName("settingNote")
        cl.addWidget(self.used)
        lay.addWidget(c)

        lay.addWidget(info_box("CHATDOOM reads your chat itself and asks the bot to remove messages, so it only works while CHATDOOM is open "
                               "and connected to your YouTube live chat. You never sign in to Google.", "How it works"))
        lay.addStretch(1)

        self.poll = QTimer(self)                       # while a code is showing, check for it every few seconds
        self.poll.setInterval(6000)
        self.poll.timeout.connect(self._poll_code)
        self.mod.changed.connect(self.refresh)
        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        if time.time() - self._last_info > 60:        # wakes the bot if the free host put it to sleep
            self._last_info = time.time()
            self.mod.refresh_info()

    # ----- actions -----
    def verify(self):
        self.mod.start_verify()
        self.poll.start()

    def _poll_code(self):
        if not self.mod.code or time.time() > self.mod.code_exp:
            self.poll.stop()
            if self.mod.code:
                self.mod.code, self.mod.message = "", "The code expired. Press Verify again."
                self.refresh()
            return
        self.mod.check_verify()

    # ----- screen state -----
    def refresh(self):
        handle = self.s.get("yt_bot_handle")
        self.handle.setText(handle)
        self.bot_title.setText(self.s.get("yt_bot_title"))
        self.step2.body.setText("Under <b>Moderators</b>, add <b>%s</b> (the name above) and save." % handle)
        kind, text = BOT_STATES.get(self.mod.bot_state, BOT_STATES["unknown"])
        set_badge(self.bot_badge, text, kind)
        verified = self.mod.verified
        if verified:
            set_badge(self.v_badge, "\u25cf  Verified", "pillOn")
            self.v_text.setText(self.s.get("yt_channel_title") or "Your channel")
            self.poll.stop()
        elif self.mod.code:
            set_badge(self.v_badge, "\u25cf  Waiting for your code", "pillWait")
            self.v_text.setText(self.mod.message)
        else:
            set_badge(self.v_badge, "\u25cf  Not verified", "pill")
            self.v_text.setText(self.mod.message)
        self.code_box.setVisible(bool(self.mod.code) and not verified)
        self.code_label.setText(self.mod.code)
        self.verify_btn.setVisible(not verified)
        self.verify_btn.setText("Get a new code" if self.mod.code else "Verify my channel")
        self.remove_btn.setVisible(verified)
        if not verified:
            set_badge(self.status, "\u25cf  Not set up", "pill")
        elif not self.s.get("yt_mod_on"):
            set_badge(self.status, "\u25cf  Paused", "pillWait")
        elif self.s.get("mod_dry_run"):
            set_badge(self.status, "\u25cf  Active \u2014 test mode", "pillWait")
        else:
            set_badge(self.status, "\u25cf  Active", "pillOn")
        self.used.setText("Actions used today: %d of %d" % (self.mod.used_today(), int(self.s.get("mod_budget"))))
