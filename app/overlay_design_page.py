"""Overlay styles page: the same design tools as the Alerts page, for the chat, now playing, meme and widget overlays."""
import json
import os
import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QColorDialog, QComboBox, QGridLayout, QLabel, QPushButton, QSlider, QSpinBox, QWidget

from . import overlay_styles as styles
from .ui_kit import SubPage, field_row, hrow, section_card


def _combo(options):
    box = QComboBox()
    for label, value in options:
        box.addItem(label, value)
    return box


class OverlayDesignPage(SubPage):
    def __init__(self, settings, overlay):
        super().__init__()
        self.s, self.overlay = settings, overlay
        self.view = None
        self.kind = "chat"
        self._loading = False
        self.boxes, self.sliders, self.checks, self.only = {}, {}, {}, []

        head, hl = section_card("Design overlays", "Changes reach OBS within a second. Each overlay keeps its own design.")
        self.target = _combo(styles.KINDS)
        self.target.currentIndexChanged.connect(self._target_changed)
        self.test = QPushButton("Send test to OBS")
        self.test.setObjectName("primary")
        self.test.clicked.connect(self.send_test)
        match = QPushButton("Use this style everywhere")
        match.setObjectName("quiet")
        match.setToolTip("Gives every overlay and your alerts this skin, font and colours.")
        match.clicked.connect(self.match_everywhere)
        hl.addWidget(hrow(QLabel("Editing"), self.target, self.test, match))
        self.preview_box = QWidget()
        self.preview_box.setMinimumHeight(220)
        self.preview_lay = QGridLayout(self.preview_box)
        self.preview_lay.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.preview_box)
        self.add_header(head)

        lay = self.add_tab("Packs")
        c, cl = section_card("Style packs", "The same packs as your alerts, tuned for this overlay. One click sets the skin, animations and font.")
        grid = QGridLayout()
        grid.setSpacing(8)
        self.pack_buttons = []
        for i, (name, values) in enumerate(styles.PACKS):
            b = QPushButton(name)
            b.setObjectName("quiet")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=values: self._apply(styles.pack_for(self.kind, v)))
            grid.addWidget(b, i // 3, i % 3)
            self.pack_buttons.append(b)
        cl.addLayout(grid)
        lucky = QPushButton("Surprise me")
        lucky.setObjectName("primary")
        lucky.clicked.connect(lambda: self._apply(styles.pack_for(self.kind, random.choice(styles.PACKS)[1])))
        cl.addWidget(hrow(lucky))
        lay.addWidget(c)

        lay = self.add_tab("Style")
        c, cl = section_card("Look and motion", "%d skins, and the same animations as alerts." % len(styles.SKINS))
        for key, title, note in (("skin", "Skin", "The background and frame."), ("enter", "Comes in with", "How it appears."),
                                 ("idle", "While on screen", "Chat and widgets look best without this."), ("exit", "Leaves with", "How it goes away.")):
            cl.addWidget(field_row(title, note, self._choice(key)))
        self.only.append((("meme",), self._field("effect", "Particles", "What flies around the meme.")))
        cl.addWidget(self.only[-1][1])
        lay.addWidget(c)

        lay = self.add_tab("Text")
        c, cl = section_card("Fonts and colours", "Hindi-ready fonts are marked. Fonts other than Poppins load from Google Fonts, so OBS needs the internet.")
        cl.addWidget(field_row("Font", "", self._choice("font")))
        self.text_row = field_row("Name animation", "How the name or title moves.", self._choice("text"))
        cl.addWidget(self.text_row)
        cl.addWidget(field_row("Size", "60% to 180% of the normal size.", self._slider("size", 60, 180)))
        cl.addWidget(field_row("See-through", "How solid the whole overlay is.", self._slider("opacity", 30, 100)))
        self.colour_check = self._check("useColors", "Use my own colours instead of the theme")
        self.colour_buttons = {}
        for key in ("c1", "c2", "c3"):
            b = QPushButton()
            b.setFixedSize(58, 30)
            b.clicked.connect(lambda _=False, k=key: self._pick_colour(k))
            self.colour_buttons[key] = b
        cl.addWidget(hrow(self.colour_check, *self.colour_buttons.values()))
        lay.addWidget(c)

        lay = self.add_tab("Layout")
        c, cl = section_card("Chat layout", "How the lines sit in the Browser source.")
        cl.addWidget(field_row("Align", "", self._choice("align")))
        cl.addWidget(field_row("Lines start from", "", self._choice("edge")))
        cl.addWidget(field_row("Newest line goes", "", self._choice("newest")))
        cl.addWidget(field_row("Width", "As a share of the Browser source.", self._slider("width", 30, 100)))
        cl.addWidget(field_row("Most lines on screen", "", self._slider("maxLines", 2, 20)))
        cl.addWidget(field_row("Name colour", "", self._choice("nameColour")))
        cl.addWidget(field_row("Lines stay for", "Seconds before a line clears.", self._setting_spin("ov_chat_seconds", 5, 120)))
        for key, text in (("keep", "Keep lines until newer ones push them out"), ("showTag", "Show the platform tag"), ("hideCommands", "Hide !commands")):
            cl.addWidget(self._check(key, text))
        self.only.append((("chat",), c))
        lay.addWidget(c)
        c, cl = section_card("Now playing layout", "")
        self.music_position = _combo(styles.POSITION_CHOICES["music"])
        self.music_position.currentIndexChanged.connect(lambda _: self._set("position", self.music_position.currentData()))
        cl.addWidget(field_row("Corner", "", self.music_position))
        cl.addWidget(self._check("showEq", "Show the moving bars"))
        cl.addWidget(self._check("showArtist", "Show the artist"))
        self.only.append((("music",), c))
        lay.addWidget(c)
        c, cl = section_card("Meme layout", "")
        self.meme_position = _combo(styles.POSITION_CHOICES["meme"])
        self.meme_position.currentIndexChanged.connect(lambda _: self._set("position", self.meme_position.currentData()))
        cl.addWidget(field_row("Place on screen", "", self.meme_position))
        cl.addWidget(field_row("Picture size", "", self._slider("picture", 30, 100)))
        cl.addWidget(field_row("Stays on screen", "Seconds before the meme clears.", self._setting_spin("meme_seconds", 2, 30)))
        cl.addWidget(self._check("showCaption", "Show the caption"))
        cl.addWidget(self._check("showWho", "Show who played it"))
        self.only.append((("meme",), c))
        lay.addWidget(c)
        c, cl = section_card("Widget layout", "Where each group sits in the Browser source.")
        for key, title in (("countersAt", "Counters"), ("goalsAt", "Goals"), ("latestAt", "Latest supporters")):
            cl.addWidget(field_row(title, "", self._choice(key)))
        cl.addWidget(field_row("Polls, predictions, giveaway and queue", "", self._choice("panelSide")))
        self.only.append((("widgets",), c))
        lay.addWidget(c)
        self.finish()
        self.load()

    # ---------- controls ----------
    def _choice(self, key):
        box = _combo(styles.CHOICES[key])
        box.currentIndexChanged.connect(lambda _: self._set(key, box.currentData()))
        self.boxes[key] = box
        return box

    def _field(self, key, title, note):
        return field_row(title, note, self._choice(key))

    def _slider(self, key, low, high):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(low, high)
        slider.valueChanged.connect(lambda v: self._set(key, v))
        self.sliders[key] = slider
        return slider

    def _check(self, key, text):
        box = QCheckBox(text)
        box.toggled.connect(lambda on: self._set(key, on))
        self.checks[key] = box
        return box

    def _setting_spin(self, key, low, high):
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(" s")
        spin.setValue(int(self.s.get(key)))
        spin.valueChanged.connect(lambda v: self.s.set(key, v))
        return spin

    # ---------- reading and saving ----------
    def design(self):
        return styles.design_for(self.s, self.kind)

    def _set(self, key, value):
        if not self._loading:
            self._apply({key: value})

    def _apply(self, values):
        styles.save_design(self.s, self.kind, dict(self.design(), **values))
        self.load()

    def _target_changed(self):
        self.kind = self.target.currentData()
        self.load()

    def match_everywhere(self):
        styles.match_all(self.s, self.kind)
        self.load()

    def load(self):
        self._loading = True
        d = self.design()
        for key, box in self.boxes.items():
            if key in d:
                box.setCurrentIndex(max(0, box.findData(d[key])))
        for key, slider in self.sliders.items():
            if key in d:
                slider.setValue(d[key])
        for key, box in self.checks.items():
            if key in d:
                box.setChecked(d[key])
        for box in (self.music_position, self.meme_position):
            if "position" in d:
                box.setCurrentIndex(max(0, box.findData(d["position"])))
        for key, b in self.colour_buttons.items():
            b.setStyleSheet("background:%s;border-radius:8px;" % d[key])
        for kinds, widget in self.only:
            widget.setVisible(self.kind in kinds)
        self.text_row.setVisible(self.kind != "widgets")
        self.test.setVisible(self.kind != "widgets")
        self._loading = False
        self.show_preview()

    def _pick_colour(self, key):
        colour = QColorDialog.getColor(QColor(self.design()[key]), self, "Choose a colour")
        if colour.isValid():
            self._apply({key: colour.name(), "useColors": True})

    def send_test(self):
        sample = styles.SAMPLES[self.kind]
        if self.kind == "chat":
            for line in sample:
                self.overlay.push("chat", dict(line))
        elif self.kind in ("music", "meme"):
            self.overlay.push(self.kind, dict(sample))

    # ---------- live preview: the real overlay page, as on the Alerts page ----------
    def showEvent(self, event):
        super().showEvent(event)
        if self.view is None and os.environ.get("QT_QPA_PLATFORM") != "offscreen" and self.overlay.port:
            QTimer.singleShot(0, self._make_preview)

    def _make_preview(self):
        if self.view is not None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self.view = QWebEngineView(self.preview_box)
        self.view.setMinimumHeight(220)
        self.view.loadFinished.connect(lambda ok: self.show_preview() if ok else None)
        self.preview_lay.addWidget(self.view, 0, 0)
        self.view.load(QUrl(self.overlay.url("preview")))

    def show_preview(self):
        if self.view is not None:
            self.view.page().runJavaScript("window.zdOverlay&&window.zdOverlay(%s,%s,%s)" % (
                json.dumps(self.kind), json.dumps(self.design()), json.dumps(styles.SAMPLES[self.kind])))
