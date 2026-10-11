"""OBS overlays page: copy the addresses into OBS Browser sources, or bring your own StreamElements overlay."""
import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

from .music import scan
from .settings import data_dir
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import FormScrollArea, bind_switch, copy_row, field_row, hrow, info_box, option_switch_row, section_card


class OverlayPage(FormScrollArea):
    def __init__(self, settings, overlay):
        super().__init__()
        self.s, self.overlay = settings, overlay
        inner = QWidget()
        inner.setObjectName("page")
        self.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 8, 12, 12)
        lay.setSpacing(14)
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]

        status = QLabel("Overlay server running on this PC (port %d)" % overlay.port if overlay.port else overlay.error)
        status.setObjectName("sub")
        lay.addWidget(status)

        c, cl = section_card("Alerts on screen",
                             "In OBS: Sources > + > Browser. Width 1280, Height 420. Stays invisible until an alert, then pops up with your theme colours.")
        wrap, self.alert_url = copy_row(overlay.url("alert"))
        cl.addWidget(wrap)
        test = QPushButton("Send a test alert")
        test.setObjectName("primary")
        test.clicked.connect(lambda: overlay.push("alert", {"platform": "tip", "name": "Rahul", "amount": "\u20b9100",
                                                            "message": "Great stream bhai, keep it up!"}))
        cl.addWidget(hrow(test))
        lay.addWidget(c)

        c, cl = section_card("Chat on screen",
                             "In OBS: Sources > + > Browser. Width 520, Height 760. Transparent background; lines fade away.")
        wrap, self.chat_url = copy_row(overlay.url("chat"))
        cl.addWidget(wrap)
        test2 = QPushButton("Send a test chat message")
        test2.clicked.connect(lambda: overlay.push("chat", {"platform": "youtube", "name": "Neha", "text": "Namaste doston! \U0001F64F"}))
        cl.addWidget(hrow(test2))
        lay.addWidget(c)

        c, cl = section_card("Now playing",
                             "Shows the song from the Music page (title and artist) in the corner of your stream. In OBS: Sources > + > Browser. Width 700, Height 160.")
        wrap, self.music_url = copy_row(overlay.url("music"))
        cl.addWidget(wrap)
        lay.addWidget(c)

        c, cl = section_card("Overlay options", "Changes apply to OBS within a second. Only this PC can open these addresses.")
        for label, key, lo, hi in (("Alert stays on screen", "ov_seconds", 3, 30), ("Chat lines stay", "ov_chat_seconds", 5, 120)):
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setValue(int(self.s.get(key)))
            sp.valueChanged.connect(lambda v, k=key: self.s.set(k, v))
            cl.addWidget(field_row(label, "Seconds before the overlay clears.", sp))
        cl.addWidget(option_switch_row("Show the viewer's message in the alert", "Include the paid or highlighted message text on screen.",
                                       bind_switch(self.s, "ov_show_message", accent)))
        cl.addWidget(option_switch_row("Play a short chime with each alert", "Your voice still reads the alert aloud.",
                                       bind_switch(self.s, "ov_sound", accent)))
        self.alert_sound = QComboBox()
        self.reload_alert_sounds()
        self.alert_sound.currentIndexChanged.connect(lambda _: self.s.set("ov_sound_file", self.alert_sound.currentData() or ""))
        sound_refresh = QPushButton("Refresh sounds")
        sound_refresh.clicked.connect(self.reload_alert_sounds)
        cl.addWidget(field_row("Alert sound file", "Choose an imported effect for the on-screen alert, or use the built-in chime.", self.alert_sound))
        cl.addWidget(hrow(sound_refresh))
        alert_style = QComboBox()
        for label, value in (("Neon energy", "neon"), ("Cherry blossom", "sakura"),
                             ("Brush / ink", "brush"), ("Sharp frame", "frame")):
            alert_style.addItem(label, value)
        alert_style.setCurrentIndex(max(0, alert_style.findData(self.s.get("ov_alert_style"))))
        alert_style.currentIndexChanged.connect(lambda _: self.s.set("ov_alert_style", alert_style.currentData()))
        cl.addWidget(field_row("Alert look", "Animated alert frame style.", alert_style))
        chat_style = QComboBox()
        for label, value in (("Glass bubbles", "glass"), ("Compact", "compact"),
                             ("Streamer panel", "panel"), ("Cherry blossom", "sakura")):
            chat_style.addItem(label, value)
        chat_style.setCurrentIndex(max(0, chat_style.findData(self.s.get("ov_chat_style"))))
        chat_style.currentIndexChanged.connect(lambda _: self.s.set("ov_chat_style", chat_style.currentData()))
        cl.addWidget(field_row("Chat look", "Chat overlay style inspired by the provided reference.", chat_style))
        lay.addWidget(c)

        c, cl = section_card(
            "Choose alert types",
            "YouTube subscriber alerts are limited to publicly visible subscriptions. Twitch alerts use EventSub and need the additional account permissions.",
        )
        cl.addWidget(option_switch_row("Payment tips", "Show payment webhook alerts.", bind_switch(self.s, "ov_alert_tips", accent)))
        cl.addWidget(option_switch_row("Super Chats / Bits", "Show paid messages from YouTube or Twitch chat.", bind_switch(self.s, "ov_alert_superchats", accent)))
        cl.addWidget(option_switch_row("Membership alerts", "Show YouTube membership events when the chat source provides them.", bind_switch(self.s, "ov_alert_memberships", accent)))
        cl.addWidget(option_switch_row("YouTube subscriber alerts", "Poll public subscriber activity every five minutes while signed in.", bind_switch(self.s, "ov_alert_youtube_subscribers", accent)))
        cl.addWidget(option_switch_row("Twitch followers", "Receive follow alerts from Twitch EventSub.", bind_switch(self.s, "ov_alert_follows", accent)))
        cl.addWidget(option_switch_row("Twitch subscriptions", "Receive new, resubscription, and gift alerts from Twitch EventSub.", bind_switch(self.s, "ov_alert_subscriptions", accent)))
        cl.addWidget(option_switch_row("Twitch raids", "Receive raid alerts from Twitch EventSub.", bind_switch(self.s, "ov_alert_raids", accent)))
        lay.addWidget(c)

        c, cl = section_card("Use a StreamElements overlay",
                             "Already have an overlay in StreamElements? Paste its overlay URL here, then add it to OBS as a separate "
                             "Browser source. CHATDOOM does not import or host this overlay.")
        self.external_url = QLineEdit(self.s.get("ov_external_url"))
        self.external_url.setPlaceholderText("Paste your StreamElements overlay URL")
        self.external_url.editingFinished.connect(lambda: self.s.set("ov_external_url", self.external_url.text().strip()))
        copy_external = QPushButton("Copy URL")
        copy_external.setObjectName("quiet")
        copy_external.clicked.connect(self.copy_external_url)
        open_se = QPushButton("Open StreamElements")
        open_se.setToolTip("Opens the StreamElements overlay dashboard in your browser.")
        open_se.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://streamelements.com/dashboard/overlays")))
        cl.addWidget(hrow(self.external_url, copy_external))
        cl.addWidget(hrow(open_se))
        cl.addWidget(info_box("Use CHATDOOM's own alerts for payments and Super Chats, and your StreamElements overlay for its own follower, "
                              "sub and tip alerts. Add both as separate Browser sources and disable duplicate alert types in one source.",
                              "Using both together"))
        lay.addWidget(c)
        lay.addStretch(1)

    def reload_alert_sounds(self):
        current = self.s.get("ov_sound_file") or ""
        self.alert_sound.blockSignals(True)
        self.alert_sound.clear()
        self.alert_sound.addItem("Built-in chime", "")
        for item in scan(os.path.join(data_dir(), "Soundboard")):
            self.alert_sound.addItem(item["title"], item["path"])
        self.alert_sound.setCurrentIndex(max(0, self.alert_sound.findData(current)))
        self.alert_sound.blockSignals(False)

    def copy_external_url(self):
        self.s.set("ov_external_url", self.external_url.text().strip())
        QGuiApplication.clipboard().setText(self.external_url.text().strip())
