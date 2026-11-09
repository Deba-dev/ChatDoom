"""Colour themes, the stylesheet, and the floating hover effect for buttons."""
from string import Template

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QParallelAnimationGroup, QPropertyAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

THEMES = {
    "Toxic Neon":  dict(bg="#0b0b0d", bg2="#17171c", text="#f4f4f6", mute="#9a9aa8", a1="#c6ff3d", a2="#ff3d8b", a3="#3dd6ff"),
    "Neon Violet": dict(bg="#05031a", bg2="#140a3a", text="#f6f4ff", mute="#aaa6cc", a1="#7c3aed", a2="#c026d3", a3="#3b82f6"),
    "Sunset":      dict(bg="#1a1216", bg2="#24181d", text="#fff1f4", mute="#c9a3b4", a1="#ff7a45", a2="#ff3d81", a3="#ffd166"),
    "Ocean":       dict(bg="#0d1620", bg2="#12202c", text="#eaf6ff", mute="#8db3cf", a1="#00b8ff", a2="#4f7cff", a3="#2dd4bf"),
    "Matcha":      dict(bg="#101814", bg2="#16201a", text="#effff5", mute="#93bfa5", a1="#34d399", a2="#a3e635", a3="#22d3ee"),
}
DEFAULT_THEME = "Toxic Neon"
CUSTOM_THEME = "Custom"
CUSTOM_DEFAULT = {"a1": "#7c3aed", "a2": "#c026d3", "bg": "#05031a"}


def custom_theme(colours):
    """A full theme from three picked colours. The background stays dark because the app's text and glows are light."""
    picked = {**CUSTOM_DEFAULT, **(colours or {})}
    a1, a2, bg = (QColor(picked[k]) for k in ("a1", "a2", "bg"))
    a1, a2 = (c if c.isValid() else QColor(CUSTOM_DEFAULT["a1"]) for c in (a1, a2))
    if not bg.isValid():
        bg = QColor(CUSTOM_DEFAULT["bg"])
    hue, sat, light, _ = bg.getHslF()
    bg = QColor.fromHslF(max(hue, 0), sat, min(light, 0.16))
    bg2 = QColor.fromHslF(max(hue, 0), sat, min(light, 0.16) + 0.06)
    a3 = QColor.fromHsvF(((max(a1.hueF(), 0) + 0.12) % 1.0), max(a1.saturationF(), 0.5), max(a1.valueF(), 0.7))
    return dict(bg=bg.name(), bg2=bg2.name(), text="#f6f4ff", mute="#aaa6cc", a1=a1.name(), a2=a2.name(), a3=a3.name())


def set_custom_theme(colours):
    THEMES[CUSTOM_THEME] = custom_theme(colours)


set_custom_theme(None)

