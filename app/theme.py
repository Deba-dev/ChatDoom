"""Colour themes, the stylesheet, and the floating hover effect for buttons."""
from string import Template

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QParallelAnimationGroup, QPropertyAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

THEMES = {
    "Neon Violet": dict(bg="#07080c", bg2="#12141c", text="#f4f4f8", mute="#9b9bb0", a1="#7c5cff", a2="#c4b5fd", a3="#e9d5ff"),
    "Sunset":      dict(bg="#1a1216", bg2="#24181d", text="#fff1f4", mute="#c9a3b4", a1="#ff7a45", a2="#ff3d81", a3="#ffd166"),
    "Ocean":       dict(bg="#0d1620", bg2="#12202c", text="#eaf6ff", mute="#8db3cf", a1="#00b8ff", a2="#4f7cff", a3="#2dd4bf"),
    "Matcha":      dict(bg="#101814", bg2="#16201a", text="#effff5", mute="#93bfa5", a1="#34d399", a2="#a3e635", a3="#22d3ee"),
}
DEFAULT_THEME = "Neon Violet"

QSS = Template("""
* { font-family: "Poppins", "Segoe UI", "Noto Sans Devanagari", sans-serif; font-size: 13px; color: $text; }
QWidget#root { background: $bg; }
QDialog { background: $bg2; }
QWidget#canvas { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $bg, stop:0.72 $bg, stop:1 $bg2); }
QWidget#page, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QFrame#side { background: rgba(0,0,0,0.45); border-right: 1px solid rgba(255,255,255,0.04); }
QLabel#brandMark { background: $a1; color: #ffffff; font-size: 12px; font-weight: 700; border-radius: 8px; padding: 6px 7px; }
QLabel#logo { font-size: 20px; font-weight: 700; }
QLabel#tagline { color: $mute; font-size: 11px; }
QLabel#group { color: $mute; font-size: 10px; font-weight: 700; padding: 12px 16px 4px 16px; }
QLabel#title { font-size: 28px; font-weight: 650; }
QLabel#sub { color: $mute; font-size: 13px; }
QLabel#hint, QLabel#field { color: $mute; font-size: 12px; }
QLabel#pageTitle, QLabel#voiceTitle { font-size: 17px; font-weight: 650; }
QLabel#settingName, QLabel#voiceName { font-size: 14px; font-weight: 600; }
QLabel#pageNote, QLabel#settingNote, QLabel#voiceNote { color: $mute; font-size: 13px; }
QLabel#settingValue, QLabel#voiceValue { font-size: 14px; font-weight: 650; }
QLabel#statNum { font-size: 20px; font-weight: 650; }
QFrame#stat, QFrame#aside { background: rgba(255,255,255,0.035); border: none; border-radius: 14px; }
QPushButton#nav { text-align: left; padding: 7px 12px; border: none; margin: 1px 12px; border-radius: 8px;
    background: transparent; color: $mute; font-size: 13px; font-weight: 500; }
QPushButton#nav:hover { background: rgba(255,255,255,0.05); color: $text; }
QPushButton#nav:checked { color: #ffffff; font-weight: 600; background: transparent; }
QFrame#navGlow { border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0.12), stop:1 rgba(255,255,255,0.03));
    border-left: 3px solid $a1; }
QFrame#toast { background: rgba(14,16,26,0.94); border: 1px solid rgba(255,255,255,0.12); border-radius: 12px; }
QLabel#toastDot { color: $a1; font-size: 11px; }
QLabel#toastDot[kind="good"] { color: #34d399; }
QLabel#toastDot[kind="warn"] { color: #fbbf24; }
QLabel#toastDot[kind="gold"] { color: #ffd24d; }
QFrame#card, QFrame#tile { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.045); border-radius: 16px; }
QListWidget { background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 4px; outline: 0; }
QListWidget::item { padding: 7px 10px; border-radius: 7px; }
QListWidget::item:hover { background: rgba(255,255,255,0.06); }
QListWidget::item:selected { background: $a1; color: #ffffff; }
QFrame#infoBox { background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.05); border-left: 3px solid $a1; border-radius: 10px; }
QLabel#stepNum { background: $a1; color: #ffffff; border-radius: 13px; font-weight: 700; font-size: 12px; }
QPushButton#danger { background: rgba(244,63,94,0.14); border: 1px solid rgba(244,63,94,0.45); color: #ffd3da; }
QPushButton#danger:hover { background: rgba(244,63,94,0.24); }
QLabel#pill, QLabel#pillOn, QLabel#pillWait, QLabel#pillBad { border-radius: 9px; padding: 3px 8px; font-size: 11px; font-weight: 600; }
QLabel#pill { background: rgba(255,255,255,0.06); color: $mute; }
QLabel#pillOn { background: rgba(52,211,153,0.16); color: #b7f7dc; }
QLabel#pillWait { background: rgba(251,191,36,0.16); color: #ffe7a3; }
QLabel#pillBad { background: rgba(244,63,94,0.16); color: #ffc1cc; }
QPushButton { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; padding: 7px 12px; font-weight: 500; }
QPushButton:hover { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.16); }
QPushButton:pressed { background: rgba(255,255,255,0.04); }
QPushButton:disabled { color: $mute; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); }
QPushButton#primary { border: 1px solid transparent; font-weight: 600; color: #ffffff; background: $a1; }
QPushButton#primary:hover { background: $a1; border: 1px solid rgba(255,255,255,0.28); }
QPushButton#primary:pressed { background: $a1; border: 1px solid transparent; }
QPushButton#primary:disabled { color: rgba(255,255,255,0.55); background: $a1; border: 1px solid transparent; }
QPushButton#stop { border: 1px solid rgba(255,93,143,0.7); background: rgba(255,60,120,0.10); color: #ffd0dc; }
QPushButton#stop:hover { background: rgba(255,60,120,0.18); }
QPushButton#quiet { background: transparent; border: 1px solid rgba(255,255,255,0.12); }
QPushButton#quiet:hover { background: rgba(255,255,255,0.06); }
QPushButton#quiet:checked { background: rgba(255,255,255,0.10); border: 1px solid $a1; color: #ffffff; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit { background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; padding: 8px 12px; selection-background-color: $a1; min-height: 20px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus { border: 1px solid $a1; background: rgba(0,0,0,0.5); }
QLineEdit#optional { background: transparent; border: 1px solid rgba(255,255,255,0.04); color: $mute; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: $mute; background: rgba(0,0,0,0.16); }
QComboBox QAbstractItemView { background: $bg2; selection-background-color: $a1; border: 1px solid rgba(255,255,255,0.12); outline: 0; }
QSlider::groove:horizontal { height: 7px; background: rgba(255,255,255,0.12); border-radius: 3px; }
QSlider::sub-page:horizontal { border-radius: 3px; background: $a1; }
QSlider::handle:horizontal { background: #ffffff; width: 18px; margin: -6px 0; border-radius: 9px; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.22); background: rgba(0,0,0,0.28); }
QCheckBox::indicator:hover { border: 1px solid $a1; }
QCheckBox::indicator:checked { border: none; background: $a1; }
QFrame#banner { border-radius: 12px; border: 1px solid rgba(255,255,255,0.10); background: $bg2; }
QFrame#banner QLabel { color: $text; font-weight: 600; }
QLabel#live { color: #ffffff; font-weight: 700; padding: 4px 12px; background: #e11d48; border-radius: 8px; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.18); border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $a1; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
""")


def build_qss(name):
    return QSS.substitute(THEMES.get(name, THEMES[DEFAULT_THEME]))


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
