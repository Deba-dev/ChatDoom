"""OBS overlays page: copy the addresses into OBS Browser sources, or bring your own StreamElements overlay."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QSpinBox

from .ui_kit import SubPage, copy_row, field_row, hrow, info_box, section_card


class OverlayPage(SubPage):
    def __init__(self, settings, overlay):
        super().__init__()
        self.s, self.overlay = settings, overlay
        lay = self.add_tab("Alerts and chat")

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

        lay = self.add_tab("Music and memes")
        c, cl = section_card("Now playing",
                             "Shows the song from the Music page (title and artist) in the corner of your stream. In OBS: Sources > + > Browser. Width 700, Height 160.")
        wrap, self.music_url = copy_row(overlay.url("music"))
        cl.addWidget(wrap)
        lay.addWidget(c)

        c, cl = section_card("Memes on screen",
                             "Shows the picture or GIF (and the line) of a meme when a viewer types its !command. Add memes on the Commands page. "
                             "In OBS: Sources > + > Browser. Width 1280, Height 720. Meme sounds play from the app, like the voice.")
        wrap, self.meme_url = copy_row(overlay.url("meme"))
        cl.addWidget(wrap)
        sp = QSpinBox()
        sp.setRange(2, 30)
        sp.setValue(int(self.s.get("meme_seconds")))
        sp.valueChanged.connect(lambda v: self.s.set("meme_seconds", v))
        cl.addWidget(field_row("Meme stays on screen", "Seconds before the meme picture clears.", sp))
        lay.addWidget(c)

        lay = self.add_tab("Widgets")
        c, cl = section_card("Counters, goals, polls, predictions, giveaway and queue",
                             "Counters sit top left, goals bottom left, the latest supporters bottom right, and polls, predictions, the giveaway "
                             "and the viewer queue on the right. Set them up on the Engage page. In OBS: Sources > + > Browser. Width 1280, Height 720.")
        wrap, self.widgets_url = copy_row(overlay.url("widgets"))
        cl.addWidget(wrap)
        lay.addWidget(c)

        lay = self.add_tab("Options")
        c, cl = section_card("Overlay options", "Changes apply to OBS within a second. Only this PC can open these addresses. Alert designs are on the Alerts page.")
        sp = QSpinBox()
        sp.setRange(5, 120)
        sp.setValue(int(self.s.get("ov_chat_seconds")))
        sp.valueChanged.connect(lambda v: self.s.set("ov_chat_seconds", v))
        cl.addWidget(field_row("Chat lines stay", "Seconds before the overlay clears.", sp))
        chat_style = QComboBox()
        for label, value in (("Glass bubbles", "glass"), ("Compact", "compact"),
                             ("Streamer panel", "panel"), ("Cherry blossom", "sakura")):
            chat_style.addItem(label, value)
        chat_style.setCurrentIndex(max(0, chat_style.findData(self.s.get("ov_chat_style"))))
        chat_style.currentIndexChanged.connect(lambda _: self.s.set("ov_chat_style", chat_style.currentData()))
        cl.addWidget(field_row("Chat look", "Chat overlay style inspired by the provided reference.", chat_style))
        lay.addWidget(c)

        lay = self.add_tab("StreamElements")
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
        self.finish()

    def copy_external_url(self):
        self.s.set("ov_external_url", self.external_url.text().strip())
        QGuiApplication.clipboard().setText(self.external_url.text().strip())
