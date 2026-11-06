"""Shared section cards, toggles, and form rows for settings pages."""
from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

FORM_SCROLL_AREAS = []


class Switch(QCheckBox):
    """Sliding on/off control; saves like a checkbox."""

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


class FormScrollArea(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        FORM_SCROLL_AREAS.append(self)


class SubPage(QWidget):
    """A main page: its sections sit behind a horizontal submenu, so nothing is buried in one long scroll."""

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 4, 0, 0)
        self._outer.setSpacing(10)
        self.subnav = QFrame()
        self.subnav.setObjectName("subnav")
        line = QHBoxLayout(self.subnav)
        line.setContentsMargins(6, 5, 6, 5)
        line.setSpacing(4)
        strip = QWidget()
        strip.setObjectName("subStrip")
        self._bar = QHBoxLayout(strip)
        self._bar.setContentsMargins(0, 0, 0, 0)
        self._bar.setSpacing(4)
        self._strip = QScrollArea()                   # on a small window the tabs slide, so none is ever cut off
        self._strip.setObjectName("subStrip")
        self._strip.setFrameShape(QFrame.NoFrame)
        self._strip.setWidgetResizable(True)
        self._strip.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._strip.setWidget(strip)
        self._arrows = []
        for text, step in (("\u2039", -180), ("\u203a", 180)):
            arrow = QPushButton(text)
            arrow.setObjectName("subArrow")
            arrow.setCursor(Qt.PointingHandCursor)
            arrow.setFixedWidth(26)
            arrow.setToolTip("More tabs")
            arrow.clicked.connect(lambda _=False, d=step: self._slide(d))
            arrow.hide()
            self._arrows.append(arrow)
        line.addWidget(self._arrows[0])
        line.addWidget(self._strip, 1)
        line.addWidget(self._arrows[1])
        self._strip.horizontalScrollBar().rangeChanged.connect(lambda _low, high: self._show_arrows(high > 0))
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.show_tab)
        self._tabs = QStackedWidget()
        self._layouts = []
        self._names = []
        self._outer.addWidget(self.subnav)
        self._outer.addWidget(self._tabs, 1)

    def add_header(self, widget):
        """A widget that stays above the submenu whichever tab is open."""
        self._outer.insertWidget(0, widget)

    def add_tab(self, title):
        scroll = FormScrollArea()
        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 12, 12)
        lay.setSpacing(14)
        scroll.setWidget(inner)
        button = QPushButton(title)
        button.setObjectName("subTab")
        button.setFixedHeight(34)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        self._group.addButton(button, len(self._names))
        self._bar.addWidget(button)
        self._tabs.addWidget(scroll)
        self._layouts.append(lay)
        self._names.append(title)
        return lay

    def finish(self):
        self._bar.addStretch(1)
        for lay in self._layouts:
            lay.addStretch(1)
        self.subnav.setVisible(len(self._names) > 1)
        self._strip.setFixedHeight(36)
        self.show_tab(0)

    def show_tab(self, which):
        index = self._names.index(which) if isinstance(which, str) else which
        self._tabs.setCurrentIndex(index)
        self._group.button(index).setChecked(True)
        self._strip.ensureWidgetVisible(self._group.button(index), 24, 0)

    def _slide(self, step):
        bar = self._strip.horizontalScrollBar()
        bar.setValue(bar.value() + step)

    def _show_arrows(self, on):
        for arrow in self._arrows:
            arrow.setVisible(on)

    def current_tab(self):
        return self._names[self._tabs.currentIndex()]

    def tab_names(self):
        return list(self._names)


class TwoColumnBoard(QWidget):
    """Two-column card grid on wide pages, one column when narrow."""

    def __init__(self, breakpoint=760):
        super().__init__()
        self._breakpoint = breakpoint
        self._wide = None
        self._pairs = []
        self._full = None
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(12)

    def set_cards(self, pairs, full=None):
        self._pairs = pairs
        self._full = full
        self._arrange(self.width() >= self._breakpoint)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange(self.width() >= self._breakpoint)

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
            if self._full is not None:
                self._grid.addWidget(self._full, len(self._pairs), 0, 1, 2)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 1)
        else:
            row = 0
            for left, right in self._pairs:
                self._grid.addWidget(left, row, 0)
                self._grid.addWidget(right, row + 1, 0)
                row += 2
            if self._full is not None:
                self._grid.addWidget(self._full, row, 0)
            self._grid.setColumnStretch(0, 1)


def section_card(title, description, object_name="tile"):
    card = QFrame()
    card.setObjectName(object_name)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(8)
    head = QLabel(title)
    head.setObjectName("pageTitle")
    note = QLabel(description)
    note.setObjectName("pageNote")
    note.setWordWrap(True)
    lay.addWidget(head)
    lay.addWidget(note)
    return card, lay


def field_row(title, note, widget):
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 4, 0, 0)
    lay.setSpacing(2)
    name = QLabel(title)
    name.setObjectName("settingName")
    detail = QLabel(note)
    detail.setObjectName("settingNote")
    detail.setWordWrap(True)
    if widget.maximumWidth() > 1000:
        widget.setMaximumWidth(420)
    lay.addWidget(name)
    lay.addWidget(detail)
    detail.setVisible(bool(note))
    lay.addWidget(widget)
    return wrap


