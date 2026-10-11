"""CHATDOOM main window. Animations only run on interaction, so idle CPU stays near zero."""
import html
import os
import sys
import time
import urllib.parse

from PySide6.QtCore import Property, QEasingCurve, QEvent, QParallelAnimationGroup, QPropertyAnimation, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPen, QPixmap, QTextBlockFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from . import hinglish
from .discord import Bridge, Cloud, LinkManager
from .discord_page import DiscordPage
from .overlay import Overlay
from .overlay_ui import OverlayPage
from .platform_events import TwitchEventSub
from .payments import TipPoller
from .payments_page import PaymentsPage
from .platform_auth import PlatformAuth
from .icons import nav_icon
from .music import MusicPlayer
from .music_page import MusicPage
from .ytmod import YtModerator
from .ytmod_page import YtModPage
from PySide6.QtCore import QSize
from .models import Message
from .moderation import Moderator
from .platforms import Hub, KickSource, TwitchSource, YouTubeSource
from .settings import Settings, data_dir
from .speech import VOICES, Speaker
from .theme import DEFAULT_THEME, FX, THEMES, build_qss
from .updater import Updater
from .version import CREATOR, PRODUCT_NAME, STAGE, VERSION, label

COLORS = {"youtube": "#ff4d4d", "twitch": "#9146ff", "kick": "#53fc18", "test": "#00d4ff", "tip": "#ffd24d"}
TAGS = {"youtube": "YT", "twitch": "TW", "kick": "KICK", "test": "TEST", "tip": "TIP"}
PAGES = ("Connect", "Live chat", "Voice", "Moderation", "Discord", "Payments", "YouTube mod", "OBS overlays", "Music")
NAV_MARK = ("◎", "☰", "♫", "⌗", "◈", "₹", "▶", "▣", "♪")
PAGE_BLURB = (
    "Connect your streaming platforms and manage live chat from one place.",
    "Messages that will be read aloud, and the ones moderation skipped.",
    "Choose and customize the voice that speaks your chat.",
    "Decide which messages are read and which are skipped.",
    "Add the bot, and viewers get roles for where they joined from.",
    "Hear paid messages and tips on stream.",
    "Add the CHATDOOM bot to your channel and keep your chat clean.",
    "Browser sources for alerts, chat and the song playing, or your StreamElements overlay.",
    "Play no-copyright music on stream, quieter while your chat is read aloud.",
)
MARKS = {"youtube": ("YT", "#ff4d4d"), "twitch": ("TW", "#9146ff"), "kick": ("KK", "#53fc18")}
CHAT_FONTS = ("Poppins", "Arial", "Segoe UI", "Calibri", "Verdana", "Tahoma", "Consolas", "Cascadia Mono", "Inter", "Roboto", "DM Sans", "Space Grotesk", "JetBrains Mono")
CHAT_WEIGHTS = (("Light", 300), ("Regular", 400), ("Medium", 500), ("Semi Bold", 600), ("Bold", 700), ("Extra Bold", 800))
CHAT_TRANSFORMS = (("Normal", "normal"), ("Uppercase", "upper"), ("Lowercase", "lower"), ("Capitalize", "caps"))
CHAT_ALIGNS = (("Left", "left"), ("Center", "center"), ("Right", "right"))


def edit_icon():
    """A small pencil, drawn here so the app does not need an icon package."""
    pix = QPixmap(16, 16)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#f4f4f8"))
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(3, 13, 12, 4)
    painter.drawLine(11, 3, 14, 6)
    painter.drawLine(2, 14, 5, 11)
    painter.end()
    return QIcon(pix)


class ChatFeed(QTextEdit):
    """Live chat text. The hint is drawn in the full box so a large font wraps instead of being clipped."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hint = ""

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.hint or not self.document().isEmpty():
            return
        painter = QPainter(self.viewport())
        painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        painter.setFont(self.font())
        margin = int(self.document().documentMargin())
        painter.drawText(self.viewport().rect().adjusted(margin, margin, -margin, -margin), Qt.TextWordWrap | Qt.AlignTop, self.hint)


class ChatStage(QWidget):
    """Chat box that keeps the text-style button and popup positioned on itself."""

    def __init__(self):
        super().__init__()
        self.feed = None
        self.trigger = None
        self.popup = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.place()

    def place(self):
        if self.feed is None:
            return
        self.feed.setGeometry(0, 0, self.width(), self.height())
        if self.trigger is not None:
            self.trigger.move(self.width() - self.trigger.width() - 10, 10)
            self.trigger.raise_()
        if self.popup is not None and self.popup.isVisible():
            self.place_popup()

    def place_popup(self):
        margin = 24
        width = min(320, max(240, self.width() - margin * 2))
        height = min(560, max(180, self.height() - margin * 2))
        self.popup.setGeometry((self.width() - width) // 2, (self.height() - height) // 2, width, height)
        self.popup.raise_()


def available_chat_fonts():
    have = set(QFontDatabase.families())
    found = [name for name in CHAT_FONTS if name in have or name == "Poppins"]
    return ["System Default"] + found


def shape_chat_text(text, mode):
    if mode == "upper":
        return (text or "").upper()
    if mode == "lower":
        return (text or "").lower()
    if mode == "caps":
        return (text or "").title()
    return text or ""
ROOT = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def esc(s):
    return html.escape(s or "")


class Switch(QCheckBox):
    """A sliding on/off control. It still saves like a checkbox."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(40, 22)
        self.setCursor(Qt.PointingHandCursor)
        self._knob = 0.0
        self._accent = QColor("#7c5cff")
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._slide)

    def knob(self):
        return self._knob

    def setKnob(self, value):
        self._knob = value
        self.update()

    knob = Property(float, knob, setKnob)

    def set_accent(self, color):
        self._accent = QColor(color)
        self.update()

    def setChecked(self, on):
        self.blockSignals(True)
        super().setChecked(on)
        self.blockSignals(False)
        self._knob = 1.0 if on else 0.0
        self.update()

    def _slide(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._accent if self.isChecked() else QColor(255, 255, 255, 36))
        painter.drawRoundedRect(0, 2, 40, 18, 9, 9)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(int(2 + self._knob * 18), 4, 14, 14)


class VoiceBoard(QWidget):
    """Places voice cards in two columns, and one column when the page is narrow."""

    def __init__(self):
        super().__init__()
        self._wide = None
        self._pairs = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(12)

    def set_cards(self, pairs, full):
        self._pairs = pairs
        self._full = full
        self._arrange(self.width() >= 760)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange(self.width() >= 760)

    def _arrange(self, wide):
        if wide == self._wide:
            return
        self._wide = wide
        while self._grid.count():
            self._grid.takeAt(0)
        if wide:
            for index, (left, right) in enumerate(self._pairs):
                self._grid.addWidget(left, index, 0)
                self._grid.addWidget(right, index, 1)
            self._grid.addWidget(self._full, len(self._pairs), 0, 1, 2)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 1)
        else:
            row = 0
            for left, right in self._pairs:
                self._grid.addWidget(left, row, 0)
                self._grid.addWidget(right, row + 1, 0)
                row += 2
            self._grid.addWidget(self._full, row, 0)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 0)


def labeled(text, widget, hint=""):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 2, 0, 2)
    lab = QLabel(text)
    lab.setMinimumWidth(190)
    lay.addWidget(lab)
    lay.addWidget(widget, 1)
    if hint:
        h = QLabel(hint)
        h.setObjectName("hint")
        lay.addWidget(h)
    return w


