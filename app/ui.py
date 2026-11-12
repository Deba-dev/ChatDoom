"""CHATDOOM main window. Animations only run on interaction, so idle CPU stays near zero."""
import html
import os
import sys
import time
import urllib.parse
from dataclasses import replace

from PySide6.QtCore import Property, QEasingCurve, QEvent, QParallelAnimationGroup, QPoint, QPropertyAnimation, QSize, Qt, QTimer, QUrl, QVariantAnimation
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPen, QPixmap, QTextBlockFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (QMenu, QMessageBox, QSystemTrayIcon, QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QMenu,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from . import alert_sounds, alert_styles, hinglish, logs, overlay_styles, system
from .chat_actions import ALL_CHATS, ChatActions, compact
from .chat_feed import ChatFeed
from .commands import PLATFORM_NAMES, Commands
from .commands_page import CommandsPage
from .discord import Bridge, Cloud, LinkManager, post_webhook, run_bg
from .discord_page import DiscordPage
from .overlay import Overlay
from .overlay_ui import OverlayPage
from .platform_events import TwitchEventSub
from .payments import TipPoller
from .payments_page import PaymentsPage
from .platform_auth import PlatformAuth
from .hotkeys import Hotkeys
from .icons import PLATFORM_COLORS, nav_icon, platform_glyph, platform_tile, utility_icon
from .music import MusicPlayer
from .music_page import MusicPage
from .ytmod import YtModerator
from .ytmod_page import YtModPage
from PySide6.QtCore import QSize
from .models import Message, viewer_key
from .moderation import BLOCKED_NAME, SHOW_ONLY, Moderator, looks_like_bot, spoken_text
from .raidguard import WINDOW as RAID_WINDOW, RaidGuard
from .platforms import SOURCES, Hub, KickSource, TwitchSource, YouTubeSource, youtube_id
from .settings import Settings, data_dir
from .speech import Speaker
from .stream_watch import FORMATS, StreamWatch, stream_format
from .appearance import AppearanceDialog
from .theme import CUSTOM_THEME, DEFAULT_THEME, FX, THEMES, build_qss, set_custom_theme
from .tools import NO_REWARDS, Tools
from .alerts_page import AlertsPage
from .overlay_design_page import OverlayDesignPage
from .settings_page import SettingsPage
from .tools_page import ToolsPage
from .ui_kit import SubPage, platform_mark, section_card
from .voice_ui import fill_voice_page
from .visuals import BACKGROUNDS, Backdrop, CardGlow, HeroCard, Motion, NavIndicator, StatCard, Toasts, count_to, stagger_in
from .updater import Updater
from .version import PRODUCT_NAME, VERSION, label

CHAT_LOG = logs.get("chat")
from .window_modes import WindowModes

COLORS = {"youtube": "#ff4d4d", "twitch": "#9146ff", "kick": "#53fc18", "test": "#00d4ff", "tip": "#ffd24d"}
TAGS = {"youtube": "YT", "twitch": "TW", "kick": "KICK", "test": "TEST", "tip": "TIP"}
PAGES = ("Connect", "Live chat", "Voice", "Moderation", "Discord", "Payments", "YouTube mod", "OBS overlays", "Music", "Commands", "Stream tools",
         "Alerts", "Loyalty", "Engage", "Overlay styles", "Settings")
NAV_MARK = ("◎", "☰", "♫", "⌗", "◈", "₹", "▶", "▣", "♪", "!", "≡", "◉", "$", "?", "◧", "⚙")
STREAM_END_GRACE = 180000          # ms with no stream connected before the stream counts as over (reconnects are not an end)
MAX_EXTRA_STREAMS = 8
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
    "Your own !commands, and memes viewers play from chat.",
    "Timers, welcomes, song requests, paid read-aloud, hotkeys and your stream summary.",
    "How every alert looks, moves and sounds on stream, with a live preview.",
    "Points, levels and a shop that keep viewers coming back.",
    "Polls, predictions, giveaways, the viewer queue, counters and goals.",
    "Style packs, skins, animations and fonts for chat, now playing, memes and widgets.",
    "How CHATDOOM looks, starts, behaves and updates, plus backups.",
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


def stream_label(b):
    """One menu line for a live or scheduled YouTube stream."""
    if b.get("live"):
        when = "LIVE"
    elif b.get("start"):
        when = time.strftime("%d %b %H:%M", time.localtime(b["start"] / 1000))
    else:
        when = "Not scheduled"
    privacy = " (%s)" % b["privacy"] if b.get("privacy") in ("unlisted", "private") else ""
    return "%s: %s%s" % (when, b.get("title") or "Untitled stream", privacy)


class PlatformCard(QFrame):
    def __init__(self, key, title, placeholder, source, settings, extra=None, hint="", field="", platform_auth=None):
        super().__init__()
        self.setObjectName("tile")
        self.key, self.source, self.s = key, source, settings
        self.platform_auth = platform_auth
        self.detected = None
        self.on_format = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(platform_mark(key, 58), 0, Qt.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel(title)
        name.setStyleSheet("font-size:19px; font-weight:700; background:transparent;")
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
        self.badge = StreamBadge(self)
        lay.addWidget(self.badge)
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
            self.auth_label.setWordWrap(True)
            auth_row.addWidget(self.auth_label, 1)
            self.find_btn = None
            if key == "youtube":
                self.find_btn = QPushButton("Find my stream")
                self.find_btn.setObjectName("quiet")
                self.find_btn.setCursor(Qt.PointingHandCursor)
                self.find_btn.clicked.connect(lambda: self.platform_auth.find_youtube_streams(picked=True))
                auth_row.addWidget(self.find_btn)
                platform_auth.broadcasts.connect(self._on_broadcasts)
            self.auth_btn = QPushButton()
            self.auth_btn.setObjectName("quiet")
            self.auth_btn.setCursor(Qt.PointingHandCursor)
            self.auth_btn.clicked.connect(self.toggle_auth)
            auth_row.addWidget(self.auth_btn)
            lay.addLayout(auth_row)
            platform_auth.changed.connect(self._auth_changed)
            self._auth_changed(key)

    def set_detected(self, info):
        self.detected = info
        self.badge.show_stream(info, self.s, self.key == "youtube")

    def toggle_auth(self):
        if self.platform_auth.is_connected(self.key):
            self.platform_auth.disconnect(self.key)
        else:
            self.platform_auth.login(self.key)

    def _on_broadcasts(self, items, picked):
        if picked:
            return self._choose_stream(items)
        ready = [b for b in items if not b.get("stale")]
        if not ready:
            return
        best = ready[0]
        current = youtube_id(self.edit.text())
        if self.source.running or current == best["id"]:
            return
        if self.edit.text().strip():              # never replace a link the streamer pasted: it may be another channel
            self.platform_auth.notice.emit("Found your stream \"%s\". Press Find my stream to use it." % best.get("title", ""))
        else:
            self._use_stream(best)

    def _choose_stream(self, items):
        if not items:
            self.platform_auth.notice.emit("No live or scheduled streams found on this YouTube account.")
            return
        self.stream_menu = QMenu(self)
        for b in items:
            action = self.stream_menu.addAction(stream_label(b).replace("&", "&&"))
            action.triggered.connect(lambda _=False, b=b: self._use_stream(b))
        self.stream_menu.popup(self.find_btn.mapToGlobal(self.find_btn.rect().bottomLeft()))

    def _use_stream(self, b):
        if self.source.running:
            self.platform_auth.notice.emit("Disconnect from the current stream first, then choose another.")
            return
        link = "https://www.youtube.com/watch?v=" + b["id"]
        self.edit.setText(link)
        self.s.set(self.key, link)
        self.s.set("youtube_auto_id", b["id"])    # chosen, not typed: going live on another stream may replace it
        if b.get("live"):
            self.platform_auth.notice.emit("Using your live stream \"%s\". Press Connect." % b.get("title", ""))
        else:
            self.platform_auth.notice.emit("Using your scheduled stream \"%s\". Press Connect once it is live." % b.get("title", ""))

    def _auth_changed(self, platform):
        if platform != self.key or self.auth_label is None:
            return
        if self.find_btn is not None:
            self.find_btn.setVisible(self.platform_auth.is_connected(platform))
        if self.platform_auth.is_connected(platform):
            self.auth_label.setText("Signed in as %s" % (self.platform_auth.display_name(platform) or "account"))
            self.auth_btn.setText("Disconnect account")
        else:
            self.auth_label.setText("Sign in to post in chat" if platform == "kick" else "Sign in for chat, polls, and platform alerts")
            self.auth_btn.setText("Login")

    def paintEvent(self, event):
        super().paintEvent(event)
        size = min(150, self.height() - 40)                  # large, faint platform symbol behind the card
        if size < 60:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(0.10)
        p.translate(self.width() - size - 22, (self.height() - size) / 2)
        platform_glyph(p, self.key, size, QColor(PLATFORM_COLORS[self.key][0]))
        p.end()

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
        paint_status(self.status, self.btn, self.source.running, text, ok)

    def set_status(self, text, ok):
        self._show(text, ok)


def paint_status(status, btn, running, text, ok):
    """Status pill and Connect / Disconnect / Retry button of a stream card."""
    status.setText("●  " + text)
    if ok:
        kind = "pillOn"
    elif "..." in text:
        kind = "pillWait"
    elif text in ("Not connected", "Disconnected", "Offline"):
        kind = "pill"
        status.setText("●  Offline")
    else:
        kind = "pillBad"
    status.setObjectName(kind)
    status.style().unpolish(status)
    status.style().polish(status)
    if running and "..." in text:
        btn.setText("Connecting...")
        role = "primary"
    elif running:
        btn.setText("Disconnect")
        role = "stop"
    elif kind == "pillBad":
        btn.setText("Retry")
        role = "primary"
    else:
        btn.setText("Connect")
        role = "primary"
    btn.setObjectName(role)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


class ExtraStreamCard(QFrame):
    """An added chat stream (any platform, its own reader), so two YouTube or Twitch chats can be read together."""

    PLACEHOLDERS = {"youtube": "Paste a live link or video ID", "twitch": "Channel name", "kick": "Channel name"}

    def __init__(self, hub, data, on_change, on_remove, settings=None, on_format=None):
        super().__init__()
        self.setObjectName("tile")
        self.hub, self.on_change = hub, on_change
        self.s, self.on_format = settings, on_format
        self.detected = None
        self.auto = bool(data.get("auto"))        # added by stream detection, so it goes away when the stream ends
        self.id = int(data["id"])
        self.key = "extra:%d" % self.id
        self.source = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(10)
        self.mark = QLabel()
        self.mark.setAlignment(Qt.AlignCenter)
        self.mark.setFixedSize(36, 36)
        head.addWidget(self.mark)
        self.platform_box = QComboBox()
        for name, key in (("YouTube Live", "youtube"), ("Twitch", "twitch"), ("Kick", "kick")):
            self.platform_box.addItem(name, key)
        head.addWidget(self.platform_box, 1)
        self.status = QLabel("●  Offline")
        self.status.setObjectName("pill")
        head.addWidget(self.status, 0, Qt.AlignVCenter)
        remove = QPushButton("Remove")
        remove.setObjectName("quiet")
        remove.setCursor(Qt.PointingHandCursor)
        remove.clicked.connect(lambda: on_remove(self))
        head.addWidget(remove)
        lay.addLayout(head)
        self.edit = QLineEdit(data.get("target", ""))
        lay.addWidget(self.edit)
        self.badge = StreamBadge(self)
        lay.addWidget(self.badge)
        self.room = QLineEdit(data.get("room", ""))
        self.room.setObjectName("optional")
        self.room.setPlaceholderText("Kick chatroom ID, only if the name lookup fails")
        lay.addWidget(self.room)
        self.label = QLineEdit(data.get("label", ""))
        self.label.setObjectName("optional")
        self.label.setMaxLength(16)
        self.label.setPlaceholderText("Short name in the chat feed (optional), like Vertical")
        lay.addWidget(self.label)
        self.btn = QPushButton("Connect")
        self.btn.setObjectName("primary")
        self.btn.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.btn, 0, Qt.AlignLeft)
        self.btn.clicked.connect(self.toggle)
        self.edit.returnPressed.connect(self.toggle)
        for field in (self.edit, self.room, self.label):
            field.editingFinished.connect(self.on_change)
        self.platform_box.setCurrentIndex(max(0, self.platform_box.findData(data.get("platform"))))
        self.platform_box.currentIndexChanged.connect(lambda _: (self._use_platform(), self.on_change()))
        self._use_platform()

    def platform(self):
        return self.platform_box.currentData()

    def _use_platform(self):
        p = self.platform()
        self.source = SOURCES[p](self.hub, self.key)
        self.mark.setText("")
        self.mark.setStyleSheet("background: transparent;")
        self.mark.setPixmap(platform_tile(p, self.mark.width()))
        self.edit.setPlaceholderText(self.PLACEHOLDERS[p])
        self.room.setVisible(p == "kick")

    def data(self):
        return {"id": self.id, "platform": self.platform(), "target": self.edit.text().strip(),
                "room": self.room.text().strip(), "label": self.label.text().strip(), "auto": self.auto}

    def set_detected(self, info):
        self.detected = info
        self.badge.show_stream(info, self.s, self.platform() == "youtube")

    def toggle(self):
        if self.source.running:
            self.source.stop()
            self.set_status("Stopping...", False)
        else:
            self.on_change()
            d = self.data()
            self.source.start(*((d["target"], d["room"]) if d["platform"] == "kick" else (d["target"],)))
            self.platform_box.setEnabled(False)

    def set_status(self, text, ok):
        paint_status(self.status, self.btn, self.source.running, text, ok)
        self.platform_box.setEnabled(not self.source.running)


class StreamBadge(QWidget):
    """Shown on a card when the stream was found through the signed-in account: its title and, on YouTube, Long or Shorts."""

    def __init__(self, card):
        super().__init__()
        self.card = card
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.text = QLabel()
        self.text.setObjectName("hint")
        self.text.setWordWrap(True)
        row.addWidget(self.text, 1)
        self.format = QComboBox()
        for name, value in FORMATS:
            self.format.addItem(name, value)
        self.format.setToolTip("YouTube does not say which is which, so CHATDOOM guesses. Correct it here.")
        self.format.currentIndexChanged.connect(self._picked)
        row.addWidget(self.format)
        self.hide()

    def show_stream(self, info, settings, youtube):
        if not info:
            self.hide()
            return
        self.text.setText("Live on %s: %s" % (info.get("account") or "your account", info.get("title") or "Untitled stream"))
        self.format.setVisible(youtube)
        self.format.blockSignals(True)
        self.format.setCurrentIndex(max(0, self.format.findData(stream_format(settings, info))))
        self.format.blockSignals(False)
        self.show()

    def _picked(self):
        if self.card.detected and self.card.on_format:
            self.card.on_format(self.card.detected["id"], self.format.currentData())


class MainWindow(ChatActions, StreamWatch, QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(PRODUCT_NAME)
        screen = QApplication.primaryScreen()
        room = screen.availableGeometry() if screen else None
        self.resize(min(1280, room.width() - 40) if room else 1280, min(840, room.height() - 60) if room else 840)
        self.setMinimumSize(980, 680)
        self.s = Settings()
        set_custom_theme(self.s.get("theme_custom"))
        self.hub = Hub()
        self.speaker = Speaker(self.s)
        self.words_path = os.path.join(data_dir(), "hinglish_words.txt")
        self.blocked_path = os.path.join(data_dir(), "blocked_words.txt")
        hinglish.load_words(self.words_path)
        hinglish.on_unknown = self._unknown_word
        self.mod = Moderator(self.s, self.blocked_path)
        self.raid = RaidGuard(self.s)
        self.raid_timer = QTimer(self)
        self.raid_timer.setInterval(5000)
        self.raid_timer.timeout.connect(self._raid_tick)
        self.memes_dir = os.path.join(data_dir(), "Memes")
        self.commands = Commands(self.s, self.memes_dir)
        self.connected = set()
        self.extra_cards = {}
        self._anims = []
        self._anim_targets = []
        self.fx = FX()
        self.fx.enabled = not bool(self.s.get("lite_mode"))
        self.motion = Motion(self.s, self)
        self.glow = CardGlow(self.s, self)
        self.msg_seen = self.msg_read = self.msg_skipped = 0
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
        self.yt_beat = QTimer(self)                       # refreshes the bot's status while you stream on YouTube
        self.yt_beat.timeout.connect(self.ytmod.refresh_info)
        self.overlay = Overlay(self.s, os.path.join(ROOT, "assets", "fonts"), self._overlay_cfg,
                               os.path.join(data_dir(), "Soundboard"), self.memes_dir)
        self.overlay.start()
        self.ovpage = OverlayPage(self.s, self.overlay)
        self.music = MusicPlayer(self.s, self.overlay.push)
        self.musicpage = MusicPage(self.s, self.music, self.overlay)
        self.cmdpage = CommandsPage(self.s, self.commands, self._test_command)
        self.tools = Tools(self.s, data_dir(), self.music)
        self.commands.points = self.tools.points
        self.commands.values = self.tools.command_values
        self.toolspage = ToolsPage(self.s, self.tools, self)
        self.alertspage = AlertsPage(self.s, self.overlay)
        self.stylespage = OverlayDesignPage(self.s, self.overlay)
        self.hotkeys = Hotkeys()
        self._hotkeys_applied = False
        self.updater = Updater(self.s)
        self.pending_update = None
        self._quitting = False
        self.tray = None
        self.modes = WindowModes(self, self.s, PRODUCT_NAME, tray=lambda: self.tray is not None and self.tray.isVisible())

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        canvas = Backdrop(self.s, THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME]))
        canvas.setObjectName("canvas")
        self.canvas = canvas
        self.toasts = Toasts(canvas, self.s)
        self.settingspage = SettingsPage(self.s, self, [(i, PAGES[i]) for i in (0, 1, 11, 14, 7, 9, 12, 13, 10, 2, 8, 3, 6, 4, 5)])
        self.theme_combo, self.backdrop_combo = self.settingspage.theme, self.settingspage.backdrop
        right = QVBoxLayout(canvas)
        right.setContentsMargins(28, 18, 28, 18)
        right.setSpacing(14)
        right.addWidget(self._build_topbar())
        self.banner = self._build_banner()
        right.addWidget(self.banner)
        self.statbar = QWidget()
        bar = QHBoxLayout(self.statbar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(14)
        self.stat_cards = [StatCard("layers", "violet", "", "", seed=i * 1.7) for i in range(3)]
        for card in self.stat_cards:
            self.motion.add(card)
            bar.addWidget(card, 1)
        right.addWidget(self.statbar)
        self.stack = QStackedWidget()
        for page in (self._page_connect(), self._page_feed(), self._page_voice(), self._page_mod(), self.discord, self.payments, self.ytpage, self.ovpage, self.musicpage, self.cmdpage, self.toolspage,
                     self.alertspage, self.toolspage.loyalty, self.toolspage.engage, self.stylespage, self.settingspage):
            self.stack.addWidget(page)
        right.addWidget(self.stack, 1)
        root.addWidget(canvas, 1)
        self.glow.watch(self.stack)
        self.glow.watch(self.statbar)

        self.hub.message.connect(self.on_message)
        self.hub.status.connect(self.on_status)
        self.platform_auth.notice.connect(lambda t: self.feed.append("<span style='color:#8ab4ff'>Account: %s</span>" % esc(t)))
        self.platform_auth.changed.connect(self._platform_account_changed)
        self.platform_auth.subscribers.connect(self.on_youtube_subscribers)
        self.twitch_events.alert.connect(self.on_twitch_event)
        self.twitch_events.notice.connect(lambda t: self.feed.append("<span style='color:#9146ff'>Twitch alerts: %s</span>" % esc(t)))
        self.platform_auth.refresh("youtube")
        self.platform_auth.refresh("twitch")
        self.platform_auth.refresh("kick")
        self.platform_auth.find_youtube_streams()
        self._start_chat()
        self._start_stream_watch()
        self.speaker.note.connect(lambda t: self.feed.append("<span style='color:#ffb020'>%s</span>" % esc(t)))
        self.speaker.note.connect(lambda t: logs.get("voice").warning(t))
        if logs.last_run_unclean():
            QTimer.singleShot(3500, lambda: self.toasts.show("CHATDOOM did not close normally last time. If it crashed, "
                                                             "Settings > Data and backup > Save logs for support makes a zip you can send us.", "warn", 10))
        self.links.notice.connect(lambda t: self.feed.append("<span style='color:#7c9cff'>Discord: %s</span>" % esc(t)))
        self.links.notice.connect(lambda t: logs.get("discord").info(t))
        self.sync = QTimer(self)                      # report activity to Discord once a minute
        self.sync.timeout.connect(self.links.save)
        self.sync.timeout.connect(self.tools.save)
        self.tick = QTimer(self)                      # stream tools: poll end, timers, points bonus (cheap, once a second)
        self.tick.timeout.connect(self._tools_tick)
        self.tick.start(1000)
        self._last_points_tick = self._last_timer_tick = time.time()
        self.stream_end = QTimer(self)
        self.stream_end.setSingleShot(True)
        self.stream_end.timeout.connect(self._stream_over)
        self.music.changed.connect(lambda: self.toolspage.refresh_live() if self._tools_open() else None)
        self.sync.start(60000)
        self.relink = QTimer(self)                    # refresh the list of linked viewers every 5 minutes
        self.relink.timeout.connect(self.links.refresh)
        self.relink.start(300000)
        QTimer.singleShot(2000, self.links.refresh)
        self.poller.tip.connect(self.on_tip)
        self.poller.notice.connect(lambda t: self.feed.append("<span style='color:#ffd24d'>%s</span>" % esc(t)))
        self.poller.notice.connect(lambda t: logs.get("tips").info(t))
        self.ytmod.notice.connect(lambda t: self.feed.append("<span style='color:#ff8a5c'>YouTube mod: %s</span>" % esc(t)))
        self.ytmod.notice.connect(lambda t: logs.get("ytmod").info(t))
        QTimer.singleShot(2500, self.poller.apply)
        self.speaker.busy_changed.connect(self.music.duck)                     # music gets quieter while a message is read aloud
        self.music.notice.connect(lambda t: self.feed.append("<span style='color:#7cf0c0'>Music: %s</span>" % esc(t)))
        self.music.notice.connect(lambda t: logs.get("music").info(t))
        QTimer.singleShot(1500, lambda: self.music.next() if self.s.get("music_autoplay") and self.music.tracks else None)
        self.updater.found.connect(self._update_found)
        self.updater.status.connect(self._update_status)
        self.updater.message.connect(lambda t: self.feed.append("<span style='color:#7cf0c0'>Update: %s</span>" % esc(t)))
        self.updater.message.connect(lambda t: logs.get("update").info(t))
        self.updater.progress.connect(self.banner_text.setText)
        self.updater.quit_now.connect(lambda: QTimer.singleShot(400, self.quit_app))
        QTimer.singleShot(3000, self.updater.after_start)
        QTimer.singleShot(6000, self._auto_update)
        self.apply_theme(self.s.get("theme"))
        self.goto(self._first_page())
        self.tools_changed()
        self.set_always_on_top(bool(self.s.get("always_on_top")), show=False)
        self.sync_tray()
        if self.s.get("start_muted"):
            self.mute_btn.setChecked(True)
        if self.s.get("auto_connect"):
            QTimer.singleShot(1200, self._connect_saved)

    # ---------- layout ----------
    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(232)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(2)
        self.logo = QLabel()
        self.logo.setObjectName("logo")
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setContentsMargins(4, 0, 4, 4)
        logo = QPixmap(os.path.join(ROOT, "assets", "chatdoom-logo.png"))
        if not logo.isNull():
            self.logo.setPixmap(logo.scaled(76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo.setText(PRODUCT_NAME)
        lay.addWidget(self.logo)
        navbox = QWidget()
        navlay = QVBoxLayout(navbox)                  # scrolls on small screens so nothing is ever cut off
        navlay.setContentsMargins(0, 0, 0, 0)
        navlay.setSpacing(0)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        groups = (("Stream", (0, 1, 11, 14, 7)), ("Community", (9, 12, 13, 10)), ("Sound", (2, 8)), ("Safety and links", (3, 6, 4, 5)), ("App", (15,)))
        for title, indexes in groups:
            g = QLabel(title.upper())
            g.setObjectName("group")
            navlay.addWidget(g)
            for i in indexes:
                b = QPushButton("  " + PAGES[i])
                b.setIcon(nav_icon(i))
                b.setIconSize(QSize(19, 19))
                b.setObjectName("nav")
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                self.nav.addButton(b, i)
                navlay.addWidget(b)
        navlay.addStretch(1)
        self.nav.idClicked.connect(self.goto)
        self.nav_glow = NavIndicator(navbox, self.s)
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)    # on a short window, a visible bar shows there is more
        self.nav_scroll.setWidget(navbox)
        lay.addWidget(self.nav_scroll, 1)
        ver = QLabel(label())
        ver.setObjectName("hint")
        ver.setAlignment(Qt.AlignCenter)
        ver.setContentsMargins(12, 4, 12, 0)
        lay.addWidget(ver)
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
        if self.s.get("ov_sound") and alert_sounds.is_builtin(sound_path):
            sound_url = alert_sounds.url_for(sound_path)
        elif (self.s.get("ov_sound") and sound_name and os.path.isfile(sound_path) and
                os.path.dirname(os.path.realpath(sound_path)) == sound_dir):
            sound_url = "/sounds/" + urllib.parse.quote(sound_name)
        return {"colors": {"a1": t["a1"], "a2": t["a2"], "a3": t["a3"]}, "sound": bool(self.s.get("ov_sound")) and not sound_url,
                "seconds": int(self.s.get("ov_seconds")), "showMessage": bool(self.s.get("ov_show_message")),
                "chatSeconds": int(self.s.get("ov_chat_seconds")), "maxLines": 8,
                "memeSeconds": int(self.s.get("meme_seconds")),
                "soundUrl": sound_url, "soundVolume": int(self.s.get("ov_sound_volume")),
                "typeSounds": alert_styles.overlay_type_sounds(self.s, sound_dir),
                "alertDesigns": alert_styles.overlay_designs(self.s, sound_dir, self.memes_dir),
                "tipTiers": alert_styles.overlay_tip_tiers(self.s, sound_dir, self.memes_dir),
                "designs": overlay_styles.all_designs(self.s),
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
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(10)
        accent = QFrame()
        accent.setObjectName("titleBar")
        accent.setFixedSize(6, 44)
        lay.addWidget(accent, 0, Qt.AlignTop)
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
        self.title_line = QFrame()
        self.title_line.setObjectName("titleLine")
        self.title_line.setFixedSize(72, 3)
        left.addSpacing(6)
        left.addWidget(self.title_line)
        lay.addLayout(left, 1)
        self.mute_btn = QPushButton()
        self.mute_btn.setObjectName("quiet")
        self.mute_btn.setIcon(utility_icon("mute"))
        self.mute_btn.setCheckable(True)
        self.mute_btn.setChecked(bool(self.s.get("muted")))
        self._update_mute_button(self.s.get("muted"))
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.toggled.connect(self._mute)
        self.tts_btn = QPushButton()
        self.tts_btn.setObjectName("quiet")
        self.tts_btn.setCheckable(True)
        self.tts_btn.setCursor(Qt.PointingHandCursor)
        self._show_read_mode()
        self.tts_btn.clicked.connect(lambda on: self.set_read_mode("tts" if on else "all"))
        skip = QPushButton("Skip")
        skip.setIcon(utility_icon("skip"))
        skip.setObjectName("quiet")
        skip.setToolTip("Skip the message being spoken")
        skip.setCursor(Qt.PointingHandCursor)
        skip.clicked.connect(self.speaker.skip)
        test = QPushButton("Test voice")
        test.setIcon(utility_icon("test"))
        test.setObjectName("quiet")
        test.setToolTip("Speak a short sample")
        test.setCursor(Qt.PointingHandCursor)
        test.clicked.connect(self.test_voice)
        self.safe_btn = QPushButton("Safe mode")
        self.safe_btn.setObjectName("quiet")
        self.safe_btn.setCheckable(True)
        self.safe_btn.setCursor(Qt.PointingHandCursor)
        self.safe_btn.setToolTip("Raid shield: read only paid messages and skip links until you turn it off")
        self.safe_btn.clicked.connect(self.set_safe_mode)
        for b in (self.mute_btn, self.tts_btn, self.safe_btn, skip, test):
            lay.addWidget(b, 0, Qt.AlignTop)
        return bar

    def _stat(self, icon, color, number, caption, seed=0.0):
        chip = StatCard(icon, color, number, caption, seed)
        self.motion.add(chip)
        return chip, chip.num

    def _page_stats(self, i):
        """The three live numbers shown at the top of each page."""
        s = self.s
        on_off = lambda v: "On" if v else "Off"
        if i == 1:
            return (("chat", "violet", self.msg_seen, "Messages"), ("check", "green", self.msg_read, "Read aloud"),
                    ("shield", "orange", self.msg_skipped, "Skipped"))
        if i == 2:
            engine = "Neural" if s.get("engine") == "neural" else "Windows"
            return (("voice", "violet", engine, "Voice engine"), ("music", "green", "%d%%" % int(s.get("volume")), "Volume"),
                    ("star", "orange", "%+d%%" % int(s.get("rate")), "Speed"))
        if i == 3:
            return (("shield", "violet", len(self.mod.blocked), "Blocked words"), ("chat", "green", int(s.get("max_len")), "Max length"),
                    ("power", "orange", self.msg_skipped, "Skipped"))
        if i == 4:
            return (("discord", "violet", "Linked" if s.get("cloud_token") else "Not set", "Server"),
                    ("people", "green", len(self.links.linked), "Linked viewers"), ("star", "orange", len(self.links.counts), "Known viewers"))
        if i == 5:
            page = self.payments.tip
            state = ("Live" if page.get("enabled") else "Paused") if page.get("status") == "ACTIVE" else ("Checking" if page else "Not set")
            return (("money", "violet", state, "UPI tip page"),
                    ("check", "green", on_off(s.get("tips_on")), "Listening"), ("star", "orange", self.tools.stats.paid_count, "Paid this stream"))
        if i == 6:
            state = {"online": "Online", "offline": "Offline", "waking": "Checking"}.get(self.ytmod.bot_state, "Unknown")
            return (("play", "violet", state, "Moderator bot"), ("shield", "green", int(s.get("yt_actions_count") or 0), "Actions today"),
                    ("layers", "orange", int(s.get("mod_budget")), "Daily limit"))
        if i == 7:
            return (("screen", "violet", int(s.get("ov_port")), "Local port"), ("star", "green", str(s.get("ov_alert_style")).capitalize(), "Alert style"),
                    ("chat", "orange", str(s.get("ov_chat_style")).capitalize(), "Chat style"))
        if i == 8:
            return (("music", "violet", len(self.music.tracks), "Tracks"), ("voice", "green", "%d%%" % int(s.get("music_volume")), "Volume"),
                    ("power", "orange", "Playing" if self.music.playing else "Stopped", "Player"))
        if i == 12:
            return (("people", "violet", len(self.tools.points.file.data), "Viewers with points"), ("star", "green", on_off(s.get("levels_on")), "Levels"),
                    ("money", "orange", len(self.tools.shop_items()), "Shop items"))
        if i == 13:
            return (("chat", "violet", "Running" if self.tools.prediction.active else "None", "Prediction"), ("people", "green", len(self.tools.queue.people), "In the queue"),
                    ("star", "orange", len(self.tools.goals()), "Goals"))
        if i == 9:
            return (("commands", "violet", len(s.get("commands") or []), "Commands"), ("star", "green", len(s.get("memes") or []), "Memes"),
                    ("power", "orange", on_off(s.get("commands_on")), "Chat commands"))
        return (("people", "violet", len(self.tools.seen_stream), "Viewers this stream"), ("layers", "green", len(s.get("counters") or []), "Counters"),
                ("star", "orange", len(s.get("timers") or []), "Timers"))

    def _refresh_stats(self):
        i = self.stack.currentIndex()
        shown = i not in (0, 11, 14, 15) and bool(self.s.get("show_stats"))   # Connect has its own cards; the design pages and Settings need the room
        self.statbar.setVisible(shown)
        if not shown:
            return
        try:
            for card, stat in zip(self.stat_cards, self._page_stats(i)):
                card.show_stat(*stat)
        except Exception:                            # a number must never stop the page from opening
            pass

    def _sync_summary(self):
        total = len(self.cards) + len(self.extra_cards)
        on = len(self.connected)
        count_to(self.num_total, total, self.s, self)
        count_to(self.num_on, on, self.s, self)
        count_to(self.num_off, max(0, total - on), self.s, self)

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
        stats.setSpacing(14)
        platforms, self.num_total = self._stat("layers", "violet", "3", "Platforms", 0.0)
        connected, self.num_on = self._stat("check", "green", "0", "Connected", 1.7)
        offline, self.num_off = self._stat("power", "orange", "3", "Offline", 3.4)
        for chip in (platforms, connected, offline):
            stats.addWidget(chip, 1)
        lay.addLayout(stats)
        self.cards = {
            "youtube": PlatformCard("youtube", "YouTube Live", "Paste a live link or video ID", YouTubeSource(self.hub), self.s,
                                    hint="Sign in and CHATDOOM finds your live streams by itself, Shorts and long format, and connects them. Or paste a link.",
                                    field="Stream link or video ID", platform_auth=self.platform_auth),
            "twitch": PlatformCard("twitch", "Twitch", "Channel name", TwitchSource(self.hub), self.s,
                                   hint="Reads chat anonymously. Sign in for alerts, moderation, and connecting by itself when you go live.",
                                   field="Channel name",
                                   platform_auth=self.platform_auth),
            "kick": PlatformCard("kick", "Kick", "Channel name", KickSource(self.hub, cloud=self.platform_auth), self.s,
                                 extra=("kick_room", "Chatroom ID, only if the name lookup fails"),
                                 hint="Reads public chat by channel name. Sign in to post, moderate, and connect by itself when you go live.",
                                 field="Channel name", platform_auth=self.platform_auth),
        }
        self.cards["youtube"].on_format = self.set_stream_format
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.addWidget(self.cards["youtube"], 0, 0)
        grid.addWidget(self.cards["twitch"], 0, 1)
        grid.addWidget(self.cards["kick"], 1, 0)
        aside = HeroCard(os.path.join(ROOT, "assets", "robot.png"))
        self.motion.add(aside)
        al = QVBoxLayout(aside)
        al.setContentsMargins(22, 18, 22, 18)
        title = QLabel("One voice for every chat")
        title.setObjectName("heroTitle")
        body = QLabel("Connect any mix of platforms, or add a second YouTube, Twitch or Kick stream. "
                      "They all share the voice, moderation, commands and overlays.")
        body.setObjectName("heroText")
        body.setWordWrap(True)
        al.addWidget(title)
        al.addWidget(body)
        al.addStretch(1)
        self.add_stream_btn = QPushButton("Add stream")
        self.add_stream_btn.setObjectName("primary")
        self.add_stream_btn.setCursor(Qt.PointingHandCursor)
        self.add_stream_btn.clicked.connect(lambda: self._add_stream())
        al.addWidget(self.add_stream_btn, 0, Qt.AlignLeft)
        grid.addWidget(aside, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.extra_grid = QGridLayout()
        self.extra_grid.setSpacing(12)
        self.extra_grid.setColumnStretch(0, 1)
        self.extra_grid.setColumnStretch(1, 1)
        lay.addLayout(self.extra_grid)
        lay.addStretch(1)
        for d in self.s.get("extra_streams") or []:
            if isinstance(d, dict) and d.get("platform") in SOURCES and str(d.get("id", "")).isdigit():
                self._add_stream(d, save=False)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    # ---------- added streams ----------
    def _add_stream(self, data=None, save=True):
        if len(self.extra_cards) >= MAX_EXTRA_STREAMS:
            return None
        if data is None:
            data = {"id": max([c.id for c in self.extra_cards.values()] + [1]) + 1, "platform": "youtube"}
        card = ExtraStreamCard(self.hub, data, self._save_streams, self._remove_stream, self.s, self.set_stream_format)
        self.extra_cards[card.key] = card
        self._layout_streams()
        if hasattr(self, "stack"):
            self.glow.watch(self.stack)
        if save:
            self._save_streams()
        self._streams_changed()
        return card

    def _remove_stream(self, card):
        card.source.stop()
        self.extra_cards.pop(card.key, None)
        self.connected.discard(card.key)
        card.setParent(None)
        card.deleteLater()
        self._layout_streams()
        self._save_streams()
        self._update_live()
        self._streams_changed()

    def _layout_streams(self):
        while self.extra_grid.count():
            self.extra_grid.takeAt(0)
        for i, card in enumerate(self.extra_cards.values()):
            self.extra_grid.addWidget(card, i // 2, i % 2)
        self.add_stream_btn.setEnabled(len(self.extra_cards) < MAX_EXTRA_STREAMS)
        self.add_stream_btn.setText("Add stream" if len(self.extra_cards) < MAX_EXTRA_STREAMS else "Stream limit reached")
        self._sync_summary()

    def _save_streams(self):
        self.s.set("extra_streams", [c.data() for c in self.extra_cards.values()])

    def _tag(self, m):
        """Feed tag: the account and format for a stream found through sign-in ("YT Drxshi · Shorts"). For one added by link,
        YT / TW / KICK for the main streams, and YT2, TW·Vertical ... for added ones."""
        tag = TAGS.get(m.platform, "?")
        name = self.stream_name(m.stream)
        if name:
            return "%s %s" % (tag, name)
        card = self.extra_cards.get(m.stream)
        if card is None:
            return tag
        label = card.label.text().strip()
        if label:
            return "%s·%s" % (tag, label)
        same = [c for c in self.extra_cards.values() if c.platform() == card.platform()]
        return "%s%d" % (tag, same.index(card) + 2)

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
        self.feed.document().setMaximumBlockCount(600)
        self.feed.hint = "Chat messages appear here. Click a message to reply, time out and more. Grey lines were skipped by moderation."
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
        lay.addWidget(self._chat_toolbar())
        lay.addWidget(self.chat_box, 1)
        controls = QFrame()
        controls.setObjectName("tile")
        row = QHBoxLayout(controls)
        row.setContentsMargins(12, 8, 12, 8)
        self.action_platform = QComboBox()
        compact(self.action_platform, 15)
        self.action_platform.currentIndexChanged.connect(self._action_platform_changed)
        self.reply_cancel = QPushButton("Cancel reply")
        self.reply_cancel.setObjectName("quiet")
        self.reply_cancel.clicked.connect(self.cancel_reply)
        self.reply_cancel.hide()
        self.message_edit = QLineEdit()
        self.message_edit.setMinimumWidth(110)
        self.message_edit.setPlaceholderText("Sign in, then type a chat message...")
        self.message_edit.returnPressed.connect(self._send_chat_message)
        self.send_chat_btn = QPushButton("Send")
        self.send_chat_btn.setObjectName("primary")
        self.send_chat_btn.clicked.connect(self._send_chat_message)
        self.poll_btn = QPushButton("Create poll")
        self.poll_btn.setObjectName("quiet")
        self.poll_btn.clicked.connect(self._create_chat_poll)
        self.chat_controls_btn = QPushButton("Chat controls")
        self.chat_controls_btn.setObjectName("quiet")
        self.chat_controls_btn.clicked.connect(self._show_chat_controls)
        row.addWidget(self.action_platform)
        row.addWidget(self.reply_cancel)
        row.addWidget(self.message_edit, 1)
        row.addWidget(self.send_chat_btn)
        row.addWidget(self.poll_btn)
        row.addWidget(self.chat_controls_btn)
        lay.addWidget(controls)
        self._refresh_targets()
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
        self.poll_btn.setEnabled(platform not in ("kick", ALL_CHATS))
        self.poll_btn.setToolTip("Kick does not offer polls to apps." if platform == "kick" else "")

    def _platform_account_changed(self, platform):
        if not hasattr(self, "action_platform") or platform not in self.platform_auth.SUPPORTED:
            return
        self._refresh_targets()
        if self.platform_auth.is_connected(platform):
            QTimer.singleShot(0, lambda: self.check_streams((platform,)))
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
                self._push_alert({
                    "platform": "youtube",
                    "category": "subscriber",
                    "name": subscriber.get("name") or "Someone",
                    "message": "",
                })
        self.s.set("yt_subscriber_seen", seen[-500:])
        self.s.set("yt_subscriber_cursor", int(result.get("cursor") or self.s.get("yt_subscriber_cursor") or 0))

    def _push_alert(self, alert):
        self.overlay.push("alert", alert)
        if self.s.get("flash_paid") and alert.get("category") in ("tip", "superchat", "membership", "subscription", "gift", "raid"):
            QApplication.alert(self, 2000)
        self.tools.note_alert(alert)
        self.tools_changed()

    def on_twitch_event(self, alert):
        self._push_alert(alert)
        self.feed.append("<span style='color:#9146ff'>Twitch alert: %s %s</span>" %
                         (esc(alert.get("name") or "Someone"), esc(alert.get("category") or "event")))

    def _send_chat_message(self):
        self.send_typed()

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
                                           duration.value() if platform == "twitch" else 60, self._target_video())

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
            voice = getattr(self, "voice_page", None)
            if popup is not None and popup.isAncestorOf(obj):
                bar = self.chat_style_scroll.verticalScrollBar()
                bar.setValue(bar.value() - event.angleDelta().y())
                return True
            if voice is not None and voice.isAncestorOf(obj):
                area = obj.parentWidget()
                while area is not None and not isinstance(area, QScrollArea):
                    area = area.parentWidget()
                if area is not None:
                    area.verticalScrollBar().setValue(area.verticalScrollBar().value() - event.angleDelta().y())
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

    def _voice_switch(self, title, detail, key, checked=None, on_toggle=None):
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
        switch.setChecked(bool(self.s.get(key)) if checked is None else checked)
        switch.toggled.connect(on_toggle or (lambda on, k=key: self.s.set(k, on)))
        lay.addLayout(text, 1)
        lay.addWidget(switch, 0, Qt.AlignTop)
        row.switch = switch
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
        self.voice_page = SubPage()
        fill_voice_page(self, self.voice_page)
        return self.voice_page

    def _page_mod(self):
        page = SubPage()
        filters, lay = section_card("What gets read", "These filters decide what gets read aloud. Skipped messages stay visible in grey on the Live chat page.")
        for text, key in (("Skip messages with links", "skip_links"), ("Skip !commands", "skip_cmds"),
                          ("Ignore known bots (Nightbot, StreamElements, ...)", "ignore_bots"),
                          ("Only read moderators and the streamer", "mods_only")):
            lay.addWidget(self._bind_check(text, key))
        lay.addWidget(labeled("Max message length", self._bind_spin("max_len", 20, 500, " chars")))
        lay.addWidget(labeled("Ignore repeats for", self._bind_spin("dedupe_secs", 0, 120, " s")))
        lay.addWidget(labeled("Same viewer cooldown", self._bind_spin("user_cooldown", 0, 60, " s")))
        page.add_tab("What gets read").addWidget(filters)
        words, lay = section_card("Blocked words", "One per line. Never read aloud, also blocks paid messages, and is checked in viewer names too.")
        self.blocked_edit = QPlainTextEdit()
        self.blocked_edit.setMinimumHeight(170)
        try:
            with open(self.blocked_path, encoding="utf-8") as f:
                self.blocked_edit.setPlainText(f.read())
        except Exception:
            pass
        lay.addWidget(self.blocked_edit, 1)
        self.name_action = QComboBox()
        self.name_action.addItem("Read the message, hide the name", "anonymous")
        self.name_action.addItem("Don't read the message", "skip")
        self.name_action.setCurrentIndex(max(0, self.name_action.findData(self.s.get("blocked_name_action") or "anonymous")))
        self.name_action.currentIndexChanged.connect(lambda _: self.s.set("blocked_name_action", self.name_action.currentData()))
        self.name_action.setToolTip("Viewer names are checked against these words too. A hidden name is said as \"Ek viewer\" "
                                    "(\"A viewer\" with an English voice) and also hidden on the OBS overlay.")
        lay.addWidget(labeled("Name has a blocked word", self.name_action))
        save = QPushButton("Save blocked words")
        save.setObjectName("primary")
        save.clicked.connect(self._save_blocked)
        lay.addWidget(save, 0, Qt.AlignLeft)
        page.add_tab("Blocked words").addWidget(words, 1)
        allowed, lay = section_card("Allowed words", "One per line. Never blocked, even when they contain a blocked word. "
                                                     "Use it when a blocked word catches normal chat.")
        self.allowed_edit = QPlainTextEdit()
        self.allowed_edit.setMinimumHeight(170)
        try:
            with open(self.mod.allowed_path, encoding="utf-8") as f:
                self.allowed_edit.setPlainText(f.read())
        except Exception:
            pass
        lay.addWidget(self.allowed_edit, 1)
        save = QPushButton("Save allowed words")
        save.setObjectName("primary")
        save.clicked.connect(self._save_allowed)
        lay.addWidget(save, 0, Qt.AlignLeft)
        page.add_tab("Allowed words").addWidget(allowed, 1)
        shield, lay = section_card("Raid shield", "When lots of new accounts or copy-pasted messages flood chat, safe mode turns on by itself: "
                                                  "only paid messages are read and links are skipped. Your settings are not changed.")
        lay.addWidget(self._bind_check("Turn on safe mode by itself during a raid", "raid_on"))
        lay.addWidget(labeled("New chatters in %ds" % RAID_WINDOW, self._bind_spin("raid_new_chatters", 3, 500, " people")))
        lay.addWidget(labeled("Turn off after quiet", self._bind_spin("raid_cooldown_min", 1, 60, " min")))
        self.raid_mode_box = QComboBox()
        self.raid_mode_box.addItem("Read paid messages only", "paid")
        self.raid_mode_box.addItem("Read paid messages and mods", "mods")
        self.raid_mode_box.setCurrentIndex(max(0, self.raid_mode_box.findData(self.s.get("raid_mode") or "paid")))
        self.raid_mode_box.currentIndexChanged.connect(lambda _: self._raid_mode_changed(self.raid_mode_box.currentData()))
        lay.addWidget(labeled("While safe mode is on", self.raid_mode_box))
        lay.addWidget(self._bind_check("Post in Discord when a raid turns it on (uses your Discord webhook)", "raid_discord"))
        note = QLabel("8 copies of the same message in %ds also count as a raid. Turn it on or off any time with the "
                      "Safe mode button at the top or the hotkey (Ctrl+Alt+H, change it in Stream tools)." % RAID_WINDOW)
        note.setWordWrap(True)
        note.setObjectName("muted")
        lay.addWidget(note)
        self.safe_now_btn = QPushButton("Turn safe mode on now")
        self.safe_now_btn.clicked.connect(lambda: self.set_safe_mode(not self.raid.on))
        lay.addWidget(self.safe_now_btn, 0, Qt.AlignLeft)
        page.add_tab("Raid shield").addWidget(shield)
        page.finish()
        return page

    # ---------- behaviour ----------
    def apply_theme(self, name):
        if name not in THEMES:
            name = DEFAULT_THEME
        t = THEMES[name]
        self.s.set("theme", name)
        self.setStyleSheet(build_qss(name))
        self.fx.recolor(t["a1"])
        self.glow.color = QColor(t["a1"])
        for switch in self.findChildren(Switch):
            switch.set_accent(t["a1"])
        if hasattr(self, "canvas"):
            self.canvas.set_theme(t)

    def _open_appearance(self):
        AppearanceDialog(self, self.s, self.set_custom_colours, self.set_background_picture, self.set_background_dim).exec()

    def set_custom_colours(self, colours):
        self.s.set("theme_custom", colours)
        set_custom_theme(colours)
        if self.theme_combo.currentText() == CUSTOM_THEME:
            self.apply_theme(CUSTOM_THEME)
        else:
            self.theme_combo.setCurrentText(CUSTOM_THEME)

    def set_background_picture(self, value):
        self.s.set("bg_image", value)
        self.backdrop_combo.setCurrentIndex(self.backdrop_combo.findData("image"))
        self.canvas.sync()

    def set_background_dim(self, value):
        self.s.set("bg_dim", value)
        self.canvas.sync()

    def _lite(self, on):
        self.s.set("lite_mode", on)
        self.fx.set_enabled(not on)
        self.canvas.sync()
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
        if i != 15 and self.s.get("last_page") != i:
            self.s.set("last_page", i)
        self.blurb.setText(PAGE_BLURB[i])
        page = self.stack.widget(i)
        self.stack.setCurrentIndex(i)
        self.nav_glow.move_to(self.nav.button(i))
        self.nav_scroll.ensureWidgetVisible(self.nav.button(i), 0, 8)
        self._refresh_stats()
        if page in self.toolspage.pages:
            self.toolspage.refresh()
        elif page is self.alertspage:
            self.alertspage.reload_sounds()
            self.alertspage.load()
        elif page is self.stylespage:
            self.stylespage.load()
        elif page is self.settingspage:
            self.settingspage.refresh()
        if self.s.get("lite_mode"):
            self.title_line.setFixedWidth(72)
            return
        sweep = QVariantAnimation(self)              # the line under the title draws itself
        sweep.setDuration(420)
        sweep.setStartValue(0)
        sweep.setEndValue(72)
        sweep.setEasingCurve(QEasingCurve.OutCubic)
        sweep.valueChanged.connect(lambda v: self.title_line.setFixedWidth(int(v)))
        group = QParallelAnimationGroup(self)
        group.addAnimation(sweep)
        cards_in, cards = stagger_in(page, group)
        if cards_in is not None:
            group.addAnimation(cards_in)
            targets = list(cards)
        else:
            targets = [page]
            fx = QGraphicsOpacityEffect(page)
            fx.setOpacity(0.0)
            page.setGraphicsEffect(fx)
            a = QPropertyAnimation(fx, b"opacity")
            a.setDuration(220)
            a.setStartValue(0.0)
            a.setEndValue(1.0)
            a.setEasingCurve(QEasingCurve.OutCubic)
            group.addAnimation(a)
        rise = QPropertyAnimation(page, b"pos")
        rise.setDuration(260)
        rise.setStartValue(page.pos() + QPoint(0, 18))
        rise.setEndValue(page.pos())
        rise.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(rise)
        group.finished.connect(self._end_anim)
        self._anims, self._anim_targets = [group], targets
        group.start()

    def _mute(self, v):
        self.s.set("muted", v)
        self._update_mute_button(v)
        if v:
            self.speaker.clear()
            self.feed.append("<span style='color:#ffb020'>Voice reading muted. Click Unmute to resume.</span>")
        else:
            self.feed.append("<span style='color:#7cf0c0'>Voice reading resumed.</span>")

    def set_read_mode(self, mode):
        """all: every allowed chat message. tts: only messages starting with !tts. paid: only paid messages.
        Tips, Super Chats, Bits and memberships are read in every mode; moderators are read in all and tts."""
        self.s.set("read_mode", mode)
        self._show_read_mode()
        box = getattr(self, "read_mode_box", None)
        if box is not None:
            box.blockSignals(True)
            box.setCurrentIndex(max(0, box.findData(mode)))
            box.blockSignals(False)
        text = {"all": "Reading all chat again.",
                "tts": "Reading only !tts messages now. Tips, Super Chats, members and mods are still read.",
                "paid": "Reading only paid messages now."}.get(mode, "")
        self.feed.append("<span style='color:#7cf0c0'>%s</span>" % esc(text))
        logs.get("voice").info("Read mode: %s", mode)

    def _show_read_mode(self):
        tts = self.s.get("read_mode") == "tts"
        self.tts_btn.setChecked(tts)
        self.tts_btn.setText("!tts only" if tts else "All chat")
        self.tts_btn.setToolTip("Reading only messages that start with !tts (plus tips, members and mods). Click to read all chat."
                                if tts else "Reading all chat. Click to read only messages that start with !tts (tips, members and mods are still read).")

    def _update_mute_button(self, muted):
        self.mute_btn.setText("Unmute" if muted else "Mute")
        self.mute_btn.setToolTip(
            "Voice is muted. Click to resume reading chat." if muted
            else "Mute voice reading and clear the queue")

    def _save_blocked(self):
        try:
            with open(self.blocked_path, "w", encoding="utf-8") as f:
                f.write(self.blocked_edit.toPlainText())
            self.mod.reload_blocked()
            self.feed.append("<span style='color:#8a93a8'>Blocked words saved (%d)</span>" % len(self.mod.blocked))
        except Exception as e:
            self.feed.append("<span style='color:#ff5470'>Could not save: %s</span>" % esc(str(e)))

    # ---------- viewer memory cards ----------
    def _memory_card(self, now=None):
        """A returning viewer's card: on the streamer's screen only (a pop-up and the Live chat feed), never the overlay."""
        text = self.tools.memory.next_card(now)
        if text:
            self.toasts.show(text, "info", 8)
            self.feed.append("<span style='color:#c4a7ff'>◆ %s</span>" % esc(text))
        return text

    # ---------- raid shield (safe mode) ----------
    def _safe_on(self, reason):
        """Safe mode is a rule on top of the settings: read_mode and skip_links are never changed, so nothing needs restoring."""
        self.mod.safe = self.s.get("raid_mode") or "paid"
        self.raid_timer.start()
        self._show_safe()
        manual = self.raid.manual
        self.feed.append("<span style='color:#ff5470'><b>Safe mode ON</b> (%s). Only paid messages%s are read, links are skipped.</span>"
                         % (esc(reason), " and mods" if self.mod.safe == "mods" else ""))
        self.toasts.show("Safe mode ON" if manual else "Safe mode ON (raid detected)", "warn")
        logs.get("voice").warning("Safe mode on: %s", reason)
        url = self.s.get("webhook_url")
        if not manual and self.s.get("raid_discord") and url:
            text = "CHATDOOM safe mode is ON: possible raid (%s). Only paid messages are read for now." % reason
            run_bg(self.bridge, "ui:hookraid", lambda: post_webhook(url, text))

    def _safe_off(self, why):
        self.raid.stop()
        self.mod.safe = ""
        self.raid_timer.stop()
        self._show_safe()
        self.feed.append("<span style='color:#7cf0c0'><b>Safe mode OFF</b> (%s). Back to your normal settings.</span>" % esc(why))
        self.toasts.show("Safe mode OFF", "good")
        logs.get("voice").info("Safe mode off: %s", why)

    def set_safe_mode(self, on):
        """The Safe mode button and hotkey."""
        if on and not self.raid.on:
            self.raid.start()
            self._safe_on("turned on by you")
        elif not on and self.raid.on:
            self._safe_off("turned off by you")
        else:
            self._show_safe()

    def _raid_tick(self):
        if self.raid.tick():
            self._safe_off("%s quiet minutes" % self.s.get("raid_cooldown_min"))

    def _raid_mode_changed(self, mode):
        self.s.set("raid_mode", mode)
        if self.raid.on:
            self.mod.safe = mode

    def _show_safe(self):
        on = self.raid.on
        self.safe_btn.setChecked(on)
        self.safe_btn.setText("SAFE MODE ON" if on else "Safe mode")
        self.safe_btn.setStyleSheet("color:#ff5470; font-weight:600;" if on else "")
        button = getattr(self, "safe_now_btn", None)
        if button is not None:
            button.setText("Turn safe mode off" if on else "Turn safe mode on now")

    def _save_allowed(self):
        try:
            with open(self.mod.allowed_path, "w", encoding="utf-8") as f:
                f.write(self.allowed_edit.toPlainText())
            self.mod.reload_blocked()
            self.feed.append("<span style='color:#8a93a8'>Allowed words saved (%d)</span>" % len(self.mod.allowed))
        except Exception as e:
            self.feed.append("<span style='color:#ff5470'>Could not save: %s</span>" % esc(str(e)))

    def _unknown_word(self, w):
        self.feed.append("<span style='color:#8a93a8'>new short word '%s' - add it in Voice > Edit word list</span>" % esc(w))

    def on_status(self, key, text, ok):
        card = self.cards.get(key) or self.extra_cards.get(key)
        if card is None:                          # a stream that was removed while it was still connecting
            self.connected.discard(key)
            return
        card.set_status(text, ok)
        was_live = bool(self.connected)
        (self.connected.add if ok else self.connected.discard)(key)
        self._sync_summary()
        self._refresh_stream_filter()
        if self.connected and not was_live:
            self._stream_started()
        elif was_live and not self.connected:
            self.stream_end.start(STREAM_END_GRACE)
        if key in self.cards:                     # Discord announcements and the YouTube bot follow your main streams
            if ok:
                self.discord.auto_announce(key, card.edit.text().strip() if key == "youtube" else None)
            if key == "youtube":
                if ok and self.ytmod.verified:
                    self.ytmod.refresh_info()
                    self.yt_beat.start(8 * 60 * 1000)
                elif not ok:
                    self.yt_beat.stop()
        self._update_live()

    def _update_live(self):
        if self.connected and self.live.isHidden():
            self.live.show()
            self.pulse.start()
        elif not self.connected and not self.live.isHidden():
            self.pulse.stop()
            self.live.hide()

    def on_message(self, m):
        if self.ytmod.is_bot(m):                  # its reasons stay out of speech, stats and moderation
            self.feed.append("<span style='color:#5d667d'>%s %s: %s</span>" % (esc(self._tag(m)), esc(m.author), esc(m.text)), "skipped", m, m.stream)
            return
        self.tools.stats.add_message(m)
        if m.kind == "chat" and not m.mod and m.platform not in ("test", "tip"):
            key = viewer_key(m)                   # before observe(), which marks the viewer as seen
            raid = self.raid.feed(key, m.text, key not in self.tools.seen_ever)
            if raid:
                self._safe_on(raid)
        is_link = self.links.handle(m)
        if not is_link and self._run_command(m):
            return
        ok, reason = self.mod.check(m)
        if ok and viewer_key(m) in (self.s.get("chat_muted") or []):
            ok, reason = False, "you stopped reading this viewer"
        CHAT_LOG.debug("%s %s %s %s: %s%s", m.platform, m.kind, "READ" if ok else "skip (%s)" % reason, m.author,
                       (m.text or "")[:80], " [%s]" % m.amount if m.amount else "")
        self.msg_seen += 1
        self.msg_read += bool(ok)
        self.msg_skipped += not ok
        if is_link:
            ok, reason = False, "link code (processing)"
        elif not ok and m.platform == "youtube" and not m.mod and m.stream in ("", "youtube"):
            self.ytmod.flag(m, reason)            # the bot moderates your main YouTube stream only
        color = COLORS.get(m.platform, "#8a93a8")
        amt = " <span style='color:#ffd24d'>[%s]</span>" % esc(m.amount) if m.amount else ""
        tag = "<span style='color:%s'><b>%s</b></span>" % (color, esc(self._tag(m)))
        hidden = self.mod.name_blocked(m)        # a name with a blocked word is never spoken or shown on stream
        name = self.mod.masked_name() if hidden else m.author
        if ok or reason in SHOW_ONLY:            # !tts-only and paid-only modes still show chat, they just don't speak it
            author = shape_chat_text(name, self.s.get("chat_transform"))
            text = shape_chat_text(m.text, self.s.get("chat_transform"))
            self.feed_message(m, tag, amt, author, text, BLOCKED_NAME if hidden else "")
            welcome = self.tools.observe(m)
            if welcome and not hidden:            # the welcome line says the name
                self._welcome(m, welcome)
            if ok:
                self.speaker.say(name, spoken_text(m.text), m.amount if m.kind == "super" else "", self._who(m))
            if m.platform != "tip":
                self.overlay.push("chat", {"platform": m.platform, "name": name, "text": m.text, "mod": bool(m.mod), "emotes": m.emotes})
            if m.kind in ("super", "member"):
                category = "membership" if m.kind == "member" else ("tip" if m.platform == "tip" else "superchat")
                alert = {"platform": m.platform, "category": category, "name": name, "amount": m.amount, "message": m.text}
                if m.rupees is not None:
                    alert["value"] = m.rupees          # picks the tip's design by amount (Alerts > Tips by amount)
                self._push_alert(alert)
            if m.kind == "super":
                self.discord.post_paid(replace(m, author=name) if hidden else m)
            if m.kind in ("super", "member"):
                self.toasts.show("%s %s %s" % (name, "sent" if m.kind == "super" else "became a member", m.amount or ""), "gold")
        else:
            author = shape_chat_text(name, self.s.get("chat_transform"))
            text = shape_chat_text(m.text, self.s.get("chat_transform"))
            self.feed_skipped(m, esc(self._tag(m)), author, text, reason)

    # ---------- !commands and !memes ----------
    def _run_command(self, m):
        """Answer a !command or play a !meme. True means the message was one, so it is not read aloud itself."""
        text = (m.text or "").strip()
        if m.platform == "tip" or not (text.startswith("!") or (self.tools.poll.active and text.isdigit())):
            return False
        if m.platform != "test" and ((self.s.get("ignore_bots") and looks_like_bot(m, self.s.get("bot_names")))
                                     or self.mod._blocked_hit(m.text) or self.mod.name_blocked(m)
                                     or (self.mod.safe and not m.mod)):   # no !memes or !commands for raiders
            return False                          # moderation skips it and shows why
        act = self.commands.handle(m) or self.tools.handle(m)
        if act is None:
            return False
        tag = "<span style='color:%s'><b>%s</b></span>" % (COLORS.get(m.platform, "#8a93a8"), esc(self._tag(m)))
        who = esc(shape_chat_text(m.author, self.s.get("chat_transform")))
        if act["skipped"]:
            self.feed.append("<span style='color:#5d667d'>%s %s: %s <i>(!%s not run: %s)</i></span>"
                             % (esc(self._tag(m)), who, esc(m.text), esc(act["name"]), esc(act["skipped"])))
            return True
        welcome = self.tools.observe(m)
        if welcome:
            self._welcome(m, welcome)
        if act["type"] in ("vote", "entry"):
            self.feed.append("<span style='color:#5d667d'>%s %s: %s <i>(%s)</i></span>"
                             % (esc(self._tag(m)), who, esc(m.text), "vote counted" if act["type"] == "vote" else "entered the giveaway"))
            self.tools_changed()
            return True
        self.tools.stats.count("meme" if act["type"] == "meme" else "command")
        self.feed.append("%s <b>%s</b>: <span style='color:#c4a7ff'>%s</span>" % (tag, who, esc(m.text)))
        if act["reply"]:
            video, why = self._reply_target(m)
            if video is None:
                self.feed.append("<span style='color:#8a93a8'>&raquo; %s <i>(not sent in chat: %s)</i></span>" % (esc(act["reply"]), esc(why)))
            else:
                self._post_chat(m.platform, act["reply"], video)
                self.feed.append("<span style='color:#7cf0c0'>&raquo; %s</span>" % esc(act["reply"]))
        if act["type"] == "meme":
            self.speaker.announce(act["speak"], act["sound"])
            if act["image"] or act["speak"]:
                self.overlay.push("meme", {"name": act["name"], "user": m.author, "caption": act["speak"],
                                           "image": "/memes/" + urllib.parse.quote(act["image"]) if act["image"] else ""})
        elif act["speak"]:
            self.speaker.announce(act["speak"])
        if act.get("toast"):
            self.toasts.show(act["toast"])
        if act["type"] in ("counter", "song", "points", "bet", "queue", "shop"):
            self.tools_changed(lists=act["type"] == "counter")
        return True

    # ---------- stream tools ----------
    def _welcome(self, m, text):
        self.feed.append("<span style='color:#ffd24d'>\u2605 %s</span>" % esc(text))
        self.toasts.show("New chatter: %s" % m.author, "good")
        if self.s.get("welcome_speak") and (self.s.get("read_mode") or "all") == "all":   # !tts-only and paid-only stay quiet
            self.speaker.announce(text)
        if self.s.get("welcome_reply"):
            video, _ = self._reply_target(m)
            if video is not None:
                self._post_chat(m.platform, text, video)

    def _can_post(self, platform):
        return self.platform_auth.is_connected(platform) or (platform == "youtube" and self.ytmod.can_post())

    def _post_chat(self, platform, text, video=""):
        """The YouTube bot speaks when it is set up, like Nightbot. Otherwise the signed-in account does."""
        if platform == "youtube" and self.ytmod.can_post():
            self.ytmod.say(text, video)
        else:
            self.platform_auth.send_message(platform, text, video, quiet=True)

    def _broadcast(self, text, rewards=False):
        """Post a message in every main chat that is connected and signed in. Returns the platforms it went to.
        rewards: the message is about points, bets or giveaways, which YouTube viewers can't take part in (YouTube rules),
        so it skips those chats instead of advertising something they can't join."""
        sent = [p for p in self.platform_auth.SUPPORTED if p in self.connected and self._can_post(p)
                and not (rewards and p in NO_REWARDS)]
        for p in sent:
            self._post_chat(p, text)
        where = ", ".join(PLATFORM_NAMES[p] for p in sent)
        self.feed.append("<span style='color:%s'>&raquo; %s <i>(%s)</i></span>" % (
            "#7cf0c0" if sent else "#8a93a8", esc(text), ("posted to " + where) if sent else "not posted: connect and sign in to YouTube, Twitch or Kick"))
        return sent

    def _tools_open(self):
        return self.stack.currentWidget() in self.toolspage.pages

    def tools_changed(self, lists=False):
        self.overlay.push("widgets", self.tools.widgets(time.time()))
        if self._tools_open():
            if lists:
                self.toolspage.refresh_lists()
            self.toolspage.refresh_live()

    def _tools_tick(self):
        self._refresh_stats()
        now = time.time()
        self._memory_card(now)
        poll = self.tools.poll
        if poll.active and now >= poll.ends:
            self.end_poll()
        elif poll.active:
            self.overlay.push("widgets", self.tools.widgets(now))           # the seconds left count down on stream
            if self._tools_open():
                self.toolspage.refresh_live(now)
        guess = self.tools.prediction
        if guess.open and now >= guess.ends:
            self.lock_prediction()
        elif guess.open:
            self.overlay.push("widgets", self.tools.widgets(now))
        self._announce_levels()
        if now - self._last_points_tick >= 60:
            self._last_points_tick = now
            self.tools.points.tick(now)
        if now - self._last_timer_tick >= 20:
            self._last_timer_tick = now
            if not self.connected:
                self.tools.reset_timers()                                    # timers only count while you are live
            for t in self.tools.due_timers(now):
                mode = t.get("mode") or "reply"
                if mode in ("reply", "both"):
                    self._broadcast(t["message"])
                if mode in ("speak", "both"):
                    self.speaker.announce(t["message"])

    def start_poll(self, question, options, seconds):
        problem = self.tools.poll.start(question, options, seconds, time.time())
        if problem:
            self.toasts.show(problem, "warn")
            return
        poll = self.tools.poll
        self._broadcast("Poll: %s Vote with %s" % (poll.question, " | ".join("!vote %d = %s" % (i + 1, o) for i, o in enumerate(poll.options))))
        self.toasts.show("Poll started: %s" % poll.question, "good")
        self.tools_changed()

    def end_poll(self):
        result = self.tools.poll.close()
        if not result:
            return
        self._broadcast(result)
        self.speaker.announce(result)
        self.toasts.show(result, "gold", 6)
        self.tools_changed()

    def _announce_levels(self):
        waiting, self.tools.points.levelups = self.tools.points.levelups, []
        for platform, name, level in waiting:
            text = (self.s.get("level_text") or "{user} reached level {level}!").replace("{user}", name).replace("{level}", str(level))
            self.feed.append("<span style='color:#ffd24d'>\u2605 %s</span>" % esc(text))
            if self.s.get("level_announce") and platform in self.platform_auth.SUPPORTED and self._can_post(platform):
                self._post_chat(platform, text)

    def start_prediction(self, question, options, seconds):
        if not self.s.get("points_on"):
            self.toasts.show("Turn on Points on the Loyalty page first.", "warn")
            return
        guess = self.tools.prediction
        problem = guess.start(question, options, seconds, time.time())
        if problem:
            self.toasts.show(problem, "warn")
            return
        self._broadcast("Prediction: %s Bet with %s" % (guess.question, " | ".join("!bet %d 100 = %s" % (i + 1, o) for i, o in enumerate(guess.options))), rewards=True)
        self.toasts.show("Prediction started", "good")
        self.tools_changed()

    def lock_prediction(self):
        if self.tools.prediction.open:
            self.tools.prediction.lock()
            self._broadcast("Bets are locked!", rewards=True)
            self.tools_changed()

    def resolve_prediction(self, number):
        paid, text = self.tools.prediction.resolve(number)
        if not text:
            return
        self.tools.settle_prediction(paid)
        self._broadcast(text, rewards=True)
        self.toasts.show(text, "gold", 6)
        self.tools_changed()

    def cancel_prediction(self):
        guess = self.tools.prediction
        if guess.active:
            paid, text = guess.refund()
            self.tools.settle_prediction(paid)
            self._broadcast(text, rewards=True)
        elif guess.result:
            guess.__init__()
        self.tools_changed()

    def set_queue(self, on):
        self.tools.queue.open = on
        self._broadcast("The viewer queue is open! Type !queue to join." if on else "The viewer queue is closed.")
        self.tools_changed()

    def next_in_queue(self):
        person = self.tools.queue.next()
        if person is None:
            self.toasts.show("Nobody is waiting in the queue.", "warn")
            return
        self._broadcast("Next up: %s" % person[1])
        self.toasts.show("Next up: %s" % person[1], "gold", 6)
        self.tools_changed()

    def clear_queue(self):
        self.tools.queue.people = []
        self.tools_changed()

    def open_giveaway(self, keyword, cost):
        problem = self.tools.giveaway.start(keyword, cost)
        if problem:
            self.toasts.show(problem, "warn")
            return
        g = self.tools.giveaway
        self._broadcast("Giveaway open! Type !%s to enter%s." % (g.keyword, " (costs %d %s)" % (g.cost, self.tools.points.name) if g.cost else ""), rewards=True)
        self.toasts.show("Giveaway open: !%s" % g.keyword, "good")
        self.tools_changed()

    def close_giveaway(self):
        g = self.tools.giveaway
        if g.active:
            g.active = False
            self._broadcast("Giveaway entries are closed (%d entered)." % len(g.entries), rewards=True)
            self.tools_changed()

    def pick_winner(self):
        win = self.tools.giveaway.pick()
        if win is None:
            self.toasts.show("Nobody (else) has entered the giveaway.", "warn")
            return
        _, name, platform = win
        text = "The giveaway winner is %s (%s)!" % (name, PLATFORM_NAMES.get(platform, platform.title()))
        self._broadcast("Congratulations %s, you won the giveaway!" % name, rewards=True)
        self.speaker.announce(text)
        self.toasts.show(text, "gold", 8)
        self.tools_changed()

    def clear_giveaway(self):
        self.tools.giveaway.__init__()
        self.tools_changed()

    def clear_song_requests(self):
        self.music.requests.clear()
        self.tools_changed()

    def summary_text(self):
        return "\n".join(self.tools.stats.lines(time.time()))

    def post_summary(self):
        if not self.tools.stats.started:
            self.toasts.show("Nothing to summarize yet: connect a stream first.", "warn")
            return False
        url = self.s.get("webhook_url")
        if not url:
            self.toasts.show("Add a Discord webhook on the Discord page to post the summary.", "warn")
            return False
        text = self.summary_text()
        run_bg(self.bridge, "ui:summary", lambda: post_webhook(url, text))
        self.feed.append("<span style='color:#7c9cff'>Discord: stream summary posted</span>")
        self.toasts.show("Stream summary posted to Discord", "good")
        return True

    def reset_summary(self):
        self.tools.stats.reset()
        if self.connected:
            self.tools.stats.begin(time.time())
        self.tools_changed()

    def _stream_started(self):
        self.stream_end.stop()
        stats = self.tools.stats
        if not stats.started or stats.ended:          # a new stream (not a quick reconnect)
            stats.begin(time.time())
            self.tools.seen_stream = set()
            self.tools.reset_timers()

    def _stream_over(self):
        stats = self.tools.stats
        if self.connected or not stats.started or stats.ended:
            return
        stats.finish(time.time() - STREAM_END_GRACE / 1000)
        if stats.ended - stats.started < 600:
            return                                    # a short test connection is not worth a summary
        self.feed.append("<span style='color:#c4a7ff'>%s</span>" % esc(self.summary_text()).replace("\n", "<br>"))
        self.toasts.show("Stream summary ready on the Stream tools page", "good", 6)
        if self.s.get("summary_post") and self.s.get("webhook_url"):
            self.post_summary()

    # ---------- hotkeys ----------
    def apply_hotkeys(self):
        self._hotkeys_applied = True
        return self.hotkeys.apply(self.winId(), self.s)

    def nativeEvent(self, event_type, message):
        act = self.hotkeys.match(event_type, message)
        if act:
            self._hotkey(act)
            return True, 0
        return False, 0                               # not ours: Qt handles it as usual

    def _hotkey(self, act):
        if act == "hk_skip":
            self.speaker.skip()
        elif act == "hk_mute":
            want = not bool(self.s.get("muted"))
            if self.mute_btn.isChecked() == want:
                self._mute(want)
            else:
                self.mute_btn.setChecked(want)
        elif act == "hk_tts":
            self.set_read_mode("all" if self.s.get("read_mode") == "tts" else "tts")
            self.toasts.show("Reading only !tts messages" if self.s.get("read_mode") == "tts" else "Reading all chat")
        elif act == "hk_safe":
            self.set_safe_mode(not self.raid.on)
        elif act == "hk_music":
            self.music.toggle()
        elif act == "hk_counter":
            counters = self.tools.counters()
            if counters:
                self.tools.bump_counter(counters[0]["name"], 1)
                c = self.tools.counters()[0]
                self.toasts.show("%s: %d" % (c.get("label") or c["name"].title(), int(c.get("value") or 0)))
                self.tools_changed(lists=True)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.nav_glow.follow)
        if not self._hotkeys_applied:
            problems = self.apply_hotkeys()
            if problems and sys.platform == "win32" and QApplication.platformName() == "windows":
                self.feed.append("<span style='color:#ffb020'>Hotkeys: %s</span>" % esc("; ".join(problems)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toasts"):
            self.toasts.layout_all()

    def _reply_target(self, m):
        """(YouTube link or '' for the main stream, '') when a command reply can be posted, else (None, reason)."""
        if m.platform == "test":
            return None, "test"
        name = PLATFORM_NAMES.get(m.platform, m.platform.title())
        if m.platform not in self.platform_auth.SUPPORTED:
            return None, "%s replies are not supported" % name
        if not self._can_post(m.platform):
            return None, "sign in to %s on the Connect page" % name
        if m.stream in ("", m.platform):
            return "", ""
        card = self.extra_cards.get(m.stream)
        if m.platform == "youtube" and card is not None:
            return card.edit.text().strip(), ""
        return None, "%s replies only go to your own channel" % name

    def _test_command(self, name):
        self.on_message(Message("test", "Test", "!" + name, mod=True))
        self.goto(1)

    def on_tip(self, ev):
        msg, note = (ev.get("message") or "").strip(), ""
        if msg and self.mod._blocked_hit(msg):
            msg, note = "", "message hidden: blocked word"
        elif msg and ev.get("currency") == "INR" and float(ev.get("value") or 0) < int(self.s.get("tip_min")):
            msg, note = "", "message not read: below the minimum amount"
        rupees = float(ev.get("value") or 0) if (ev.get("currency") or "INR") == "INR" else None
        self.on_message(Message("tip", ev.get("name") or "Someone", msg, "super", ev.get("display", ""),
                               event_id=str(ev.get("id") or ""), rupees=rupees))
        if note:
            self.feed.append("<span style='color:#5d667d'>%s</span>" % esc(note))

    def test_voice(self):
        if self.s.get("muted"):
            self.feed.append("<span style='color:#ffb020'>Voice is muted. Click Unmute before testing speech.</span>")
            return
        for m in (Message("test", "Test", "bhai kya krra hoga, nhi pta yr, bht mast stream h lol"),
                  Message("test", "Test", "नमस्ते दोस्तों, चैट रीडर चालू है।")):
            self.on_message(m)
        self.goto(1)

    # ---------- window and app behaviour (Settings page) ----------
    def _first_page(self):
        wanted = int(self.s.get("start_page"))
        wanted = int(self.s.get("last_page")) if wanted < 0 else wanted
        return wanted if 0 <= wanted < self.stack.count() else 0

    def _connect_saved(self):
        for card in list(self.cards.values()) + list(self.extra_cards.values()):
            if card.edit.text().strip() and not card.source.running:
                card.toggle()

    def set_always_on_top(self, on, show=True):
        shown = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(on))
        if show and shown:
            self.show()

    def sync_tray(self):
        wanted = bool(self.s.get("close_to_tray") or self.s.get("esc_to_tray")) and QSystemTrayIcon.isSystemTrayAvailable()
        if wanted and self.tray is None:
            self.tray = QSystemTrayIcon(QApplication.windowIcon() or self.windowIcon(), self)
            self.tray.setToolTip(PRODUCT_NAME)
            menu = QMenu(self)
            menu.addAction("Open %s" % PRODUCT_NAME, self.show_from_tray)
            menu.addAction("Quit", self.quit_app)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda why: self.show_from_tray() if why == QSystemTrayIcon.Trigger else None)
        if self.tray is not None:
            self.tray.setVisible(wanted)

    def show_from_tray(self):
        self.modes.show_again()

    def start_window(self, autostart=False):
        """Called once at launch. Only Windows' own start can begin hidden, and only if there is a tray icon to get back."""
        if autostart and self.s.get("start_hidden") and self.tray is not None and self.tray.isVisible():
            return
        self.modes.show()           # in the saved window mode, at the saved size

    def keyPressEvent(self, e):
        if not self.modes.handle_key(e):      # F11 fullscreen, Esc to the tray
            super().keyPressEvent(e)

    def quit_app(self):
        self._quitting = True
        self.close()
        QApplication.quit()

    def restart_app(self):
        system.restart()
        self.quit_app()

    def closeEvent(self, e):
        if not self._quitting and self.s.get("close_to_tray") and self.modes.hide_to_tray():
            e.ignore()
            return
        if not self._quitting and self.s.get("confirm_quit") and self.connected:
            ask = QMessageBox.question(self, PRODUCT_NAME, "You are still connected. Close CHATDOOM and stop the voice and overlays?")
            if ask != QMessageBox.Yes:
                e.ignore()
                return
        self.modes.remember()
        logs.LOG.info("Closing: %d chat messages seen, %d read aloud, %d skipped", self.msg_seen, self.msg_read, self.msg_skipped)
        self.links.save()
        if self.tools.prediction.active:             # nobody loses points because the app was closed
            self.tools.settle_prediction(self.tools.prediction.refund()[0])
        self.tools.save(final=True)
        self.hotkeys.clear()
        self.music.stop()
        self.twitch_events.stop()
        self.yt_subscriber_timer.stop()
        self.overlay.stop()
        for c in list(self.cards.values()) + list(self.extra_cards.values()):
            c.source.stop()
        self.speaker.clear()
        super().closeEvent(e)