def option_switch_row(title, note, switch):
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 6, 0, 6)
    text = QVBoxLayout()
    text.setSpacing(1)
    name = QLabel(title)
    name.setObjectName("settingName")
    name.setWordWrap(True)
    detail = QLabel(note)
    detail.setObjectName("settingNote")
    detail.setWordWrap(True)
    text.addWidget(name)
    text.addWidget(detail)
    detail.setVisible(bool(note))
    lay.addLayout(text, 1)
    lay.addWidget(switch, 0, Qt.AlignTop)
    return row


def bind_switch(settings, key, accent):
    switch = Switch()
    switch.set_accent(accent)
    switch.setChecked(bool(settings.get(key)))
    switch.toggled.connect(lambda on, k=key: settings.set(k, on))
    return switch


def meter_row(title, note, slider, fmt):
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 6, 0, 2)
    lay.setSpacing(4)
    top = QHBoxLayout()
    name = QLabel(title)
    name.setObjectName("settingName")
    value = QLabel(fmt(slider.value()))
    value.setObjectName("settingValue")
    top.addWidget(name)
    top.addStretch(1)
    top.addWidget(value)
    detail = QLabel(note)
    detail.setObjectName("settingNote")
    detail.setWordWrap(True)
    slider.valueChanged.connect(lambda v, f=fmt, lab=value: lab.setText(f(v)))
    lay.addLayout(top)
    lay.addWidget(detail)
    lay.addWidget(slider)
    return wrap


def hrow(*widgets):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for x in widgets:
        if x is None:
            continue
        stretch = 1 if x.__class__.__name__ in ("QLineEdit", "QComboBox", "QPlainTextEdit") else 0
        lay.addWidget(x, stretch)
    return w


# ---------------------------------------------------------------- shared pieces for the newer pages
from PySide6.QtGui import QGuiApplication          # noqa: E402
from PySide6.QtWidgets import QLineEdit, QPushButton   # noqa: E402

from .icons import platform_tile                       # noqa: E402


def platform_mark(key, size=36):
    mark = QLabel()
    mark.setAlignment(Qt.AlignCenter)
    mark.setFixedSize(size, size)
    mark.setStyleSheet("background: transparent;")
    mark.setPixmap(platform_tile(key, size))
    return mark


def make_badge(text="", kind="pill"):
    """Status chip. kind: pill (idle) | pillOn (good) | pillWait (working) | pillBad (problem)."""
    label = QLabel(text)
    label.setObjectName(kind)
    return label


def set_badge(label, text, kind):
    label.setText(text)
    label.setObjectName(kind)
    label.style().unpolish(label)
    label.style().polish(label)


def info_box(text, title=""):
    box = QFrame()
    box.setObjectName("infoBox")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(2)
    if title:
        head = QLabel(title)
        head.setObjectName("settingName")
        lay.addWidget(head)
    body = QLabel(text)
    body.setObjectName("settingNote")
    body.setWordWrap(True)
    body.setTextFormat(Qt.RichText)
    body.setOpenExternalLinks(True)
    lay.addWidget(body)
    box.body = body
    return box


def copy_row(text="", placeholder="", button="Copy"):
    """Read-only text with a Copy button. Returns (widget, line_edit)."""
    edit = QLineEdit(text)
    edit.setReadOnly(True)
    edit.setPlaceholderText(placeholder)
    btn = QPushButton(button)
    btn.setObjectName("quiet")
    btn.setCursor(Qt.PointingHandCursor)

    def copy():
        QGuiApplication.clipboard().setText(edit.text())
        btn.setText("Copied")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1400, lambda: btn.setText(button))

    btn.clicked.connect(copy)
    edit.copy_button = btn
    return hrow(edit, btn), edit


def step_row(number, title, detail):
    """A numbered instruction line: round number chip, bold title, softer detail text."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 4, 0, 4)
    lay.setSpacing(12)
    chip = QLabel(str(number))
    chip.setObjectName("stepNum")
    chip.setAlignment(Qt.AlignCenter)
    chip.setFixedSize(26, 26)
    text = QVBoxLayout()
    text.setSpacing(1)
    head = QLabel(title)
    head.setObjectName("settingName")
    head.setWordWrap(True)
    body = QLabel(detail)
    body.setObjectName("settingNote")
    body.setWordWrap(True)
    body.setTextFormat(Qt.RichText)
    text.addWidget(head)
    text.addWidget(body)
    lay.addWidget(chip, 0, Qt.AlignTop)
    lay.addLayout(text, 1)
    row.head, row.body = head, body
    return row


def status_row(badge, label=None):
    """A compact badge on the left with optional text beside it (the badge keeps its natural size)."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    lay.addWidget(badge, 0, Qt.AlignLeft | Qt.AlignVCenter)
    if label is not None:
        lay.addWidget(label, 1)
    else:
        lay.addStretch(1)
    return row