class PlatformCard(QFrame):
    def __init__(self, key, title, placeholder, source, settings, extra=None, hint="", field="", platform_auth=None):
        super().__init__()
        self.setObjectName("tile")
        self.key, self.source, self.s = key, source, settings
        self.platform_auth = platform_auth
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(10)
        letter, color = MARKS.get(key, ("•", "#888888"))
        mark = QLabel(letter)
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(36, 36)
        mark.setStyleSheet("background:%s; color:#0b0b10; font-weight:700; font-size:12px; border-radius:10px;" % color)
        head.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel(title)
        name.setStyleSheet("font-size:15px; font-weight:650;")
        names.addWidget(name)
        if hint:
            h = QLabel(hint)
            h.setObjectName("hint")
            h.setWordWrap(True)
            names.addWidget(h)
        head.addLayout(names, 1)
        self.status = QLabel("●  Offline")
        self.status.setObjectName("pill")
        head.addWidget(self.status, 0, Qt.AlignTop)
        lay.addLayout(head)
        cap = QLabel(field or placeholder)
        cap.setObjectName("field")
        lay.addWidget(cap)
        self.edit = QLineEdit(settings.get(key))
        self.edit.setPlaceholderText(placeholder)
        lay.addWidget(self.edit)
        self.extra = None
        if extra:
            box = QFrame()
            box.setObjectName("advanced")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 4, 0, 0)
            bl.setSpacing(4)
            lab = QLabel(extra[1])
            lab.setObjectName("hint")
            bl.addWidget(lab)
            self.extra = QLineEdit(settings.get(extra[0]))
            self.extra.setObjectName("optional")
            self.extra.setPlaceholderText("Optional")
            bl.addWidget(self.extra)
            lay.addWidget(box)
        self.btn = QPushButton("Connect")
        self.btn.setObjectName("primary")
        self.btn.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.btn, 0, Qt.AlignLeft)
        self.btn.clicked.connect(self.toggle)
        self.edit.returnPressed.connect(self.toggle)
        self.auth_label = None
        if platform_auth and key in platform_auth.SUPPORTED:
            auth_row = QHBoxLayout()
            self.auth_label = QLabel("Account not connected")
            self.auth_label.setObjectName("hint")
            auth_row.addWidget(self.auth_label, 1)
            self.auth_btn = QPushButton()
            self.auth_btn.setObjectName("quiet")
            self.auth_btn.setCursor(Qt.PointingHandCursor)
            self.auth_btn.clicked.connect(self.toggle_auth)
            auth_row.addWidget(self.auth_btn)
            lay.addLayout(auth_row)
            platform_auth.changed.connect(self._auth_changed)
            self._auth_changed(key)

    def toggle_auth(self):
        if self.platform_auth.is_connected(self.key):
            self.platform_auth.disconnect(self.key)
        else:
            self.platform_auth.login(self.key)

    def _auth_changed(self, platform):
        if platform != self.key or self.auth_label is None:
            return
        if self.platform_auth.is_connected(platform):
            self.auth_label.setText("Signed in as %s" % (self.platform_auth.display_name(platform) or "account"))
            self.auth_btn.setText("Disconnect account")
        else:
            self.auth_label.setText("Sign in for chat, polls, and platform alerts")
            self.auth_btn.setText("Login")

    def enterEvent(self, event):
        if not self.s.get("lite_mode") and self.graphicsEffect() is None:
            shade = QGraphicsDropShadowEffect(self)
            shade.setBlurRadius(28)
            shade.setOffset(0, 10)
            shade.setColor(QColor(0, 0, 0, 160))
            self.setGraphicsEffect(shade)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setGraphicsEffect(None)
        super().leaveEvent(event)

    def args(self):
        self.s.set(self.key, self.edit.text().strip())
        if self.extra is not None:
            self.s.set("kick_room", self.extra.text().strip())
            return (self.edit.text().strip(), self.extra.text().strip())
        return (self.edit.text().strip(),)

    def toggle(self):
        if self.source.running:
            self.source.stop()
            self._show("Stopping...", False)
        else:
            self.source.start(*self.args())

    def _show(self, text, ok):
        self.status.setText("●  " + text)
        if ok:
            kind = "pillOn"
        elif "..." in text:
            kind = "pillWait"
        elif text in ("Not connected", "Disconnected", "Offline"):
            kind = "pill"
            self.status.setText("●  Offline")
        else:
            kind = "pillBad"
        self.status.setObjectName(kind)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        if self.source.running and "..." in text:
            self.btn.setText("Connecting...")
            role = "primary"
        elif self.source.running:
            self.btn.setText("Disconnect")
            role = "stop"
        elif kind == "pillBad":
            self.btn.setText("Retry")
            role = "primary"
        else:
            self.btn.setText("Connect")
            role = "primary"
        self.btn.setObjectName(role)
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

    def set_status(self, text, ok):
        self._show(text, ok)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("%s (%s) \u2014 by %s" % (PRODUCT_NAME, STAGE, CREATOR))
        self.resize(1180, 760)
        self.setMinimumSize(980, 680)
        self.s = Settings()
        self.hub = Hub()
        self.speaker = Speaker(self.s)
        self.words_path = os.path.join(data_dir(), "hinglish_words.txt")
        self.blocked_path = os.path.join(data_dir(), "blocked_words.txt")
        hinglish.load_words(self.words_path)
        hinglish.on_unknown = self._unknown_word
        self.mod = Moderator(self.s, self.blocked_path)
        self.connected = set()
        self._anims = []
        self._anim_targets = []
        self.fx = FX()
        self.fx.enabled = not bool(self.s.get("lite_mode"))
        self.bridge = Bridge()
        self.platform_auth = PlatformAuth(self.s, self.bridge)
        self.twitch_events = TwitchEventSub(self.platform_auth)
        self.yt_subscriber_timer = QTimer(self)
        self.yt_subscriber_timer.setInterval(300000)
        self.yt_subscriber_timer.timeout.connect(self._poll_youtube_subscribers)
        self._subscriber_error = ""
        self.s.set("yt_subscriber_cursor", int(time.time() * 1000))
        self.cloud = Cloud(self.s)
        self.links = LinkManager(self.s, self.cloud, self.bridge, os.path.join(data_dir(), "counts.json"))
        self.discord = DiscordPage(self.s, self.cloud, self.bridge, self.links)
        self.poller = TipPoller(self.s, self.cloud, self.bridge)
        self.payments = PaymentsPage(self.s, self.cloud, self.bridge, self.poller)
        self.ytmod = YtModerator(self.s, self.bridge)
        self.ytpage = YtModPage(self.s, self.ytmod)
        self.yt_beat = QTimer(self)                       # keeps the free-hosted bot awake while you stream on YouTube
        self.yt_beat.timeout.connect(self.ytmod.refresh_info)
        self.overlay = Overlay(self.s, os.path.join(ROOT, "assets", "fonts"), self._overlay_cfg,
                               os.path.join(data_dir(), "Soundboard"))
        self.overlay.start()
        self.ovpage = OverlayPage(self.s, self.overlay)
        self.music = MusicPlayer(self.s, self.overlay.push)
        self.musicpage = MusicPage(self.s, self.music, self.overlay)
        self.updater = Updater(self.s)
        self.pending_update = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        canvas = QWidget()
        canvas.setObjectName("canvas")
        right = QVBoxLayout(canvas)
        right.setContentsMargins(28, 18, 28, 18)
        right.setSpacing(14)
        right.addWidget(self._build_topbar())
        self.banner = self._build_banner()
        right.addWidget(self.banner)
        self.stack = QStackedWidget()
        for page in (self._page_connect(), self._page_feed(), self._page_voice(), self._page_mod(), self.discord, self.payments, self.ytpage, self.ovpage, self.musicpage):
            self.stack.addWidget(page)
        right.addWidget(self.stack, 1)
        root.addWidget(canvas, 1)

        self.hub.message.connect(self.on_message)
        self.hub.status.connect(self.on_status)
        self.platform_auth.notice.connect(lambda t: self.feed.append("<span style='color:#8ab4ff'>Account: %s</span>" % esc(t)))
        self.platform_auth.changed.connect(self._platform_account_changed)
        self.platform_auth.subscribers.connect(self.on_youtube_subscribers)
        self.twitch_events.alert.connect(self.on_twitch_event)
        self.twitch_events.notice.connect(lambda t: self.feed.append("<span style='color:#9146ff'>Twitch alerts: %s</span>" % esc(t)))
        self.platform_auth.refresh("youtube")
        self.platform_auth.refresh("twitch")
        self.speaker.note.connect(lambda t: self.feed.append("<span style='color:#ffb020'>%s</span>" % esc(t)))
        self.links.notice.connect(lambda t: self.feed.append("<span style='color:#7c9cff'>Discord: %s</span>" % esc(t)))
        self.sync = QTimer(self)                      # report activity to Discord once a minute
        self.sync.timeout.connect(self.links.save)
        self.sync.start(60000)
        self.relink = QTimer(self)                    # refresh the list of linked viewers every 5 minutes
        self.relink.timeout.connect(self.links.refresh)
        self.relink.start(300000)
        QTimer.singleShot(2000, self.links.refresh)
        self.poller.tip.connect(self.on_tip)
        self.poller.notice.connect(lambda t: self.feed.append("<span style='color:#ffd24d'>%s</span>" % esc(t)))
        self.ytmod.notice.connect(lambda t: self.feed.append("<span style='color:#ff8a5c'>YouTube mod: %s</span>" % esc(t)))
        QTimer.singleShot(2500, self.poller.apply)
        self.speaker.busy_changed.connect(self.music.duck)                     # music gets quieter while a message is read aloud
        self.music.notice.connect(lambda t: self.feed.append("<span style='color:#7cf0c0'>Music: %s</span>" % esc(t)))
        QTimer.singleShot(1500, lambda: self.music.next() if self.s.get("music_autoplay") and self.music.tracks else None)
        self.updater.found.connect(self._update_found)
        self.updater.status.connect(self._update_status)
        self.updater.message.connect(lambda t: self.feed.append("<span style='color:#7cf0c0'>Update: %s</span>" % esc(t)))
        self.updater.progress.connect(self.banner_text.setText)
        self.updater.quit_now.connect(lambda: QTimer.singleShot(400, QApplication.quit))
        QTimer.singleShot(6000, self._auto_update)
        self.apply_theme(self.s.get("theme"))
        self.goto(0)

    # ---------- layout ----------
    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(228)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 16, 0, 14)
        lay.setSpacing(2)
        self.logo = QLabel()
        self.logo.setObjectName("logo")
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setContentsMargins(4, 4, 4, 8)
        logo = QPixmap(os.path.join(ROOT, "assets", "chatdoom-logo.png"))
        if not logo.isNull():
            self.logo.setPixmap(logo.scaled(196, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo.setText(PRODUCT_NAME)
        lay.addWidget(self.logo)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        groups = (("Workspace", (0, 1, 2, 8)), ("Tools", (3, 4, 5, 6, 7)))
        for title, indexes in groups:
            g = QLabel(title.upper())
            g.setObjectName("group")
            lay.addWidget(g)
            for i in indexes:
                b = QPushButton("  " + PAGES[i])
                b.setIcon(nav_icon(i))
                b.setIconSize(QSize(18, 18))
                b.setObjectName("nav")
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                self.nav.addButton(b, i)
                lay.addWidget(b)
        self.nav.idClicked.connect(self.goto)
        lay.addStretch(1)
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 8, 16, 4)
        bl.setSpacing(6)
        lab = QLabel("SETTINGS")
        lab.setObjectName("group")
        bl.addWidget(lab)
        theme = QComboBox()
        theme.addItems(list(THEMES))
        theme.setCurrentText(self.s.get("theme") if self.s.get("theme") in THEMES else DEFAULT_THEME)
        theme.currentTextChanged.connect(self.apply_theme)
        bl.addWidget(theme)
        lite = QCheckBox("Lite mode")
        lite.setToolTip("Turns off fade and hover motion. Use it on slow PCs or while gaming.")
        lite.setChecked(bool(self.s.get("lite_mode")))
        lite.toggled.connect(self._lite)
        bl.addWidget(lite)
        upd = QPushButton("Check for updates")
        upd.setCursor(Qt.PointingHandCursor)
        upd.clicked.connect(lambda: self.updater.check(True))
        bl.addWidget(upd)
        lay.addWidget(box)
        ver = QLabel(label())
        ver.setObjectName("hint")
        ver.setContentsMargins(16, 4, 12, 0)
        by = QLabel(CREATOR)
        by.setObjectName("hint")
        by.setContentsMargins(16, 0, 12, 0)
        lay.addWidget(ver)
        lay.addWidget(by)
        return side

    def _build_banner(self):
        b = QFrame()
        b.setObjectName("banner")
        lay = QHBoxLayout(b)
        lay.setContentsMargins(16, 8, 12, 8)
        self.banner_text = QLabel("")
        self.banner_text.setWordWrap(True)
        lay.addWidget(self.banner_text, 1)
        self.upd_btn = QPushButton("Update now")
        self.upd_btn.setObjectName("primary")
        self.upd_btn.clicked.connect(self._update_now)
        later = QPushButton("Later")
        later.clicked.connect(b.hide)
        lay.addWidget(self.upd_btn)
        lay.addWidget(later)
        b.hide()
        return b

    def _update_found(self, info):
        self.pending_update = info
        self.banner_text.setText("A new version is available: %s (you have %s)" % (info["version"], VERSION))
        self.upd_btn.setEnabled(True)
        self.upd_btn.show()
        self.banner.show()

    def _update_status(self, text):
        self.pending_update = None
        self.banner_text.setText(text)
        self.upd_btn.hide()
        self.banner.show()

    def _update_now(self):
        info = self.pending_update
        if not info:
            return
        if not info.get("asset"):
            self.feed.append("<span style='color:#7cf0c0'>Update: No installer file is attached to this release yet.</span>")
            return
        self.banner_text.setText("Downloading update...")
        self.upd_btn.setEnabled(False)
        self.updater.install(info)

    def _auto_update(self):
        if self.s.get("auto_update_check") and time.time() - float(self.s.get("update_last") or 0) > 20 * 3600:
            self.updater.check(False)

    def _overlay_cfg(self):
        t = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])
        sound_path = self.s.get("ov_sound_file") or ""
        sound_name = os.path.basename(sound_path)
        sound_url = ""
        sound_dir = os.path.realpath(os.path.join(data_dir(), "Soundboard"))
        if (self.s.get("ov_sound") and sound_name and os.path.isfile(sound_path) and
                os.path.dirname(os.path.realpath(sound_path)) == sound_dir):
            sound_url = "/sounds/" + urllib.parse.quote(sound_name)
        return {"colors": {"a1": t["a1"], "a2": t["a2"], "a3": t["a3"]}, "sound": bool(self.s.get("ov_sound")) and not sound_url,
                "seconds": int(self.s.get("ov_seconds")), "showMessage": bool(self.s.get("ov_show_message")),
                "chatSeconds": int(self.s.get("ov_chat_seconds")), "maxLines": 8,
                "soundUrl": sound_url,
                "alertStyle": self.s.get("ov_alert_style"), "chatStyle": self.s.get("ov_chat_style"),
                "showTips": bool(self.s.get("ov_alert_tips")),
                "showSuperchats": bool(self.s.get("ov_alert_superchats")),
                "showMemberships": bool(self.s.get("ov_alert_memberships")),
                "showSubscribers": bool(self.s.get("ov_alert_youtube_subscribers")),
                "showFollows": bool(self.s.get("ov_alert_follows")),
                "showSubscriptions": bool(self.s.get("ov_alert_subscriptions")),
                "showRaids": bool(self.s.get("ov_alert_raids"))}

    def _build_topbar(self):
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 8)
        left = QVBoxLayout()
        left.setSpacing(2)
        row = QHBoxLayout()
        self.title = QLabel("Connect")
        self.title.setObjectName("title")
        row.addWidget(self.title)
        self.live = QLabel("● LIVE")
        self.live.setObjectName("live")
        self.live_fx = QGraphicsOpacityEffect(self.live)
        self.live.setGraphicsEffect(self.live_fx)
        self.live.hide()
        self.pulse = QPropertyAnimation(self.live_fx, b"opacity", self)
        self.pulse.setDuration(1600)
        self.pulse.setKeyValueAt(0, 1.0)
        self.pulse.setKeyValueAt(0.5, 0.35)
        self.pulse.setKeyValueAt(1, 1.0)
        self.pulse.setLoopCount(-1)
        row.addWidget(self.live)
        row.addStretch(1)
        left.addLayout(row)
        self.blurb = QLabel(PAGE_BLURB[0])
        self.blurb.setObjectName("sub")
        self.blurb.setWordWrap(True)
        left.addWidget(self.blurb)
        lay.addLayout(left, 1)
        self.mute_btn = QPushButton("Mute")
        self.mute_btn.setObjectName("quiet")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setChecked(bool(self.s.get("muted")))
        self.mute_btn.setToolTip("Silence the voice and clear the queue")
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.toggled.connect(self._mute)
        skip = QPushButton("Skip")
        skip.setObjectName("quiet")
        skip.setToolTip("Skip the message being spoken")
        skip.setCursor(Qt.PointingHandCursor)
        skip.clicked.connect(self.speaker.skip)
        test = QPushButton("Test voice")
        test.setObjectName("quiet")
        test.setToolTip("Speak a short sample")
        test.setCursor(Qt.PointingHandCursor)
        test.clicked.connect(self.test_voice)
        for b in (self.mute_btn, skip, test):
            lay.addWidget(b, 0, Qt.AlignTop)
        return bar

    def _stat(self, number, caption):
        chip = QFrame()
        chip.setObjectName("stat")
        lay = QVBoxLayout(chip)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(0)
        num = QLabel(number)
        num.setObjectName("statNum")
        cap = QLabel(caption)
        cap.setObjectName("hint")
        lay.addWidget(num)
        lay.addWidget(cap)
        return chip, num

    def _sync_summary(self):
        on = len(self.connected)
        self.num_on.setText(str(on))
        self.num_off.setText(str(3 - on))

    def _page_connect(self):
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 4, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(14)
        stats = QHBoxLayout()
        stats.setSpacing(10)
        platforms, _ = self._stat("3", "Platforms")
        connected, self.num_on = self._stat("0", "Connected")
        offline, self.num_off = self._stat("3", "Offline")
        for chip in (platforms, connected, offline):
            stats.addWidget(chip, 1)
        lay.addLayout(stats)
        self.cards = {
            "youtube": PlatformCard("youtube", "YouTube Live", "Paste a live link or video ID", YouTubeSource(self.hub), self.s,
                                    hint="Chat reading reconnects automatically. Sign in to send chat/polls and show public-subscriber alerts; memberships come from live chat.",
                                    field="Stream link or video ID", platform_auth=self.platform_auth),
            "twitch": PlatformCard("twitch", "Twitch", "Channel name", TwitchSource(self.hub), self.s,
                                   hint="Reads chat anonymously. Sign in for follower, subscription, gift, and raid alerts; new alert permissions are requested.",
                                   field="Channel name",
                                   platform_auth=self.platform_auth),
            "kick": PlatformCard("kick", "Kick", "Channel name", KickSource(self.hub), self.s,
                                 extra=("kick_room", "Chatroom ID, only if the name lookup fails"),
                                 hint="Public chat by channel name.", field="Channel name"),
        }
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(self.cards["youtube"], 0, 0)
        grid.addWidget(self.cards["twitch"], 0, 1)
        grid.addWidget(self.cards["kick"], 1, 0)
        aside = QFrame()
        aside.setObjectName("aside")
        al = QVBoxLayout(aside)
        al.setContentsMargins(18, 16, 18, 16)
        title = QLabel("One voice for every chat")
        title.setStyleSheet("font-size:15px; font-weight:650;")
        body = QLabel("Connect any mix of platforms. CHATDOOM speaks the messages you allow, and keeps passwords off this page.")
        body.setObjectName("sub")
        body.setWordWrap(True)
        al.addWidget(title)
        al.addWidget(body)
        al.addStretch(1)
        grid.addWidget(aside, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def _page_feed(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)
        self.chat_box = ChatStage()
        self.feed = ChatFeed(self.chat_box)
        self.feed.setObjectName("feed")
        self.feed.setReadOnly(True)
        self.feed.document().setMaximumBlockCount(300)
        self.feed.hint = "Chat messages appear here. Grey lines were skipped by moderation."
        self.feed.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.feed.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.feed.document().setDocumentMargin(12)
        self.feed.setViewportMargins(0, 42, 0, 0)
        self.chat_style_btn = QPushButton(self.chat_box)
        self.chat_style_btn.setObjectName("chatStyle")
        self.chat_style_btn.setIcon(edit_icon())
        self.chat_style_btn.setIconSize(QSize(16, 16))
        self.chat_style_btn.setCursor(Qt.PointingHandCursor)
        self.chat_style_btn.setFixedSize(32, 30)
        self.chat_style_btn.setToolTip("Text style")
        self.chat_style_btn.setAccessibleName("Text style")
        self.chat_style_btn.setCheckable(True)
        self.chat_style_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);"
            " border-radius: 8px; padding: 0; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.22); }"
            "QPushButton:focus { border: 1px solid rgba(255,255,255,0.55); }"
            "QPushButton:checked { background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.40); }")
        self.chat_style_btn.clicked.connect(self._toggle_chat_style)
        self.chat_box.feed = self.feed
        self.chat_box.trigger = self.chat_style_btn
        self.chat_popup = self._chat_style_popup()
        self.chat_box.popup = self.chat_popup
        self.chat_popup.hide()
        lay.addWidget(self.chat_box, 1)
        controls = QFrame()
        controls.setObjectName("tile")
        row = QHBoxLayout(controls)
        row.setContentsMargins(12, 8, 12, 8)
        self.action_platform = QComboBox()
        self.action_platform.addItem("YouTube", "youtube")
        self.action_platform.addItem("Twitch", "twitch")
        self.action_platform.currentIndexChanged.connect(self._action_platform_changed)
        self.message_edit = QLineEdit()
        self.message_edit.setPlaceholderText("Sign in, then type a chat message...")
        self.message_edit.returnPressed.connect(self._send_chat_message)
        self.send_chat_btn = QPushButton("Send")
        self.send_chat_btn.setObjectName("primary")
        self.send_chat_btn.clicked.connect(self._send_chat_message)
        self.poll_btn = QPushButton("Create poll")
        self.poll_btn.setObjectName("quiet")
        self.poll_btn.clicked.connect(self._create_chat_poll)
        row.addWidget(self.action_platform)
        row.addWidget(self.message_edit, 1)
        row.addWidget(self.send_chat_btn)
        row.addWidget(self.poll_btn)
        lay.addWidget(controls)
        self._action_platform_changed()
        QApplication.instance().installEventFilter(self)
        self._apply_chat_style()
        return page

    def _action_platform_changed(self, *_):
        if not hasattr(self, "action_platform"):
            return
        platform = self.action_platform.currentData()
        if platform == "youtube":
            self.message_edit.setMaxLength(200)
        else:
            self.message_edit.setMaxLength(500)

    def _platform_account_changed(self, platform):
        if not hasattr(self, "action_platform") or platform not in ("youtube", "twitch"):
            return
        index = self.action_platform.findData(platform)
        if index < 0:
            return
        name = self.platform_auth.display_name(platform)
        label = platform.title() + ((" — " + name) if self.platform_auth.is_connected(platform) and name
                                    else (" — signed in" if self.platform_auth.is_connected(platform) else " — sign-in needed"))
        self.action_platform.setItemText(index, label)
        if platform == "twitch":
            if self.platform_auth.is_connected(platform):
                self.twitch_events.start()
            else:
                self.twitch_events.stop()
        elif platform == "youtube":
            if self.platform_auth.is_connected(platform):
                if not self.yt_subscriber_timer.isActive():
                    self.yt_subscriber_timer.start()
                    self._poll_youtube_subscribers()
            else:
                self.yt_subscriber_timer.stop()

    def _poll_youtube_subscribers(self):
        if not self.s.get("ov_alert_youtube_subscribers"):
            self.s.set("yt_subscriber_cursor", int(time.time() * 1000))
            return
        if self.platform_auth.is_connected("youtube"):
            self.platform_auth.poll_youtube_subscribers(int(self.s.get("yt_subscriber_cursor") or 0))

    def on_youtube_subscribers(self, result):
        if result.get("error"):
            if result["error"] != self._subscriber_error:
                self._subscriber_error = result["error"]
                self.feed.append("<span style='color:#ff8a5c'>YouTube subscriber alerts: %s</span>" % esc(result["error"]))
            return
        self._subscriber_error = ""
        saved_seen = self.s.get("yt_subscriber_seen")
        seen = list(saved_seen) if isinstance(saved_seen, list) else []
        seen_ids = set(seen)
        for subscriber in result.get("subscribers") or []:
            uid = subscriber.get("id")
            if not uid or uid in seen_ids:
                continue
            seen_ids.add(uid)
            seen.append(uid)
            if self.s.get("ov_alert_youtube_subscribers"):
                self.overlay.push("alert", {
                    "platform": "youtube",
                    "category": "subscriber",
                    "name": subscriber.get("name") or "Someone",
                    "message": "",
                })
        self.s.set("yt_subscriber_seen", seen[-500:])
        self.s.set("yt_subscriber_cursor", int(result.get("cursor") or self.s.get("yt_subscriber_cursor") or 0))

    def on_twitch_event(self, alert):
        self.overlay.push("alert", alert)
        self.feed.append("<span style='color:#9146ff'>Twitch alert: %s %s</span>" %
                         (esc(alert.get("name") or "Someone"), esc(alert.get("category") or "event")))

    def _send_chat_message(self):
        self.platform_auth.send_message(self.action_platform.currentData(), self.message_edit.text())

    def _create_chat_poll(self):
        platform = self.action_platform.currentData()
        dialog = QDialog(self)
        dialog.setWindowTitle("Create %s poll" % platform.title())
        layout = QVBoxLayout(dialog)
        question = QLineEdit()
        question.setMaxLength(60 if platform == "twitch" else 100)
        question.setPlaceholderText("Poll question")
        layout.addWidget(question)
        options = []
        max_options = 5 if platform == "twitch" else 4
        for index in range(max_options):
            option = QLineEdit()
            option.setMaxLength(25 if platform == "twitch" else 50)
            option.setPlaceholderText("Option %d%s" % (index + 1, " (required)" if index < 2 else " (optional)"))
            options.append(option)
            layout.addWidget(option)
        duration = QSpinBox()
        duration.setRange(15, 180)
        duration.setSuffix(" seconds")
        duration.setValue(60)
        if platform == "twitch":
            layout.addWidget(duration)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.platform_auth.create_poll(platform, question.text(), [item.text() for item in options],
                                           duration.value() if platform == "twitch" else 60)

    def _set_chat_style_open(self, open_):
        self.chat_style_btn.setChecked(open_)
        if open_:
            self.chat_box.place_popup()
            self.chat_popup.show()
        else:
            self.chat_popup.hide()

    def _toggle_chat_style(self):
        self._set_chat_style_open(not self.chat_popup.isVisible())

    def _style_popup_hit(self, widget):
        if widget is None:
            return False
        if widget is self.chat_style_btn or widget is self.chat_popup or self.chat_popup.isAncestorOf(widget):
            return True
        active = QApplication.activePopupWidget()
        return active is not None and (widget is active or active.isAncestorOf(widget))

    def eventFilter(self, obj, event):
        popup = getattr(self, "chat_popup", None)
        if event.type() == QEvent.Wheel and isinstance(obj, (QSlider, QComboBox)) and QApplication.activePopupWidget() is None:
            voice = getattr(self, "voice_scroll", None)
            if popup is not None and popup.isAncestorOf(obj):
                bar = self.chat_style_scroll.verticalScrollBar()
                bar.setValue(bar.value() - event.angleDelta().y())
                return True
            if voice is not None and voice.isAncestorOf(obj):
                bar = voice.verticalScrollBar()
                bar.setValue(bar.value() - event.angleDelta().y())
                return True
        if popup is not None and popup.isVisible():
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self._set_chat_style_open(False)
                return True
            if event.type() == QEvent.MouseButtonPress and not self._style_popup_hit(QApplication.widgetAt(event.globalPosition().toPoint())):
                self._set_chat_style_open(False)
        return super().eventFilter(obj, event)

    def _chat_style_popup(self):
        popup = QFrame(self.chat_box)
        popup.setObjectName("chatPop")
        popup.setStyleSheet("QFrame#chatPop { background: rgba(14,16,24,0.96); border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; }")
        shadow = QGraphicsDropShadowEffect(popup)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 160))
        popup.setGraphicsEffect(shadow)
        lay = QVBoxLayout(popup)
        lay.setContentsMargins(8, 8, 8, 8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._chat_style_panel())
        self.chat_style_scroll = scroll
        lay.addWidget(scroll)
        return popup

    def _chat_style_panel(self):
        panel = QFrame()
        panel.setObjectName("tile")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(6)
        title = QLabel("Text Style")
        title.setStyleSheet("font-size:14px; font-weight:650;")
        outer.addWidget(title)
        note = QLabel("Live chat messages only")
        note.setObjectName("hint")
        outer.addWidget(note)
        self.chat_font = QComboBox()
        for name in available_chat_fonts():
            self.chat_font.addItem(name, "" if name == "System Default" else name)
        self.chat_font.setCurrentIndex(max(0, self.chat_font.findData(self.s.get("chat_font") or "")))
        self.chat_font.currentIndexChanged.connect(lambda _: self._save_chat("chat_font", self.chat_font.currentData()))
        outer.addWidget(self._style_label("Font"))
        outer.addWidget(self.chat_font)
        self.chat_size, size_row = self._style_slider("chat_size", 10, 32, lambda v: "%d px" % v)
        outer.addWidget(self._style_label("Size"))
        outer.addLayout(size_row)
        self.chat_weight = QComboBox()
        for name, value in CHAT_WEIGHTS:
            self.chat_weight.addItem(name, value)
        self.chat_weight.setCurrentIndex(max(0, self.chat_weight.findData(int(self.s.get("chat_weight") or 400))))
        self.chat_weight.currentIndexChanged.connect(lambda _: self._save_chat("chat_weight", int(self.chat_weight.currentData())))
        outer.addWidget(self._style_label("Weight"))
        outer.addWidget(self.chat_weight)
        color_row = QHBoxLayout()
        self.chat_color_btn = QPushButton()
        self.chat_color_btn.setObjectName("quiet")
        self.chat_color_btn.setCursor(Qt.PointingHandCursor)
        self.chat_color_btn.clicked.connect(self._pick_chat_color)
        color_row.addWidget(self.chat_color_btn, 1)
        outer.addWidget(self._style_label("Color"))
        outer.addLayout(color_row)
        self.chat_line, line_row = self._style_slider("chat_line", 10, 20, lambda v: "%.1f" % (v / 10))
        outer.addWidget(self._style_label("Line height"))
        outer.addLayout(line_row)
        self.chat_track, track_row = self._style_slider("chat_track", -1, 4, lambda v: "%d px" % v)
        outer.addWidget(self._style_label("Letter spacing"))
        outer.addLayout(track_row)
        self.chat_opacity, fade_row = self._style_slider("chat_opacity", 0, 100, lambda v: "%d%%" % v)
        outer.addWidget(self._style_label("Opacity"))
        outer.addLayout(fade_row)
        self.chat_transform = QComboBox()
        for name, value in CHAT_TRANSFORMS:
            self.chat_transform.addItem(name, value)
        self.chat_transform.setCurrentIndex(max(0, self.chat_transform.findData(self.s.get("chat_transform") or "normal")))
        self.chat_transform.currentIndexChanged.connect(lambda _: self._save_chat("chat_transform", self.chat_transform.currentData()))
        outer.addWidget(self._style_label("Transform"))
        outer.addWidget(self.chat_transform)
        self.chat_style = QComboBox()
        self.chat_style.addItem("Normal", False)
        self.chat_style.addItem("Italic", True)
        self.chat_style.setCurrentIndex(1 if self.s.get("chat_italic") else 0)
        self.chat_style.currentIndexChanged.connect(lambda _: self._save_chat("chat_italic", bool(self.chat_style.currentData())))
        outer.addWidget(self._style_label("Style"))
        outer.addWidget(self.chat_style)
        self.chat_align = QComboBox()
        for name, value in CHAT_ALIGNS:
            self.chat_align.addItem(name, value)
        self.chat_align.setCurrentIndex(max(0, self.chat_align.findData(self.s.get("chat_align") or "left")))
        self.chat_align.currentIndexChanged.connect(lambda _: self._save_chat("chat_align", self.chat_align.currentData()))
        outer.addWidget(self._style_label("Alignment"))
        outer.addWidget(self.chat_align)
        outer.addWidget(self._style_label("Preview"))
        self.chat_preview = QLabel("Samir: Hello everyone!\nAlex: Welcome to the stream!")
        self.chat_preview.setWordWrap(True)
        self.chat_preview.setMinimumHeight(64)
        outer.addWidget(self.chat_preview)
        reset = QPushButton("Reset to default")
        reset.setObjectName("quiet")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self._reset_chat_style)
        outer.addWidget(reset)
        return panel

    def _style_label(self, text):
        lab = QLabel(text)
        lab.setObjectName("field")
        return lab

    def _style_slider(self, key, lo, hi, fmt):
        row = QHBoxLayout()
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(int(self.s.get(key)))
        value = QLabel(fmt(sl.value()))
        value.setObjectName("hint")
        value.setMinimumWidth(42)
        sl.valueChanged.connect(lambda v, k=key, f=fmt, lab=value: (lab.setText(f(v)), self._save_chat(k, int(v))))
        row.addWidget(sl, 1)
        row.addWidget(value)
        return sl, row

    def _save_chat(self, key, value):
        self.s.set(key, value)
        self._apply_chat_style()

    def _pick_chat_color(self):
        current = QColor(self.s.get("chat_color") or "#f4f4f8")
        chosen = QColorDialog.getColor(current, self, "Live chat text color")
        if chosen.isValid():
            self._save_chat("chat_color", chosen.name())

    def _reset_chat_style(self):
        from .settings import DEFAULTS
        for key in ("chat_font", "chat_size", "chat_weight", "chat_color", "chat_line", "chat_track", "chat_opacity", "chat_transform", "chat_italic", "chat_align"):
            self.s.set(key, DEFAULTS[key])
        self.chat_font.setCurrentIndex(max(0, self.chat_font.findData("")))
        self.chat_size.setValue(int(DEFAULTS["chat_size"]))
        self.chat_weight.setCurrentIndex(max(0, self.chat_weight.findData(400)))
        self.chat_line.setValue(int(DEFAULTS["chat_line"]))
        self.chat_track.setValue(int(DEFAULTS["chat_track"]))
        self.chat_opacity.setValue(int(DEFAULTS["chat_opacity"]))
        self.chat_transform.setCurrentIndex(0)
        self.chat_style.setCurrentIndex(0)
        self.chat_align.setCurrentIndex(0)
        self._apply_chat_style()

    def _apply_chat_style(self):
        family = self.s.get("chat_font") or "Poppins"
        size = int(self.s.get("chat_size") or 13)
        weight = int(self.s.get("chat_weight") or 400)
        italic = bool(self.s.get("chat_italic"))
        track = int(self.s.get("chat_track") or 0)
        color = QColor(self.s.get("chat_color") or "#f4f4f8")
        color.setAlphaF(max(0, min(100, int(self.s.get("chat_opacity") or 100))) / 100)
        align = {"center": Qt.AlignCenter, "right": Qt.AlignRight}.get(self.s.get("chat_align"), Qt.AlignLeft)
        font = QFont(family if family != "System Default" else "Poppins")
        if not self.s.get("chat_font"):
            font = QFont("Poppins")
        font.setPixelSize(size)
        font.setWeight(QFont.Weight(weight) if weight in (100, 200, 300, 400, 500, 600, 700, 800, 900) else QFont.Weight.Normal)
        font.setItalic(italic)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, track)
        css = "QTextEdit#feed { color: %s; font-family: \"%s\"; font-size: %dpx; font-weight: %d; font-style: %s; background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 0; }" % (
            color.name(QColor.NameFormat.HexArgb), font.family(), size, weight, "italic" if italic else "normal")
        self.feed.setFont(font)
        self.feed.setStyleSheet(css)
        self.feed.setAlignment(align)
        block = QTextBlockFormat()
        block.setLineHeight(float(int(self.s.get("chat_line") or 10) * 10), 1)
        block.setAlignment(align)
        cursor = QTextCursor(self.feed.document())
        cursor.beginEditBlock()
        block_cursor = self.feed.document().firstBlock()
        while block_cursor.isValid():
            cursor.setPosition(block_cursor.position())
            cursor.setBlockFormat(block)
            block_cursor = block_cursor.next()
        cursor.endEditBlock()
        if hasattr(self, "chat_preview"):
            self.chat_preview.setFont(font)
            self.chat_preview.setAlignment(align)
            self.chat_preview.setStyleSheet("color: %s; background: rgba(0,0,0,0.28); border-radius: 10px; padding: 8px;" % color.name(QColor.NameFormat.HexArgb))
            sample = shape_chat_text("Samir: Hello everyone!", self.s.get("chat_transform")) + "\n" + shape_chat_text("Alex: Welcome to the stream!", self.s.get("chat_transform"))
            self.chat_preview.setText(sample)
        if hasattr(self, "chat_color_btn"):
            self.chat_color_btn.setText(self.s.get("chat_color") or "#f4f4f8")
            self.chat_color_btn.setStyleSheet("QPushButton { color: %s; }" % (self.s.get("chat_color") or "#f4f4f8"))

    def _bind_check(self, text, key):
        cb = QCheckBox(text)
        cb.setChecked(bool(self.s.get(key)))
        cb.toggled.connect(lambda v: self.s.set(key, v))
        return cb

    def _bind_slider(self, key, lo, hi):
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(int(self.s.get(key)))
        sl.valueChanged.connect(lambda v: self.s.set(key, v))
        return sl

    def _bind_spin(self, key, lo, hi, suffix=""):
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setSuffix(suffix)
        sp.setValue(int(self.s.get(key)))
        sp.valueChanged.connect(lambda v: self.s.set(key, v))
        return sp

    def _voice_combo(self, key):
        cb = QComboBox()
        for name, vid in VOICES:
            cb.addItem(name, vid)
        cb.setCurrentIndex(max(0, cb.findData(self.s.get(key))))
        cb.currentIndexChanged.connect(lambda _: self.s.set(key, cb.currentData()))
        return cb

    def _voice_section(self, title, detail):
        card = QFrame()
        card.setObjectName("tile")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)
        head = QLabel(title)
        head.setObjectName("voiceTitle")
        note = QLabel(detail)
        note.setObjectName("voiceNote")
        note.setWordWrap(True)
        lay.addWidget(head)
        lay.addWidget(note)
        return card, lay

    def _voice_field(self, title, detail, widget):
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(2)
        name = QLabel(title)
        name.setObjectName("voiceName")
        note = QLabel(detail)
        note.setObjectName("voiceNote")
        note.setWordWrap(True)
        if widget.maximumWidth() > 1000:
            widget.setMaximumWidth(420)
        lay.addWidget(name)
        lay.addWidget(note)
        lay.addWidget(widget)
        return wrap

    def _voice_switch(self, title, detail, key):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 6, 0, 6)
        text = QVBoxLayout()
        text.setSpacing(1)
        name = QLabel(title)
        name.setObjectName("voiceName")
        name.setWordWrap(True)
        note = QLabel(detail)
        note.setObjectName("voiceNote")
        note.setWordWrap(True)
        text.addWidget(name)
        text.addWidget(note)
        switch = Switch()
        switch.set_accent(THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"])
        switch.setChecked(bool(self.s.get(key)))
        switch.toggled.connect(lambda on, k=key: self.s.set(k, on))
        lay.addLayout(text, 1)
        lay.addWidget(switch, 0, Qt.AlignTop)
        return row

    def _voice_meter(self, title, detail, key, lo, hi, fmt):
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 6, 0, 2)
        lay.setSpacing(4)
        top = QHBoxLayout()
        name = QLabel(title)
        name.setObjectName("voiceName")
        value = QLabel()
        value.setObjectName("voiceValue")
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(value)
        note = QLabel(detail)
        note.setObjectName("voiceNote")
        note.setWordWrap(True)
        slider = self._bind_slider(key, lo, hi)
        value.setText(fmt(slider.value()))
        slider.valueChanged.connect(lambda v, f=fmt, lab=value: lab.setText(f(v)))
        lay.addLayout(top)
        lay.addWidget(note)
        lay.addWidget(slider)
        return wrap

    def _page_voice(self):
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 8, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.voice_scroll = scroll
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(12)

        engine, engine_lay = self._voice_section("Voice engine", "Choose the speech engine used to read your chat.")
        eng = QComboBox()
        eng.addItem("Neural voices (online, best quality)", "neural")
        eng.addItem("Windows voices (offline)", "windows")
        eng.setCurrentIndex(max(0, eng.findData(self.s.get("engine"))))
        eng.currentIndexChanged.connect(lambda _: self.s.set("engine", eng.currentData()))
        engine_lay.addWidget(self._voice_field("Voice engine", "Neural voices need the internet. Windows voices work offline.", eng))
        lay.addWidget(engine)

        languages, lang_lay = self._voice_section("Language voices", "Pick who speaks each kind of message.")
        lang_lay.addWidget(self._voice_field("Hindi", "Choose the voice for Devanagari messages.", self._voice_combo("hi_voice")))
        lang_lay.addWidget(self._voice_field("Hinglish / English", "Choose the voice for Latin-script messages.", self._voice_combo("en_voice")))

        options, opt_lay = self._voice_section("Voice options", "Small choices for how messages are spoken.")
        read_mode = QComboBox()
        read_mode.addItem("Read every allowed chat message", "all")
        read_mode.addItem("Read paid messages only", "paid")
        read_mode.setCurrentIndex(max(0, read_mode.findData(self.s.get("read_mode") or "all")))
        read_mode.currentIndexChanged.connect(lambda _: self.s.set("read_mode", read_mode.currentData()))
        opt_lay.addWidget(self._voice_field(
            "Chat reading mode", "Paid-only mode skips regular chat but still reads enabled Super Chats, Bits, memberships, and tips.",
            read_mode))
        opt_lay.addWidget(self._voice_switch("Different voice for each viewer", "Use a different voice when possible for each viewer.", "per_viewer"))
        opt_lay.addWidget(self._voice_switch("Say the viewer's name first", "Speak the viewer's name before reading their message.", "read_name"))
        opt_lay.addWidget(self._voice_switch("Read paid messages", "Allow Super Chats, Bits, memberships, and tips to be read.", "read_super"))
        opt_lay.addWidget(self._voice_switch(
            "Translate chat into English", "Detect and translate non-English messages through Cloudflare AI before speaking. Requires your Discord cloud connection; usage is shared and limited.",
            "translate_chat"))

        playback, play_lay = self._voice_section("Playback", "How fast and how loud the voice sounds.")
        play_lay.addWidget(self._voice_meter("Speed", "Controls how quickly messages are spoken.", "rate", -5, 5, lambda v: "%.1f×" % (1 + v * 0.1)))
        play_lay.addWidget(self._voice_meter("Volume", "Controls the voice output level.", "volume", 0, 100, lambda v: "%d%%" % v))

        queue, queue_lay = self._voice_section("Message queue", "Controls how many chat messages can wait to be spoken.")
        spin = self._bind_spin("queue_max", 1, 20)
        spin.setMaximumWidth(88)
        queue_lay.addWidget(self._voice_field("Maximum messages in queue", "Older messages are removed when chat becomes too fast.", spin))

        words, word_lay = self._voice_section("Word list", "Manage words and pronunciation used when reading Hinglish chat.")
        buttons = QHBoxLayout()
        edit = QPushButton("Edit word list")
        edit.setObjectName("primary")
        edit.setCursor(Qt.PointingHandCursor)
        edit.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.words_path)))
        reload_words = QPushButton("Reload word list")
        reload_words.setObjectName("quiet")
        reload_words.setCursor(Qt.PointingHandCursor)
        reload_words.clicked.connect(lambda: self.feed.append("<span style='color:#8a93a8'>Loaded %d short-form words</span>"
                                                               % hinglish.load_words(self.words_path)))
        buttons.addWidget(edit)
        buttons.addWidget(reload_words)
        buttons.addStretch(1)
        word_lay.addLayout(buttons)

        board = VoiceBoard()
        board.set_cards([(languages, options), (playback, queue)], words)
        lay.addWidget(board)
        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def _page_mod(self):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        note = QLabel("These filters decide what gets read aloud. Skipped messages stay visible in grey on the Live chat page.")
        note.setObjectName("sub")
        note.setWordWrap(True)
        lay.addWidget(note)
        for text, key in (("Skip messages with links", "skip_links"), ("Skip !commands", "skip_cmds"),
                          ("Ignore known bots (Nightbot, StreamElements, ...)", "ignore_bots"),
                          ("Only read moderators and the streamer", "mods_only")):
            lay.addWidget(self._bind_check(text, key))
        lay.addWidget(labeled("Max message length", self._bind_spin("max_len", 20, 500, " chars")))
        lay.addWidget(labeled("Ignore repeats for", self._bind_spin("dedupe_secs", 0, 120, " s")))
        lay.addWidget(labeled("Same viewer cooldown", self._bind_spin("user_cooldown", 0, 60, " s")))
        lay.addWidget(QLabel("Blocked words (one per line, never read aloud, also blocks paid messages)"))
        self.blocked_edit = QPlainTextEdit()
        try:
            with open(self.blocked_path, encoding="utf-8") as f:
                self.blocked_edit.setPlainText(f.read())
        except Exception:
            pass
        lay.addWidget(self.blocked_edit, 1)
        save = QPushButton("Save blocked words")
        save.setObjectName("primary")
        save.clicked.connect(self._save_blocked)
        lay.addWidget(save, 0, Qt.AlignLeft)
        return page

    # ---------- behaviour ----------
    def apply_theme(self, name):
        if name not in THEMES:
            name = DEFAULT_THEME
        t = THEMES[name]
        self.s.set("theme", name)
        self.setStyleSheet(build_qss(name))
        self.fx.recolor(t["a1"])
        for switch in self.findChildren(Switch):
            switch.set_accent(t["a1"])

    def _lite(self, on):
        self.s.set("lite_mode", on)
        self.fx.set_enabled(not on)
        if on:
            self.pulse.stop()
            self.live_fx.setOpacity(1.0)
        elif self.connected:
            self.pulse.start()

    def _end_anim(self):
        for g in self._anims:
            g.stop()
        for w in self._anim_targets:
            w.setGraphicsEffect(None)
        self._anims, self._anim_targets = [], []

    def goto(self, i):
        self._end_anim()
        self.nav.button(i).setChecked(True)
        self.title.setText(PAGES[i])
        self.blurb.setText(PAGE_BLURB[i])
        page = self.stack.widget(i)
        self.stack.setCurrentIndex(i)
        if self.s.get("lite_mode"):
            return
        group = QParallelAnimationGroup(self)
        targets = [page]
        fx = QGraphicsOpacityEffect(page)
        fx.setOpacity(0.0)
        page.setGraphicsEffect(fx)
        a = QPropertyAnimation(fx, b"opacity")
        a.setDuration(160)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(a)
        group.finished.connect(self._end_anim)
        self._anims, self._anim_targets = [group], targets
        group.start()

    def _mute(self, v):
        self.s.set("muted", v)
        if v:
            self.speaker.clear()

    def _save_blocked(self):
        try:
            with open(self.blocked_path, "w", encoding="utf-8") as f:
                f.write(self.blocked_edit.toPlainText())
            self.mod.reload_blocked()
            self.feed.append("<span style='color:#8a93a8'>Blocked words saved (%d)</span>" % len(self.mod.blocked))
        except Exception as e:
            self.feed.append("<span style='color:#ff5470'>Could not save: %s</span>" % esc(str(e)))

    def _unknown_word(self, w):
        self.feed.append("<span style='color:#8a93a8'>new short word '%s' - add it in Voice > Edit word list</span>" % esc(w))

    def on_status(self, platform, text, ok):
        card = self.cards.get(platform)
        if card:
            card.set_status(text, ok)
        (self.connected.add if ok else self.connected.discard)(platform)
        self._sync_summary()
        if ok:
            self.discord.auto_announce(platform, card.edit.text().strip() if platform == "youtube" else None)
        if platform == "youtube":
            if ok and self.ytmod.verified:
                self.ytmod.refresh_info()
                self.yt_beat.start(8 * 60 * 1000)
            elif not ok:
                self.yt_beat.stop()
        if self.connected and self.live.isHidden():
            self.live.show()
            self.pulse.start()
        elif not self.connected and not self.live.isHidden():
            self.pulse.stop()
            self.live.hide()

    def on_message(self, m):
        is_link = self.links.handle(m)
        ok, reason = self.mod.check(m)
        if is_link:
            ok, reason = False, "link code (processing)"
        elif not ok and m.platform == "youtube" and not m.mod:
            self.ytmod.flag(m, reason)
        color = COLORS.get(m.platform, "#8a93a8")
        amt = " <span style='color:#ffd24d'>[%s]</span>" % esc(m.amount) if m.amount else ""
        tag = "<span style='color:%s'><b>%s</b></span>" % (color, TAGS.get(m.platform, "?"))
        if ok:
            author = shape_chat_text(m.author, self.s.get("chat_transform"))
            text = shape_chat_text(m.text, self.s.get("chat_transform"))
            self.feed.append("%s <b>%s</b>%s: %s" % (tag, esc(author), amt, esc(text)))
            self.speaker.say(m.author, m.text, m.amount if m.kind == "super" else "")
            if m.platform != "tip":
                self.overlay.push("chat", {"platform": m.platform, "name": m.author, "text": m.text})
            if m.kind in ("super", "member"):
                category = "membership" if m.kind == "member" else ("tip" if m.platform == "tip" else "superchat")
                self.overlay.push("alert", {"platform": m.platform, "category": category,
                                            "name": m.author, "amount": m.amount, "message": m.text})
            if m.kind == "super":
                self.discord.post_paid(m)
        else:
            author = shape_chat_text(m.author, self.s.get("chat_transform"))
            text = shape_chat_text(m.text, self.s.get("chat_transform"))
            self.feed.append("<span style='color:#5d667d'>%s %s: %s <i>(skipped: %s)</i></span>"
                             % (TAGS.get(m.platform, "?"), esc(author), esc(text), reason))

    def on_tip(self, ev):
        msg, note = (ev.get("message") or "").strip(), ""
        if msg and self.mod._blocked_hit(msg):
            msg, note = "", "message hidden: blocked word"
        elif msg and ev.get("currency") == "INR" and float(ev.get("value") or 0) < int(self.s.get("tip_min")):
            msg, note = "", "message not read: below the minimum amount"
        self.on_message(Message("tip", ev.get("name") or "Someone", msg, "super", ev.get("display", ""),
                               event_id=str(ev.get("id") or "")))
        if note:
            self.feed.append("<span style='color:#5d667d'>%s</span>" % esc(note))

    def test_voice(self):
        for m in (Message("test", "Test", "bhai kya krra hoga, nhi pta yr, bht mast stream h lol"),
                  Message("test", "Test", "नमस्ते दोस्तों, चैट रीडर चालू है।")):
            self.on_message(m)
        self.goto(1)

    def closeEvent(self, e):
        self.links.save()
        self.music.stop()
        self.twitch_events.stop()
        self.yt_subscriber_timer.stop()
        self.overlay.stop()
        for c in self.cards.values():
            c.source.stop()
        self.speaker.clear()
        super().closeEvent(e)
