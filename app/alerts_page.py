"""Alerts page: pick how every on-screen alert looks, moves and sounds, with a live preview. One design for all, or one per alert type."""
import json
import os
import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFileDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox,
                               QWidget)

from . import alert_styles as styles
from .commands import MEME_IMAGES, import_file
from .design_tools import DesignTools
from .music import scan
from .settings import data_dir
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import SubPage, bind_switch, field_row, hrow, info_box, option_switch_row, section_card

TEMPLATE_HINT = "Leave empty for the normal wording. {name} is the viewer, {amount} is the amount or tier."
BUTTON = "quiet"


def _combo(options):
    box = QComboBox()
    for label, value in options:
        box.addItem(label, value)
    return box


class AlertsPage(DesignTools, SubPage):
    def __init__(self, settings, overlay):
        super().__init__()
        self.s, self.overlay = settings, overlay
        self.view = None
        self.kind = ""                          # "" is the design every alert uses; otherwise one alert type
        self._loading = False
        self.boxes = {}
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]

        head, hl = section_card("Design alerts", "Changes reach OBS within a second. Pick one alert type to give it its own design.")
        self.target = _combo((("All alerts", ""),) + styles.ALERT_TYPES)
        self.target.currentIndexChanged.connect(self._target_changed)
        self.own = QCheckBox("This alert has its own design")
        self.own.toggled.connect(self._own_toggled)
        self.own.hide()
        test = QPushButton("Send test to OBS")
        test.setObjectName("primary")
        test.clicked.connect(self.send_test)
        test_all = QPushButton("Test every alert")
        test_all.setObjectName(BUTTON)
        test_all.clicked.connect(self.test_all)
        hl.addWidget(hrow(QLabel("Editing"), self.target, self.own, test, test_all))
        self.preview_box = QWidget()
        self.preview_box.setMinimumHeight(210)
        self.preview_lay = QGridLayout(self.preview_box)
        self.preview_lay.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.preview_box)
        self.add_header(head)

        lay = self.add_tab("Packs")
        c, cl = section_card("Ready-made packs", "One click sets the look, animations, text effect, particles and font together. Change anything afterwards.")
        grid = QGridLayout()
        grid.setSpacing(8)
        self.pack_buttons = []
        for i, (name, values) in enumerate(styles.PACKS):
            b = QPushButton(name)
            b.setObjectName(BUTTON)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=values: self._apply(v))
            grid.addWidget(b, i // 3, i % 3)
            self.pack_buttons.append(b)
        cl.addLayout(grid)
        lucky = QPushButton("Surprise me")
        lucky.setObjectName("primary")
        lucky.clicked.connect(self.surprise)
        cl.addWidget(hrow(lucky))
        lay.addWidget(c)

        lay = self.add_tab("Style")
        c, cl = section_card("Look and motion", "%d looks, %d ways in, %d ways out, %d idle motions and %d particle effects." % (
            len(styles.LOOKS), len(styles.ENTERS), len(styles.EXITS), len(styles.IDLES), len(styles.EFFECTS)))
        for key, title, note in (("look", "Look", "The shape and frame of the alert."), ("enter", "Comes in with", "How the alert appears."),
                                 ("idle", "While on screen", "The motion while it stays."), ("exit", "Leaves with", "How the alert goes away."),
                                 ("effect", "Particles", "What flies around it.")):
            cl.addWidget(field_row(title, note, self._choice(key)))
        lay.addWidget(c)

        lay = self.add_tab("Text")
        c, cl = section_card("Fonts and wording", "Hindi-ready fonts are marked. Fonts other than Poppins load from Google Fonts, so OBS needs the internet.")
        cl.addWidget(field_row("Font", "Used for all the text in the alert.", self._choice("font")))
        cl.addWidget(field_row("Name animation", "How the viewer's name moves.", self._choice("text")))
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(60, 160)
        self.size.valueChanged.connect(lambda v: self._set("size", v))
        cl.addWidget(field_row("Size", "60% to 160% of the normal size.", self.size))
        self.template = QLineEdit()
        self.template.setMaxLength(160)
        self.template.setPlaceholderText("{name} just joined the squad!")
        self.template.editingFinished.connect(lambda: self._set("template", self.template.text().strip()))
        cl.addWidget(field_row("Your own wording", TEMPLATE_HINT, self.template))
        cl.addWidget(option_switch_row("Show the viewer's message in the alert", "Include the paid or highlighted message text on screen.",
                                       bind_switch(self.s, "ov_show_message", accent)))
        lay.addWidget(c)
        c, cl = section_card("Colours", "Off follows your CHATDOOM theme colours.")
        self.use_colors = QCheckBox("Use my own colours")
        self.use_colors.toggled.connect(lambda on: self._set("useColors", on))
        self.colour_buttons = {}
        for key in ("c1", "c2", "c3"):
            b = QPushButton()
            b.setFixedSize(58, 30)
            b.clicked.connect(lambda _=False, k=key: self._pick_colour(k))
            self.colour_buttons[key] = b
        cl.addWidget(hrow(self.use_colors, *self.colour_buttons.values()))
        lay.addWidget(c)

        lay = self.add_tab("Media")
        c, cl = section_card("Picture or GIF", "Shown in the alert. Files are copied into your Memes folder.")
        self.image_label = QLabel()
        self.image_label.setObjectName("settingNote")
        pick = QPushButton("Choose picture")
        pick.setObjectName(BUTTON)
        pick.clicked.connect(self.pick_image)
        clear = QPushButton("Remove")
        clear.setObjectName(BUTTON)
        clear.clicked.connect(lambda: self._set("image", ""))
        cl.addWidget(hrow(pick, clear, self.image_label))
        cl.addWidget(field_row("Picture position", "", self._choice("layout")))
        lay.addWidget(c)
        c, cl = section_card("Sound and timing", "Import sounds on the Music page, then choose one here.")
        self.sound = QComboBox()
        self.sound.currentIndexChanged.connect(lambda _: self._set("sound", self.sound.currentData() or ""))
        refresh = QPushButton("Refresh sounds")
        refresh.setObjectName(BUTTON)
        refresh.clicked.connect(self.reload_sounds)
        cl.addWidget(field_row("Sound for this design", "Empty uses the sound below.", self.sound))
        cl.addWidget(hrow(refresh))
        self.seconds = QSpinBox()
        self.seconds.setRange(0, 60)
        self.seconds.setSpecialValueText("Use the normal time")
        self.seconds.setSuffix(" s")
        self.seconds.valueChanged.connect(lambda v: self._set("seconds", v))
        cl.addWidget(field_row("Stays on screen", "Long messages stay a little longer.", self.seconds))
        cl.addWidget(field_row("Place on screen", "Where it shows in the Browser source.", self._choice("position")))
        normal = QSpinBox()
        normal.setRange(3, 30)
        normal.setSuffix(" s")
        normal.setValue(int(self.s.get("ov_seconds")))
        normal.valueChanged.connect(lambda v: self.s.set("ov_seconds", v))
        cl.addWidget(field_row("Normal time on screen", "Used when a design does not set its own.", normal))
        cl.addWidget(option_switch_row("Play a short chime with each alert", "Your voice still reads the alert aloud.", bind_switch(self.s, "ov_sound", accent)))
        self.main_sound = QComboBox()
        self.main_sound.currentIndexChanged.connect(lambda _: self.s.set("ov_sound_file", self.main_sound.currentData() or ""))
        cl.addWidget(field_row("Normal alert sound", "Replaces the built-in chime.", self.main_sound))
        lay.addWidget(c)

        lay = self.add_tab("Alert types")
        c, cl = section_card("Choose which alerts show",
                             "YouTube subscriber alerts are limited to publicly visible subscriptions. Twitch alerts use EventSub and need the additional account permissions.")
        for title, note, key in (("Payment tips", "Show payment webhook alerts.", "ov_alert_tips"),
                                 ("Super Chats / Bits", "Show paid messages from YouTube or Twitch chat.", "ov_alert_superchats"),
                                 ("Membership alerts", "Show YouTube membership events when the chat source provides them.", "ov_alert_memberships"),
                                 ("YouTube subscriber alerts", "Poll public subscriber activity every five minutes while signed in.", "ov_alert_youtube_subscribers"),
                                 ("Twitch followers", "Receive follow alerts from Twitch EventSub.", "ov_alert_follows"),
                                 ("Twitch subscriptions", "Receive new, resubscription, and gift alerts from Twitch EventSub.", "ov_alert_subscriptions"),
                                 ("Twitch raids", "Receive raid alerts from Twitch EventSub.", "ov_alert_raids")):
            cl.addWidget(option_switch_row(title, note, bind_switch(self.s, key, accent)))
        lay.addWidget(c)
        lay.addWidget(info_box("Add <b>/alert</b> to OBS as a Browser source. Its address is on the OBS overlays page.", "Show it on stream"))
        self.add_design_tools(("alert",))
        self.finish()
        self.reload_sounds()
        self.load()

    # ---------- reading and saving ----------
    def _choice(self, key):
        box = _combo(styles.CHOICES[key])
        box.currentIndexChanged.connect(lambda _: self._set(key, box.currentData()))
        self.boxes[key] = box
        return box

    def design(self):
        return styles.design_for(self.s, self.kind) if self.kind else styles.main_design(self.s)

    def tool_kind(self):
        return "alert"

    def reset_design(self):
        if self.kind:
            custom = styles.custom_designs(self.s)
            custom.pop(self.kind, None)
            self.s.set("ov_alert_custom", custom)
        else:
            self.s.set("ov_alert_design", {})
            self.s.set("ov_alert_style", "neon")
        self.load()

    def _has_own(self):
        return self.kind in styles.custom_designs(self.s)

    def _save(self, design):
        if self.kind:
            custom = styles.custom_designs(self.s)
            custom[self.kind] = design
            self.s.set("ov_alert_custom", custom)
        else:
            self.s.set("ov_alert_design", design)
            self.s.set("ov_alert_style", design["look"])

    def _set(self, key, value):
        if not self._loading:
            self._apply({key: value})

    def _apply(self, values):
        design = self.design()
        design.update(values)
        if self.kind and not self._has_own():       # changing one alert type is what gives it its own design
            self._loading = True
            self.own.setChecked(True)
            self._loading = False
        self._save(styles.clean(design))
        self.load()

    def surprise(self):
        pick = {key: random.choice(options)[1] for key, options in styles.CHOICES.items() if key not in ("position", "layout")}
        self._apply(pick)

    def _target_changed(self):
        self.kind = self.target.currentData() or ""
        self.load()

    def _own_toggled(self, on):
        if self._loading or not self.kind:
            return
        custom = styles.custom_designs(self.s)
        if on:
            custom[self.kind] = styles.main_design(self.s)
        else:
            custom.pop(self.kind, None)
        self.s.set("ov_alert_custom", custom)
        self.load()

    def load(self):
        self._loading = True
        d = self.design()
        self.own.setVisible(bool(self.kind))
        self.own.setChecked(self._has_own())
        for key, box in self.boxes.items():
            box.setCurrentIndex(max(0, box.findData(d[key])))
        self.size.setValue(d["size"])
        self.seconds.setValue(d["seconds"])
        if self.template.text() != d["template"]:
            self.template.setText(d["template"])
        self.use_colors.setChecked(d["useColors"])
        for key, b in self.colour_buttons.items():
            b.setStyleSheet("background:%s;border-radius:8px;" % d[key])
        self.image_label.setText(os.path.basename(d["image"]) or "No picture")
        self.sound.setCurrentIndex(max(0, self.sound.findData(d["sound"])))
        self.load_design_tools(d)
        self._loading = False
        self.show_preview()

    def reload_sounds(self):
        keep = self._loading
        self._loading = True
        items = scan(os.path.join(data_dir(), "Soundboard"))
        for box, empty in ((self.sound, "Same as the normal sound"), (self.main_sound, "Built-in chime")):
            box.blockSignals(True)
            box.clear()
            box.addItem(empty, "")
            for item in items:
                box.addItem(item["title"], item["path"])
            box.blockSignals(False)
        self.main_sound.setCurrentIndex(max(0, self.main_sound.findData(self.s.get("ov_sound_file") or "")))
        self.sound.setCurrentIndex(max(0, self.sound.findData(self.design()["sound"])))
        self._loading = keep

    def _pick_colour(self, key):
        colour = QColorDialog.getColor(QColor(self.design()[key]), self, "Choose a colour")
        if colour.isValid():
            self._apply({key: colour.name(), "useColors": True})

    def pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture or GIF", os.path.expanduser("~"),
                                              "Pictures (%s)" % " ".join("*" + e for e in MEME_IMAGES))
        if path:
            self._set("image", import_file(path, os.path.join(data_dir(), "Memes")))

    # ---------- testing ----------
    def sample(self):
        return dict(styles.SAMPLES[self.kind or "tip"])

    def send_test(self):
        self.overlay.push("alert", self.sample())

    def test_all(self):
        for kind in styles.TYPE_KEYS:
            self.overlay.push("alert", dict(styles.SAMPLES[kind]))

    # ---------- live preview: the real overlay page, so what you see is what OBS shows ----------
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
        self.view.setMinimumHeight(210)
        self.view.loadFinished.connect(lambda ok: self.show_preview() if ok else None)
        self.preview_lay.addWidget(self.view, 0, 0)
        self.view.load(QUrl(self.overlay.url("preview")))

    def show_preview(self):
        if self.view is None:
            return
        data = styles.for_overlay(self.design(), os.path.join(data_dir(), "Soundboard"), os.path.join(data_dir(), "Memes"))
        data["position"] = "mid-center"            # the small preview always shows the alert in the middle
        self.view.page().runJavaScript("window.zdPreview&&window.zdPreview(%s,%s)" % (json.dumps(data), json.dumps(self.sample())))
