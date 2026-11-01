"""Look and motion: the animated background, the sliding sidebar highlight, toast notifications and number count-ups.
Motion stops in Lite mode and whenever CHATDOOM is not the active window, so games keep the CPU."""
import math
import time

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

BACKGROUNDS = (("Aurora (animated)", "aurora"), ("Soft gradient", "gradient"), ("Plain", "plain"))


class Backdrop(QWidget):
    """Canvas behind the pages. Aurora is drawn small and scaled up smoothly, which keeps each frame cheap."""

    FPS = 12
    SCALE = 8

    def __init__(self, settings, theme):
        super().__init__()
        self.s, self.theme = settings, dict(theme)
        self.t0 = time.monotonic()
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(1000 // self.FPS)
        self.timer.timeout.connect(self._step)
        QApplication.instance().applicationStateChanged.connect(lambda _: self.sync())

    def set_theme(self, theme):
        self.theme = dict(theme)
        self.update()

    def animated(self):
        return (self.s.get("background") == "aurora" and not self.s.get("lite_mode") and self.isVisible()
                and QApplication.applicationState() == Qt.ApplicationActive)

    def sync(self):
        """Start or stop the motion after a setting, focus or visibility change."""
        if self.animated():
            if not self.timer.isActive():
                self.t0 = time.monotonic() - self.phase
                self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def _step(self):
        self.phase = time.monotonic() - self.t0
        self.update()

    def blobs(self, t):
        """Three soft lights wandering on slow Lissajous paths (positions 0..1, radius as a share of the width)."""
        a1, a2, a3 = (QColor(self.theme[k]) for k in ("a1", "a2", "a3"))
        return ((a1, 0.22 + 0.16 * math.sin(t * 0.11), 0.30 + 0.20 * math.sin(t * 0.07 + 1.0), 0.55),
                (a2, 0.78 + 0.14 * math.sin(t * 0.09 + 2.0), 0.25 + 0.18 * math.cos(t * 0.06), 0.45),
                (a3, 0.55 + 0.25 * math.cos(t * 0.05 + 0.5), 0.88 + 0.10 * math.sin(t * 0.08 + 3.0), 0.50))

    def paintEvent(self, event):
        painter = QPainter(self)
        bg, bg2 = QColor(self.theme["bg"]), QColor(self.theme["bg2"])
        mode = self.s.get("background")
        if mode == "plain":
            painter.fillRect(self.rect(), bg)
            return
        if mode != "aurora":
            g = QLinearGradient(0, 0, self.width(), self.height())
            g.setColorAt(0, bg)
            g.setColorAt(0.72, bg)
            g.setColorAt(1, bg2)
            painter.fillRect(self.rect(), g)
            return
        w, h = max(8, self.width() // self.SCALE), max(8, self.height() // self.SCALE)
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(bg)
        small = QPainter(img)
        small.setRenderHint(QPainter.Antialiasing)
        strength = 70 if self.s.get("lite_mode") else 95
        for color, x, y, r in self.blobs(self.phase):
            grad = QRadialGradient(QPointF(x * w, y * h), r * w)
            inner, outer = QColor(color), QColor(color)
            inner.setAlpha(strength)
            outer.setAlpha(0)
            grad.setColorAt(0, inner)
            grad.setColorAt(1, outer)
            small.fillRect(img.rect(), grad)
        shade = QLinearGradient(0, 0, 0, h)                      # darker toward the bottom so text stays readable
        shade.setColorAt(0, QColor(0, 0, 0, 0))
        shade.setColorAt(1, QColor(0, 0, 0, 120))
        small.fillRect(img.rect(), shade)
        small.end()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self.rect(), img)


class NavIndicator(QFrame):
    """The highlight behind the selected sidebar button; it glides to the new button."""

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.s = settings
        self.setObjectName("navGlow")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.anim = QPropertyAnimation(self, b"geometry", self)
        self.anim.setDuration(260)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.target = None
        self.hide()

    def move_to(self, button, animate=True):
        self.target = button
        if button is None or not button.isVisible():
            return
        rect = QRect(button.mapTo(self.parentWidget(), QPoint(0, 0)), button.size()).adjusted(12, 1, -12, -1)
        self.lower()
        if not self.isVisible() or not animate or self.s.get("lite_mode"):
            self.anim.stop()
            self.setGeometry(rect)
            self.show()
            return
        self.anim.stop()
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(rect)
        self.anim.start()

    def follow(self):
        """Re-place without motion (after a resize)."""
        if self.target is not None:
            self.move_to(self.target, animate=False)


class Toasts:
    """Small notices that slide in at the top right of the canvas and fade out by themselves."""

    MAX = 4

    def __init__(self, canvas, settings):
        self.canvas, self.s, self.items = canvas, settings, []

    def show(self, text, kind="info", seconds=4.0):
        if not self.s.get("toasts"):
            return None
        box = QFrame(self.canvas)
        box.setObjectName("toast")
        box.setProperty("kind", kind)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(14, 10, 14, 10)
        dot = QLabel("●")
        dot.setObjectName("toastDot")
        dot.setProperty("kind", kind)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMinimumWidth(200)
        label.setMaximumWidth(320)
        lay.addWidget(dot, 0, Qt.AlignTop)
        lay.addWidget(label, 1)
        box.label = label
        box.adjustSize()
        box.mousePressEvent = lambda e, b=box: self.dismiss(b)
        fx = QGraphicsOpacityEffect(box)
        fx.setOpacity(0.0 if not self.s.get("lite_mode") else 1.0)
        box.setGraphicsEffect(fx)
        self.items.insert(0, box)
        while len(self.items) > self.MAX:
            self._drop(self.items.pop())
        self.layout_all(new=box)
        box.show()
        box.raise_()
        if not self.s.get("lite_mode"):
            fade = QPropertyAnimation(fx, b"opacity", box)
            fade.setDuration(220)
            fade.setEndValue(1.0)
            fade.start()
        QTimer.singleShot(int(seconds * 1000), lambda b=box: self.dismiss(b))
        return box

    def layout_all(self, new=None):
        y = 74
        for box in self.items:
            end = QPoint(self.canvas.width() - box.width() - 28, y)
            old = getattr(box, "_slide", None)
            if old is not None:
                old.stop()                             # a running slide-in would pull it back to its old place
            if box is new and not self.s.get("lite_mode"):
                slide = QPropertyAnimation(box, b"pos", box)
                box._slide = slide
                slide.setDuration(320)
                slide.setEasingCurve(QEasingCurve.OutBack)
                slide.setStartValue(end + QPoint(60, 0))
                slide.setEndValue(end)
                slide.start()
            else:
                box.move(end)
            y += box.height() + 8

    def dismiss(self, box):
        if box not in self.items:
            return
        self.items.remove(box)
        if self.s.get("lite_mode"):
            self._drop(box)
        else:
            fade = QPropertyAnimation(box.graphicsEffect(), b"opacity", box)
            fade.setDuration(240)
            fade.setEndValue(0.0)
            fade.finished.connect(lambda b=box: self._drop(b))
            fade.start()
        self.layout_all()

    def _drop(self, box):
        box.hide()
        box.deleteLater()


def count_to(label, value, settings, owner):
    """Show a number change on a stat chip as a short count-up."""
    try:
        start = int(label.text())
    except ValueError:
        start = value
    old = getattr(label, "_count_anim", None)
    if old is not None:
        old.stop()
    if start == value or settings.get("lite_mode"):
        label.setText(str(value))
        return
    anim = QVariantAnimation(owner)
    anim.setDuration(380)
    anim.setStartValue(start)
    anim.setEndValue(value)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.valueChanged.connect(lambda v: label.setText(str(int(v))))
    anim.finished.connect(lambda: label.setText(str(value)))
    label._count_anim = anim
    anim.start()

