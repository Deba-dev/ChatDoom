"""Look and motion: the animated background, the sliding sidebar highlight, toast notifications and number count-ups.
Motion stops in Lite mode and whenever CHATDOOM is not the active window, so games keep the CPU."""
import math
import os
import sys
import time

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation, QRect, QRectF,
                            QSequentialAnimationGroup, Qt, QTimer, QVariantAnimation)
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)

from .icons import stat_tile
from .settings import data_dir

BACKGROUNDS = (("Waves", "aurora"), ("Soft", "gradient"), ("Plain", "plain"), ("Picture", "image"))
BUILT_IN_BACKGROUNDS = (("Nebula", "nebula"), ("Night lights", "night-lights"), ("Sunset", "sunset"),
                        ("Deep ocean", "deep-ocean"), ("Neon grid", "neon-grid"), ("Forest mist", "forest-mist"))
ROOT = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def background_path(value):
    """'builtin:nebula' or 'custom:file.png' -> the picture's path, or '' for anything else."""
    kind, _, name = str(value or "").partition(":")
    name = os.path.basename(name)
    if kind == "builtin" and name:
        return os.path.join(ROOT, "assets", "backgrounds", name + ".jpg")
    if kind == "custom" and name:
        return os.path.join(data_dir(), "Backgrounds", name)
    return ""
CARD_NAMES = ("tile", "card", "stat", "aside", "hero")
STAT_COLORS = {"violet": ("#a78bfa", "#6d28d9"), "green": ("#4ade80", "#059669"), "orange": ("#fdba74", "#ea580c"),
               "blue": ("#7dd3fc", "#2563eb"), "pink": ("#f9a8d4", "#c026d3")}


