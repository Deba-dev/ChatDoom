"""Alerts page: pick how every on-screen alert looks, moves and sounds, with a live preview. One design for all, or one per alert type."""
import json
import os
import random
import tempfile

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFileDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from . import alert_sounds
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
        self.player = None
        self.kind = ""                          # "" is the design every alert uses; otherwise one alert type
        self.tier = None                        # editing a "Tips by amount" step: its starting amount in rupees
        self._loading = False
        self.boxes = {}
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]

        head, hl = section_card("Design alerts", "Changes reach OBS within a second. Pick one alert type to give it its own design.")
        self.target = QComboBox()
        self._fill_targets()
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
        c, cl = section_card("Timing", "How long alerts stay and where they sit.")
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
        lay.addWidget(c)

        lay = self.add_tab("Sounds")
        c, cl = section_card("Alert sound", "%d built-in sounds, plus anything you import on the Music page. Press Play to hear one here." % len(alert_sounds.SOUNDS))
        cl.addWidget(option_switch_row("Play a sound with each alert", "Your voice still reads the alert aloud.", bind_switch(self.s, "ov_sound", accent)))
        self.main_sound = QComboBox()
        self.main_sound.currentIndexChanged.connect(lambda _: self.s.set("ov_sound_file", self.main_sound.currentData() or ""))
        cl.addWidget(field_row("Normal alert sound", "Used when nothing below is chosen.", hrow(self.main_sound, self._play_button(self.main_sound))))
        self.sound = QComboBox()
        self.sound.currentIndexChanged.connect(lambda _: self._set("sound", self.sound.currentData() or ""))
        cl.addWidget(field_row("Sound for this design", "Follows the Editing choice at the top of this page.", hrow(self.sound, self._play_button(self.sound))))
        self.sound_volume = QSlider(Qt.Horizontal)
        self.sound_volume.setRange(0, 100)
        self.sound_volume.valueChanged.connect(lambda v: self._set("soundVolume", v))
        cl.addWidget(field_row("Sound volume", "How loud alert sounds play in OBS.", self.sound_volume))
        refresh = QPushButton("Refresh sounds")
        refresh.setObjectName(BUTTON)
        refresh.clicked.connect(self.reload_sounds)
        cl.addWidget(hrow(refresh))
        lay.addWidget(c)
        c, cl = section_card("A sound for each alert", "Give each alert type its own sound, or pick a pack to fill them all at once.")
        packs = []
        for name, values in alert_sounds.PACKS:
            b = QPushButton(name)
            b.setObjectName(BUTTON)
            b.clicked.connect(lambda _=False, v=values: self.use_sound_pack(v))
            packs.append(b)
        clear_all = QPushButton("Clear all")
        clear_all.setObjectName(BUTTON)
        clear_all.clicked.connect(lambda: self.use_sound_pack({}))
        cl.addWidget(hrow(*packs, clear_all))
        self.type_boxes = {}
        for title, kind in styles.ALERT_TYPES:
            box = QComboBox()
            box.currentIndexChanged.connect(lambda _, k=kind: self._set_type_sound(k))
            self.type_boxes[kind] = box
            cl.addWidget(field_row(title, "", hrow(box, self._play_button(box))))
        lay.addWidget(c)

        lay = self.add_tab("Tips by amount")
        c, cl = section_card(
            "A bigger tip gets a bigger alert",
            "Give tips from an amount upwards their own design, sound and time on screen, up to %d steps. A tip uses the "
            "highest step it reaches; smaller tips use the normal Tips design. Works for rupee tips from your UPI tip page."
            % styles.MAX_TIERS)
        self.tier_rows = QVBoxLayout()
        self.tier_rows.setSpacing(6)
        holder = QWidget()
        holder.setLayout(self.tier_rows)
        cl.addWidget(holder)
        self.add_tier_button = QPushButton("Add a step")
        self.add_tier_button.setObjectName("primary")
        self.add_tier_button.clicked.connect(self.add_tier)
        self.tier_note = QLabel("")
        self.tier_note.setObjectName("sub")
        self.tier_note.setWordWrap(True)
        cl.addWidget(hrow(self.add_tier_button, self.tier_note))
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
        self._fill_tier_rows()
        self.load()

    # ---------- reading and saving ----------
    def _choice(self, key):
        box = _combo(styles.CHOICES[key])
        box.currentIndexChanged.connect(lambda _: self._set(key, box.currentData()))
        self.boxes[key] = box
        return box

    def _tier_index(self):
        return next((i for i, t in enumerate(styles.tip_tiers(self.s)) if t["from"] == self.tier), None)

    def design(self):
        if self.tier is not None and self._tier_index() is not None:
            return styles.tier_design(self.s, self._tier_index())
        return styles.design_for(self.s, self.kind) if self.kind else styles.main_design(self.s)

    def tool_kind(self):
        return "alert"

    def reset_design(self):
        if self.tier is not None:
            styles.set_tier(self.s, self._tier_index(), design={})
        elif self.kind:
            custom = styles.custom_designs(self.s)
            custom.pop(self.kind, None)
            self.s.set("ov_alert_custom", custom)
        else:
            self.s.set("ov_alert_design", {})
            self.s.set("ov_alert_style", "neon")
        self.load()

    def _has_own(self):
        return self.tier is not None or self.kind in styles.custom_designs(self.s)

    def _save(self, design):
        if self.tier is not None:
            styles.set_tier(self.s, self._tier_index(), design=design)
            self._fill_tier_rows()
        elif self.kind:
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
        data = self.target.currentData() or ""
        if data.startswith("tier:"):
            self.kind, self.tier = "tip", int(data[5:])
        else:
            self.kind, self.tier = data, None
        self.load()

    # ---------- tips by amount ----------
    def _fill_targets(self, keep=None):
        """The Editing list: all alerts, each alert type, and each Tips step right under Tips."""
        keep = keep if keep is not None else (self.target.currentData() or "")
        self.target.blockSignals(True)
        self.target.clear()
        self.target.addItem("All alerts", "")
        for label, value in styles.ALERT_TYPES:
            self.target.addItem(label, value)
            if value == "tip":
                for t in styles.tip_tiers(self.s):
                    self.target.addItem("   Tips ₹%s and up" % format(t["from"], ","), "tier:%d" % t["from"])
        found = self.target.findData(keep)
        self.target.setCurrentIndex(max(0, found))
        self.target.blockSignals(False)
        if found < 0 and keep:
            self._target_changed()

    def _fill_tier_rows(self):
        while self.tier_rows.count():
            item = self.tier_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        tiers = styles.tip_tiers(self.s)
        if not tiers:
            empty = QLabel("No steps yet: every tip uses the Tips design.")
            empty.setObjectName("settingNote")
            self.tier_rows.addWidget(empty)
        looks = dict((v, k) for k, v in styles.LOOKS)
        for i, t in enumerate(tiers):
            amount = QSpinBox()
            amount.setRange(1, styles.TIER_MAX_FROM)
            amount.setPrefix("₹ ")
            amount.setGroupSeparatorShown(True)
            amount.setValue(t["from"])
            amount.setFixedWidth(150)
            amount.editingFinished.connect(lambda i=i, box=amount: self.move_tier(i, box.value()))
            upto = tiers[i + 1]["from"] - 1 if i + 1 < len(tiers) else None
            span = QLabel(("up to ₹%s" % format(upto, ",")) if upto else "and up")
            span.setObjectName("settingNote")
            d = styles.tier_design(self.s, i)
            what = QLabel("%s, %d%% size" % (looks.get(d["look"], d["look"]), d["size"]))
            what.setObjectName("settingNote")
            edit = QPushButton("Design it")
            edit.setObjectName(BUTTON)
            edit.clicked.connect(lambda _=False, v=t["from"]: self.edit_tier(v))
            test = QPushButton("Test")
            test.setObjectName(BUTTON)
            test.clicked.connect(lambda _=False, v=t["from"]: self.overlay.push("alert", self.tier_sample(v)))
            remove = QPushButton("Remove")
            remove.setObjectName(BUTTON)
            remove.clicked.connect(lambda _=False, i=i: self.remove_tier(i))
            self.tier_rows.addWidget(hrow(amount, span, what, edit, test, remove))
        self.add_tier_button.setEnabled(len(tiers) < styles.MAX_TIERS)

    def _tiers_changed(self, keep=None):
        self._fill_tier_rows()
        self._fill_targets(keep)
        self.load()

    def add_tier(self):
        index = styles.add_tier(self.s)
        if index is None:
            self.tier_note.setText("You have the most steps (%d)." % styles.MAX_TIERS)
            return
        start = styles.tip_tiers(self.s)[index]["from"]
        self.tier_note.setText("Added tips from ₹%s. Change the amount if you like, then Design it." % format(start, ","))
        self._tiers_changed()

    def move_tier(self, index, start):
        tiers = styles.tip_tiers(self.s)
        if index >= len(tiers) or tiers[index]["from"] == start:
            return
        old = tiers[index]["from"]
        if styles.set_tier(self.s, index, start=start) is None:
            self.tier_note.setText("Another step already starts at ₹%s." % format(start, ","))
            self._fill_tier_rows()
            return
        self.tier_note.setText("")
        keep = None
        if self.tier == old:
            self.tier, keep = start, "tier:%d" % start
        self._tiers_changed(keep)

    def remove_tier(self, index):
        styles.remove_tier(self.s, index)
        self.tier_note.setText("")
        self._tiers_changed()

    def edit_tier(self, start):
        self.target.setCurrentIndex(max(0, self.target.findData("tier:%d" % start)))
        self.tier_note.setText("Now editing tips from ₹%s: use the Packs, Style, Text, Media and Sounds tabs." % format(start, ","))

    def tier_sample(self, start):
        return dict(styles.SAMPLES["tip"], amount="₹" + format(start, ","), value=float(start))

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
        self.own.setVisible(bool(self.kind) and self.tier is None)
        self.own.setChecked(self._has_own())
        for key, box in self.boxes.items():
            box.setCurrentIndex(max(0, box.findData(d[key])))
        self.size.setValue(d["size"])
        self.sound_volume.setValue(d["soundVolume"])
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
        boxes = [(self.sound, "Same as the normal sound", True), (self.main_sound, "Simple chime", False)]
        boxes += [(box, "Same as the design", True) for box in self.type_boxes.values()]
        for box, empty, can_silence in boxes:
            box.blockSignals(True)
            box.clear()
            box.addItem(empty, "")
            if can_silence:
                box.addItem("No sound", alert_sounds.SILENT)
                box.addItem("Random built-in sound", alert_sounds.RANDOM)
            for name, value in alert_sounds.choices():
                box.addItem(name, value)
            for item in items:
                box.addItem(item["title"], item["path"])
            box.blockSignals(False)
        self.main_sound.setCurrentIndex(max(0, self.main_sound.findData(self.s.get("ov_sound_file") or "")))
        self.sound.setCurrentIndex(max(0, self.sound.findData(self.design()["sound"])))
        self._load_type_sounds()
        self._loading = keep

    def _load_type_sounds(self):
        saved = styles.type_sounds(self.s)
        for kind, box in self.type_boxes.items():
            box.blockSignals(True)
            box.setCurrentIndex(max(0, box.findData(saved.get(kind, ""))))
            box.blockSignals(False)

    def _set_type_sound(self, kind):
        saved = styles.type_sounds(self.s)
        value = self.type_boxes[kind].currentData() or ""
        if value:
            saved[kind] = value
        else:
            saved.pop(kind, None)
        self.s.set("ov_type_sounds", saved)

    def use_sound_pack(self, values):
        self.s.set("ov_type_sounds", {kind: alert_sounds.PREFIX + key for kind, key in values.items()})
        self._load_type_sounds()

    def _play_button(self, box):
        b = QPushButton("Play")
        b.setObjectName(BUTTON)
        b.clicked.connect(lambda: self.play_sound(box.currentData() or ""))
        return b

    def play_sound(self, value):
        """Plays a sound here in the app, so it can be judged without going live."""
        if value == alert_sounds.SILENT or not value:
            value = alert_sounds.choices()[0][1] if not value else ""
        if value == alert_sounds.RANDOM:
            value = random.choice(alert_sounds.choices())[1]
        if not value:
            return None
        if alert_sounds.is_builtin(value):
            path = os.path.join(tempfile.gettempdir(), "chatdoom-%s.wav" % value[len(alert_sounds.PREFIX):])
            with open(path, "wb") as f:
                f.write(alert_sounds.wav_bytes(value[len(alert_sounds.PREFIX):]))
        else:
            path = value
        if self.player is None:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self.player, self.player_out = QMediaPlayer(self), QAudioOutput(self)
            self.player.setAudioOutput(self.player_out)
        self.player_out.setVolume(self.design()["soundVolume"] / 100)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        return path

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
        if self.tier is not None:
            return self.tier_sample(self.tier)
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