QSS = Template("""
* { font-family: "Poppins", "Segoe UI", "Noto Sans Devanagari", sans-serif; font-size: 13px; color: $text; }
QWidget#root { background: $bg; }
QDialog { background: $bg2; }
QWidget#canvas { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $bg, stop:0.72 $bg, stop:1 $bg2); }
QWidget#page, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QFrame#side { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba($c2,0.10), stop:0.5 $bg, stop:1 rgba($c1,0.06));
    border-right: 1px solid rgba(255,255,255,0.07); }
QLabel#brandMark { background: $a1; color: $on; font-size: 12px; font-weight: 700; border-radius: 8px; padding: 6px 7px; }
QLabel#logo { font-size: 21px; font-weight: 800; letter-spacing: 0.5px; }
QLabel#tagline { color: $mute; font-size: 11px; }
QLabel#group { color: $mute; font-size: 10px; font-weight: 700; padding: 8px 16px 3px 16px; }
QLabel#title { font-size: 32px; font-weight: 800; }
QFrame#titleBar { border-radius: 3px; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $hi, stop:1 $a2); }
QFrame#titleLine { border-radius: 1px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $a2, stop:1 transparent); }
QLabel#sub { color: $mute; font-size: 13px; }
QLabel#hint, QLabel#field { color: $mute; font-size: 12px; }
QLabel#pageTitle, QLabel#voiceTitle { font-size: 17px; font-weight: 650; }
QLabel#settingName, QLabel#voiceName { font-size: 14px; font-weight: 600; }
QLabel#pageNote, QLabel#settingNote, QLabel#voiceNote { color: $mute; font-size: 13px; }
QLabel#settingValue, QLabel#voiceValue { font-size: 14px; font-weight: 650; }
QLabel#statNum { font-size: 27px; font-weight: 800; color: $a1; background: transparent; }
QLabel#statCap { color: $text; font-size: 13px; font-weight: 500; background: transparent; }
QFrame#stat { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba($c1,0.14), stop:1 rgba($c2,0.06));
    border: 1px solid rgba($c1,0.30); border-radius: 24px; }
QFrame#aside, QFrame#hero { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba($c1,0.22), stop:1 rgba($c2,0.14));
    border: 1px solid rgba($c2,0.45); border-radius: 26px; }
QLabel#heroTitle { font-size: 19px; font-weight: 700; background: transparent; }
QLabel#heroText { color: $text; font-size: 13px; background: transparent; }
QPushButton#nav { text-align: left; padding: 6px 14px; border: none; margin: 1px 12px; border-radius: 12px;
    background: transparent; color: $text; font-size: 13px; font-weight: 500; }
QPushButton#nav:hover { background: rgba($c1,0.20); color: #ffffff; }
QPushButton#nav:checked { color: $on; font-weight: 700; background: transparent; }
QFrame#navGlow { border-radius: 16px; border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $hi, stop:1 $lo); }
QFrame#toast { background: rgba(14,16,26,0.94); border: 1px solid rgba(255,255,255,0.12); border-radius: 12px; }
QLabel#toastDot { color: $a1; font-size: 11px; }
QLabel#toastDot[kind="good"] { color: #34d399; }
QLabel#toastDot[kind="warn"] { color: #fbbf24; }
QLabel#toastDot[kind="gold"] { color: #ffd24d; }
QComboBox#sideCombo { padding: 5px 8px; font-size: 12px; min-height: 18px; }
QFrame#card, QFrame#tile { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(255,255,255,0.045), stop:1 rgba($c2,0.05));
    border: 1px solid rgba(255,255,255,0.09); border-radius: 24px; }
QFrame#tile:hover, QFrame#card:hover, QFrame#stat:hover { border: 1px solid $a1; }
QListWidget { background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 4px; outline: 0; }
QListWidget::item { padding: 7px 10px; border-radius: 7px; }
QListWidget::item:hover { background: rgba(255,255,255,0.06); }
QListWidget::item:selected { background: $a1; color: $on; }
QFrame#infoBox { background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.05); border-left: 3px solid $a1; border-radius: 10px; }
QLabel#stepNum { background: $a1; color: $on; border-radius: 13px; font-weight: 700; font-size: 12px; }
QPushButton#danger { background: rgba(244,63,94,0.14); border: 1px solid rgba(244,63,94,0.45); color: #ffd3da; }
QPushButton#danger:hover { background: rgba(244,63,94,0.24); }
QLabel#pill, QLabel#pillOn, QLabel#pillWait, QLabel#pillBad { border-radius: 9px; padding: 3px 8px; font-size: 11px; font-weight: 600; }
QLabel#pill { background: rgba(255,255,255,0.06); color: $mute; }
QLabel#pillOn { background: rgba(52,211,153,0.16); color: #b7f7dc; }
QLabel#pillWait { background: rgba(251,191,36,0.16); color: #ffe7a3; }
QLabel#pillBad { background: rgba(244,63,94,0.16); color: #ffc1cc; }
QPushButton { background: rgba(255,255,255,0.05); border: 1px solid rgba($c1,0.34); border-radius: 14px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: rgba($c1,0.16); border: 1px solid $a1; }
QPushButton:pressed { background: rgba(255,255,255,0.04); }
QPushButton:disabled { color: $mute; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); }
QPushButton#primary { border: none; font-weight: 700; color: $on; padding: 10px 20px; border-radius: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $hi, stop:1 $lo); }
QPushButton#primary:hover { border: 2px solid $a2;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $hi, stop:1 $a2); }
QPushButton#primary:pressed { background: $lo; border: 1px solid transparent; }
QPushButton#primary:disabled { color: $mute; background: rgba($c1,0.35); border: 1px solid transparent; }
QPushButton#stop { border: 1px solid rgba(255,93,143,0.7); background: rgba(255,60,120,0.10); color: #ffd0dc; }
QPushButton#stop:hover { background: rgba(255,60,120,0.18); }
QFrame#subnav { background: rgba(0,0,0,0.24); border: 1px solid rgba($c1,0.28); border-radius: 14px; }
QScrollArea#subStrip, QWidget#subStrip { background: transparent; border: none; }
QPushButton#subArrow { background: rgba($c1,0.22); border: none; border-radius: 9px; padding: 4px 0; color: #ffffff; font-weight: 700; }
QPushButton#subArrow:hover { background: rgba($c1,0.45); }
QPushButton#subTab { background: transparent; border: none; border-radius: 10px; padding: 7px 14px; color: $text; font-weight: 500; }
QPushButton#subTab:hover { background: rgba($c1,0.20); color: #ffffff; }
QPushButton#subTab:checked { background: $a1; color: $on; font-weight: 700; }
QPushButton#quiet { background: rgba(0,0,0,0.25); border: 1px solid rgba($c1,0.42); }
QPushButton#quiet:hover { background: rgba($c1,0.22); border: 1px solid rgba($c1,0.80); }
QPushButton#quiet:checked { background: rgba(255,255,255,0.10); border: 1px solid $a1; color: #ffffff; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit { background: rgba(0,0,0,0.42); border: 1px solid rgba($c1,0.28);
    border-radius: 12px; padding: 8px 12px; selection-background-color: $a1; min-height: 20px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus { border: 1px solid $a1; background: rgba(0,0,0,0.5); }
QLineEdit#optional { background: transparent; border: 1px solid rgba(255,255,255,0.04); color: $mute; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: $mute; background: rgba(0,0,0,0.16); }
QMenu { background: $bg2; color: #f4f4f8; border: 1px solid rgba(255,255,255,0.14); padding: 6px; }
QMenu::item { padding: 7px 26px 7px 12px; border-radius: 6px; background: transparent; }
QMenu::item:selected { background: $a1; color: $on; }
QMenu::item:disabled { color: #8a93a8; }
QMenu::separator { height: 1px; background: rgba(255,255,255,0.12); margin: 5px 8px; }
QComboBox QAbstractItemView { background: $bg2; selection-background-color: $a1; border: 1px solid rgba(255,255,255,0.12); outline: 0; }
QSlider::groove:horizontal { height: 7px; background: rgba(255,255,255,0.12); border-radius: 3px; }
QSlider::sub-page:horizontal { border-radius: 3px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $hi, stop:1 $a2); }
QSlider::handle:horizontal { background: #ffffff; width: 18px; margin: -6px 0; border-radius: 9px; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.22); background: rgba(0,0,0,0.28); }
QCheckBox::indicator:hover { border: 1px solid $a1; }
QCheckBox::indicator:checked { border: 2px solid $bg; background: $a1; }
QFrame#banner { border-radius: 12px; border: 1px solid rgba(255,255,255,0.10); background: $bg2; }
QFrame#banner QLabel { color: $text; font-weight: 600; }
QLabel#live { color: #ffffff; font-weight: 800; padding: 4px 12px; background: $a2; border-radius: 10px; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.18); border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $a1; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
""")