class Backdrop(QWidget):
    """Canvas behind the pages. Aurora is drawn small and scaled up smoothly, which keeps each frame cheap."""

    FPS = 12
    SCALE = 8

    def __init__(self, settings, theme):
        super().__init__()
        self.s, self.theme = settings, dict(theme)
        self.t0 = time.monotonic()
        self.phase = 0.0
        self.frame = None                # the finished picture; repainting a small area only copies from it
        self.picture = (None, None)      # (setting value, loaded picture), so a repaint never reads the file again
        self.timer = QTimer(self)
        self.timer.setInterval(1000 // self.FPS)
        self.timer.timeout.connect(self._step)
        QApplication.instance().applicationStateChanged.connect(lambda _: self.sync())

    def set_theme(self, theme):
        self.theme = dict(theme)
        self.frame = None
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
        self.frame = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.frame = None

    def showEvent(self, event):
        super().showEvent(event)
        self.sync()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def _step(self):
        self.phase = time.monotonic() - self.t0
        self.frame = None
        self.update()

    def blobs(self, t):
        """Three soft lights wandering on slow Lissajous paths (positions 0..1, radius as a share of the width)."""
        a1, a2, a3 = (QColor(self.theme[k]) for k in ("a1", "a2", "a3"))
        return ((a1, 0.22 + 0.16 * math.sin(t * 0.11), 0.30 + 0.20 * math.sin(t * 0.07 + 1.0), 0.55),
                (a2, 0.78 + 0.14 * math.sin(t * 0.09 + 2.0), 0.25 + 0.18 * math.cos(t * 0.06), 0.45),
                (a3, 0.55 + 0.25 * math.cos(t * 0.05 + 0.5), 0.88 + 0.10 * math.sin(t * 0.08 + 3.0), 0.50))

    def ribbons(self, painter, w, h, t):
        """Glowing bands that flow along the top right and the bottom edge."""
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        a1, a2, a3 = (QColor(self.theme[k]) for k in ("a1", "a2", "a3"))
        bands = ((a1, 0.02, -0.16, 0.12, 0.8, 0.20, 90), (a2, -0.02, -0.10, 0.08, 1.1, 0.12, 70), (a3, 0.10, -0.18, 0.05, 1.5, 0.05, 80),
                 (a1, 0.92, 0.03, 0.05, 1.2, 0.20, 80), (a2, 0.97, -0.02, 0.03, 0.9, 0.10, 70))
        for i, (color, y0, tilt, swing, waves, thick, alpha) in enumerate(bands):
            top, low = [], []
            for n in range(41):
                x = n / 40.0
                y = y0 + tilt * x + swing * math.sin(waves * math.pi * x + t * 0.22 + i * 1.3)
                band = thick * (0.45 + 0.55 * (0.5 + 0.5 * math.sin(x * 2.4 + t * 0.15 + i)))
                top.append(QPointF(x * w, y * h))
                low.append(QPointF(x * w, (y + band) * h))
            path = QPainterPath(top[0])
            for pt in top[1:]:
                path.lineTo(pt)
            for pt in reversed(low):
                path.lineTo(pt)
            path.closeSubpath()
            g = QLinearGradient(0, 0, w, 0)
            start, mid, end = QColor(color), QColor(color), QColor(color)
            start.setAlpha(0 if i < 3 else alpha // 2)
            mid.setAlpha(alpha // 3 if i < 3 else alpha // 4)
            end.setAlpha(alpha)
            g.setColorAt(0, start)
            g.setColorAt(0.55, mid)
            g.setColorAt(1, end)
            painter.fillPath(path, g)

    def paintEvent(self, event):
        if self.frame is None or self.frame.size() != self.size():
            self.frame = QPixmap(self.size())
            canvas = QPainter(self.frame)
            self.draw(canvas)
            canvas.end()
        painter = QPainter(self)
        painter.drawPixmap(event.rect(), self.frame, event.rect())

    def _load_picture(self):
        value = self.s.get("bg_image")
        if self.picture[0] != value:
            image = QImage(background_path(value))
            self.picture = (value, None if image.isNull() else image)
        return self.picture[1]

    def _draw_picture(self, painter, image):
        scaled = image.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        painter.drawImage((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
        shade = QColor(self.theme["bg"])
        shade.setAlpha(int(255 * min(85, max(20, int(self.s.get("bg_dim")))) / 100))
        painter.fillRect(self.rect(), shade)

    def draw(self, painter):
        bg, bg2 = QColor(self.theme["bg"]), QColor(self.theme["bg2"])
        mode = self.s.get("background")
        if mode == "image":
            image = self._load_picture()
            if image is not None:
                self._draw_picture(painter, image)
                return
            mode = "gradient"                     # a moved or deleted picture must not leave the window blank
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
        self.ribbons(painter, self.width(), self.height(), self.phase)


class Motion(QObject):
    """One slow clock for all small moving parts. It stops in Lite mode and when CHATDOOM is not the active window."""

    FPS = 12

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s, self.items = settings, []
        self.timer = QTimer(self)
        self.timer.setInterval(1000 // self.FPS)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def add(self, widget):
        self.items.append(widget)

    def _tick(self):
        if self.s.get("lite_mode") or QApplication.applicationState() != Qt.ApplicationActive:
            return
        for w in self.items:
            if w.isVisible():
                w.phase += 1.0 / self.FPS
                w.update()


class StatCard(QFrame):
    """A number with a colour badge, and a slowly moving line on the right."""

    def __init__(self, icon, color, value, caption, seed=0.0):
        super().__init__()
        self.setObjectName("stat")
        self.setMinimumHeight(92)
        self.color, self.phase, self.seed = color, 0.0, seed
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 12, 16, 12)
        lay.setSpacing(16)
        self.badge = QLabel()
        self.badge.setFixedSize(58, 58)
        self.badge.setStyleSheet("background: transparent;")
        lay.addWidget(self.badge)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.num = QLabel(str(value))
        self.num.setObjectName("statNum")
        self.cap = QLabel(caption)
        self.cap.setObjectName("statCap")
        col.addStretch(1)
        col.addWidget(self.num)
        col.addWidget(self.cap)
        col.addStretch(1)
        lay.addLayout(col)
        lay.addStretch(1)
        self._key = None
        self.show_stat(icon, color, value, caption)

    def show_stat(self, icon, color, value, caption):
        if self._key != (icon, color):
            self._key, self.color = (icon, color), color
            self.badge.setPixmap(stat_tile(icon, STAT_COLORS[color], 58))
        if self.num.text() != str(value):
            self.num.setText(str(value))
        if self.cap.text() != caption:
            self.cap.setText(caption)

    def paintEvent(self, event):
        super().paintEvent(event)
        w, h = self.width(), self.height()
        x0 = w * 0.50
        if w - x0 < 40:
            return
        c1, c2 = (QColor(c) for c in STAT_COLORS[self.color])
        pts = []
        t = self.phase * 0.7 + self.seed
        for n in range(33):
            f = n / 32.0
            y = 0.58 + 0.17 * math.sin(f * 5.2 + t) * (0.45 + 0.55 * f) - 0.20 * f * f
            pts.append(QPointF(x0 + f * (w - x0), h * y))
        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        fill = QPainterPath(line)
        fill.lineTo(pts[-1].x(), h)
        fill.lineTo(pts[0].x(), h)
        fill.closeSubpath()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 21, 21)
        p.setClipPath(shape)
        shade = QLinearGradient(x0, 0, w, 0)
        faint, strong = QColor(c2), QColor(c2)
        faint.setAlpha(0)
        strong.setAlpha(90)
        shade.setColorAt(0, faint)
        shade.setColorAt(1, strong)
        p.fillPath(fill, shade)
        pen_grad = QLinearGradient(x0, 0, w, 0)
        c_start = QColor(c1)
        c_start.setAlpha(30)
        pen_grad.setColorAt(0, c_start)
        pen_grad.setColorAt(1, c1)
        pen = QPen(pen_grad, 2.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(line)


class HeroCard(QFrame):
    """The large welcome card; the robot floats gently in the corner."""

    def __init__(self, picture):
        super().__init__()
        self.setObjectName("hero")
        self.setMinimumHeight(250)
        self.art = QPixmap(picture)
        self.scaled = None
        self.phase = 0.0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scaled = None

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.art.isNull():
            return
        if self.scaled is None:
            self.scaled = self.art.scaledToHeight(min(int(self.height() * 0.70), 240), Qt.SmoothTransformation)
        lift = 5.0 * math.sin(self.phase * 1.3)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 21, 21)
        p.setClipPath(shape)
        p.drawPixmap(QPointF(self.width() - self.scaled.width() - 10, self.height() - self.scaled.height() + 6 + lift), self.scaled)


def top_cards(root):
    """The outermost cards inside a page (a card inside a card moves with its parent)."""
    found = []
    for frame in root.findChildren(QFrame):
        if frame.objectName() not in CARD_NAMES:
            continue
        parent = frame.parentWidget()
        while parent is not None and parent is not root:
            if parent.objectName() in CARD_NAMES:
                break
            parent = parent.parentWidget()
        else:
            found.append(frame)
    return found


class CardGlow(QObject):
    """Cards light up in the theme colour while the mouse is over them."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s, self.color = settings, QColor("#7c3aed")

    def watch(self, root):
        for card in top_cards(root):
            if not card.property("glows"):
                card.setProperty("glows", True)
                card.installEventFilter(self)

    def eventFilter(self, obj, ev):
        kind = ev.type()
        if kind == QEvent.Enter and not self.s.get("lite_mode") and obj.graphicsEffect() is None:
            shade = QGraphicsDropShadowEffect(obj)
            shade.setOffset(0, 0)
            shade.setBlurRadius(0)
            shade.setColor(self.color)
            obj.setGraphicsEffect(shade)
            grow = QPropertyAnimation(shade, b"blurRadius", shade)
            grow.setDuration(220)
            grow.setEndValue(30)
            grow.setEasingCurve(QEasingCurve.OutCubic)
            grow.start()
        elif kind == QEvent.Leave and isinstance(obj.graphicsEffect(), QGraphicsDropShadowEffect):
            obj.setGraphicsEffect(None)
        return False


def stagger_in(page, parent, gap=45, limit=9):
    """Cards fade in one after the other. Returns the animation and the cards, or (None, []) if there is nothing to animate."""
    cards = [c for c in top_cards(page) if c.isVisible() and c.mapTo(page, QPoint(0, 0)).y() < max(1, page.height())]
    cards = [c for c in cards if c.graphicsEffect() is None][:limit]
    if not cards:
        return None, []
    group = QParallelAnimationGroup(parent)
    for i, card in enumerate(cards):
        fx = QGraphicsOpacityEffect(card)
        fx.setOpacity(0.0)
        card.setGraphicsEffect(fx)
        fade = QPropertyAnimation(fx, b"opacity")
        fade.setDuration(260)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        step = QSequentialAnimationGroup()
        step.addPause(i * gap)
        step.addAnimation(fade)
        group.addAnimation(step)
    return group, cards


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

