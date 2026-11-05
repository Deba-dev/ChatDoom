"""Customize look window: your own colours, a built-in picture, or your own picture behind the pages."""
import os
import time
import shutil

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QColorDialog, QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QLabel, QPushButton, QSlider,
                               QToolButton, QVBoxLayout)

from .settings import data_dir
from .theme import CUSTOM_DEFAULT
from .ui_kit import field_row, hrow, section_card
from .visuals import BUILT_IN_BACKGROUNDS, background_path

MAX_IMAGE_BYTES = 25 * 1024 * 1024
COLOUR_ROWS = (("a1", "Main colour", "Buttons, highlights and switches."),
               ("a2", "Second colour", "Gradients and small accents."),
               ("bg", "Background colour", "Kept dark so text stays easy to read."))


def import_image(source):
    """Copies a picture into CHATDOOM's own folder. Returns (setting value, '') or ('', reason)."""
    try:
        if os.path.getsize(source) > MAX_IMAGE_BYTES:
            return "", "That picture is over 25 MB. Choose a smaller one."
    except OSError:
        return "", "That picture could not be opened."
    if QImage(source).isNull():
        return "", "That file is not a picture CHATDOOM can read."
    folder = os.path.join(data_dir(), "Backgrounds")
    os.makedirs(folder, exist_ok=True)
    name = "custom-%d%s" % (int(time.time() * 1000), os.path.splitext(source)[1].lower())
    try:
        shutil.copyfile(source, os.path.join(folder, name))
    except OSError:
        return "", "That picture could not be copied."
    for old in os.listdir(folder):                       # only the newest custom picture is kept
        if old != name:
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass
    return "custom:" + name, ""


class AppearanceDialog(QDialog):
    def __init__(self, parent, settings, on_colours, on_image, on_dim):
        super().__init__(parent)
        self.s, self.on_colours, self.on_image, self.on_dim = settings, on_colours, on_image, on_dim
        self.setWindowTitle("Customize look")
        self.setMinimumWidth(560)
        self.colours = {**CUSTOM_DEFAULT, **(self.s.get("theme_custom") or {})}
        self.swatches = {}
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        card, cl = section_card("Colours", "Pick your own colours. CHATDOOM switches to the Custom theme.")
        for key, title, note in COLOUR_ROWS:
            swatch = QPushButton()
            swatch.setFixedSize(84, 30)
            swatch.setCursor(Qt.PointingHandCursor)
            swatch.setAccessibleName(title)
            swatch.clicked.connect(lambda _=False, k=key: self.pick(k))
            self.swatches[key] = swatch
            cl.addWidget(field_row(title, note, swatch))
        reset = QPushButton("Reset colours")
        reset.setObjectName("quiet")
        reset.clicked.connect(self.reset)
        cl.addWidget(hrow(reset))
        lay.addWidget(card)

        card, cl = section_card("Background picture", "Choose one of ours or use your own picture.")
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (title, key) in enumerate(BUILT_IN_BACKGROUNDS):
            button = QToolButton()
            button.setText(title)
            button.setToolTip(title)
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setIcon(QIcon(QPixmap(background_path("builtin:" + key)).scaled(150, 84, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)))
            button.setIconSize(QSize(150, 84))
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.on_image("builtin:" + k))
            grid.addWidget(button, i // 3, i % 3)
        cl.addLayout(grid)
        own = QPushButton("Use my own picture")
        own.setObjectName("primary")
        own.clicked.connect(self.choose)
        cl.addWidget(hrow(own))
        self.note = QLabel("")
        self.note.setObjectName("settingNote")
        self.note.setWordWrap(True)
        cl.addWidget(self.note)
        self.dim = QSlider(Qt.Horizontal)
        self.dim.setRange(20, 85)
        self.dim.setValue(int(self.s.get("bg_dim")))
        self.dim.setFixedWidth(180)
        self.dim.valueChanged.connect(self.on_dim)
        cl.addWidget(field_row("Darken picture", "More darkening keeps text easier to read.", self.dim))
        lay.addWidget(card)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        lay.addWidget(buttons)
        self.paint_swatches()

    def paint_swatches(self):
        for key, swatch in self.swatches.items():
            swatch.setStyleSheet("background: %s; border: 1px solid rgba(255,255,255,0.35); border-radius: 8px;" % self.colours[key])
            swatch.setToolTip(self.colours[key])

    def pick(self, key):
        colour = QColorDialog.getColor(QColor(self.colours[key]), self, "Choose a colour")
        if colour.isValid():
            self.colours[key] = colour.name()
            self.paint_swatches()
            self.on_colours(dict(self.colours))

    def reset(self):
        self.colours = dict(CUSTOM_DEFAULT)
        self.paint_swatches()
        self.on_colours(dict(self.colours))

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a background picture", os.path.expanduser("~/Pictures"),
                                              "Pictures (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        value, problem = import_image(path)
        self.note.setText(problem)
        if value:
            self.on_image(value)