def on_colour(accent):
    """Text colour on an accent fill: dark on light accents (lime, gold), white on deep ones (violet)."""
    c = QColor(accent)
    light = (0.2126 * c.redF() ** 2.2 + 0.7152 * c.greenF() ** 2.2 + 0.0722 * c.blueF() ** 2.2)
    return "#0b0b0d" if light > 0.35 else "#ffffff"


def build_qss(name):
    t = dict(THEMES.get(name, THEMES[DEFAULT_THEME]))
    for key, color in (("c1", "a1"), ("c2", "a2"), ("c3", "a3")):        # the same colours as numbers, for see-through fills
        c = QColor(t[color])
        t[key] = "%d,%d,%d" % (c.red(), c.green(), c.blue())
    t["hi"] = QColor(t["a1"]).lighter(118).name()
    t["lo"] = QColor(t["a1"]).darker(135).name()
    t["on"] = on_colour(t["a1"])
    return QSS.substitute(t)


class _Floaty(QObject):
    """Makes one button 'float': its glow grows and lifts on hover, and presses down on click."""

    def __init__(self, widget, fx):
        super().__init__(widget)
        self.w, self.fx = widget, fx
        self.effect = None
        widget.installEventFilter(self)
        if fx.enabled:
            self.build()

    def build(self):
        self.effect = QGraphicsDropShadowEffect(self.w)
        self.effect.setOffset(0, 1)
        self.effect.setBlurRadius(6)
        self.effect.setColor(self.fx.color)
        self.group = QParallelAnimationGroup(self.effect)
        self.blur = QPropertyAnimation(self.effect, b"blurRadius", self.group)
        self.lift = QPropertyAnimation(self.effect, b"yOffset", self.group)
        for a in (self.blur, self.lift):
            a.setEasingCurve(QEasingCurve.OutCubic)
            self.group.addAnimation(a)
        self.w.setGraphicsEffect(self.effect)

    def remove(self):
        if self.effect is not None:
            self.group.stop()
            self.w.setGraphicsEffect(None)      # Qt deletes the effect here
            self.effect = None

    def go(self, blur, y, ms):
        if self.effect is None:
            return
        self.group.stop()
        self.blur.setDuration(ms)
        self.lift.setDuration(ms)
        self.blur.setEndValue(blur)
        self.lift.setEndValue(y)
        self.group.start()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Enter:
            self.go(14, 4, 160)
        elif t == QEvent.Leave:
            self.go(6, 1, 180)
        elif t == QEvent.MouseButtonPress:
            self.go(8, 0, 70)
        elif t == QEvent.MouseButtonRelease:
            self.go(14, 4, 140)
        return False


class FX:
    """Registry of floating buttons. Lite mode turns every effect off for weak PCs."""

    def __init__(self, glow="#8b5cf6"):
        self.enabled = True
        self.color = QColor(glow)
        self.color.setAlpha(110)
        self.items = []

    def attach(self, widget):
        self.items.append(_Floaty(widget, self))

    def recolor(self, glow):
        self.color = QColor(glow)
        self.color.setAlpha(110)
        for it in self.items:
            if it.effect is not None:
                it.effect.setColor(self.color)

    def set_enabled(self, on):
        self.enabled = on
        for it in self.items:
            if on and it.effect is None:
                it.build()
            elif not on:
                it.remove()
