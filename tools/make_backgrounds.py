"""Draws the built-in background pictures into assets/backgrounds. Run once:  py -3.12 tools/make_backgrounds.py"""
import math
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

W, H = 1920, 1080
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "backgrounds")


def fill(p, stops):
    g = QLinearGradient(0, 0, W * 0.25, H)
    for at, colour in stops:
        g.setColorAt(at, QColor(colour))
    p.fillRect(0, 0, W, H, g)


def glow(p, x, y, r, colour, alpha):
    c = QColor(colour)
    c.setAlpha(alpha)
    edge = QColor(colour)
    edge.setAlpha(0)
    g = QRadialGradient(QPointF(x, y), r)
    g.setColorAt(0, c)
    g.setColorAt(1, edge)
    p.fillRect(0, 0, W, H, g)


def stars(p, rng, count):
    p.setPen(Qt.NoPen)
    for _ in range(count):
        c = QColor(255, 255, 255, rng.randint(50, 220))
        p.setBrush(c)
        size = rng.choice((1.0, 1.0, 1.4, 2.0, 2.6))
        p.drawEllipse(QPointF(rng.uniform(0, W), rng.uniform(0, H)), size, size)


def ridge(p, rng, base, height, colour, roughness):
    path = QPainterPath(QPointF(0, H))
    a, b, c = rng.uniform(0, 6), rng.uniform(0, 6), rng.uniform(0, 6)
    for x in range(0, W + 8, 8):
        wave = math.sin(x / 310 + a) + 0.5 * math.sin(x / 130 + b) + roughness * math.sin(x / 47 + c)
        path.lineTo(x, base - height * wave)
    path.lineTo(W, H)
    path.closeSubpath()
    p.fillPath(path, QColor(colour))


def ribbon(p, y, swing, colour, alpha, thick):
    p.setBrush(Qt.NoBrush)
    for layer in range(14):
        c = QColor(colour)
        c.setAlpha(max(4, alpha - layer * (alpha // 15)))
        pen = QPen(c, thick + layer * 7)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        path = QPainterPath(QPointF(-40, y))
        for x in range(-40, W + 60, 20):
            path.lineTo(x, y + swing * math.sin(x / 300) + swing * 0.45 * math.sin(x / 120 + 1.2) - layer * 9)
        p.drawPath(path)
    p.setPen(Qt.NoPen)


def nebula(p, rng):
    fill(p, ((0, "#07041c"), (1, "#120733")))
    for x, y, r, colour, alpha in ((420, 300, 760, "#7c3aed", 170), (1400, 280, 700, "#db2777", 130), (1050, 880, 800, "#2563eb", 150), (220, 900, 520, "#0ea5e9", 90)):
        glow(p, x, y, r, colour, alpha)
    stars(p, rng, 520)


def night_lights(p, rng):
    fill(p, ((0, "#03121a"), (1, "#061f24")))
    stars(p, rng, 300)
    ribbon(p, 340, 90, "#2dd4bf", 44, 10)
    ribbon(p, 470, 120, "#22c55e", 34, 8)
    ribbon(p, 250, 70, "#818cf8", 28, 7)
    ridge(p, rng, 900, 34, "#04161b", 0.25)
    ridge(p, rng, 985, 28, "#020c10", 0.3)


def sunset(p, rng):
    fill(p, ((0, "#1b1035"), (0.45, "#7a1f5c"), (0.72, "#e8562e"), (1, "#f8a03f")))
    glow(p, 1250, 700, 420, "#ffd27a", 235)
    ridge(p, rng, 800, 46, "#5a1848", 0.2)
    ridge(p, rng, 880, 38, "#33103b", 0.25)
    ridge(p, rng, 985, 30, "#170a24", 0.3)


def deep_ocean(p, rng):
    fill(p, ((0, "#04223a"), (0.6, "#031627"), (1, "#010912")))
    for x, r, alpha in ((430, 620, 80), (960, 760, 110), (1500, 580, 70)):
        glow(p, x, -60, r, "#38bdf8", alpha)
    for y, swing, colour, alpha in ((560, 34, "#0ea5e9", 20), (720, 44, "#2563eb", 18), (880, 30, "#14b8a6", 16)):
        ribbon(p, y, swing, colour, alpha, 12)
    p.setPen(Qt.NoPen)
    for _ in range(90):
        p.setBrush(QColor(180, 230, 255, rng.randint(20, 80)))
        p.drawEllipse(QPointF(rng.uniform(0, W), rng.uniform(300, H)), *(rng.uniform(1.5, 5.5),) * 2)


def neon_grid(p, rng):
    fill(p, ((0, "#0a0420"), (0.55, "#1a0838"), (1, "#05020f")))
    horizon = 610
    glow(p, W / 2, horizon, 620, "#ec4899", 190)
    glow(p, W / 2, horizon, 300, "#fbbf24", 110)
    stars(p, rng, 180)
    p.fillRect(0, horizon, W, H - horizon, QColor("#070314"))
    line = QColor("#c026d3")
    line.setAlpha(150)
    p.setPen(QPen(line, 2))
    for i in range(-18, 19):
        p.drawLine(QPointF(W / 2 + i * 34, horizon), QPointF(W / 2 + i * 250, H))
    for i in range(1, 13):
        y = horizon + (H - horizon) * (i / 12) ** 2.1
        p.drawLine(QPointF(0, y), QPointF(W, y))


def forest_mist(p, rng):
    fill(p, ((0, "#16302b"), (0.6, "#0d221e"), (1, "#06120f")))
    glow(p, 1320, 210, 620, "#a7f3d0", 95)
    for base, height, colour, rough in ((620, 40, "#1c3f37", 0.2), (720, 44, "#14312b", 0.3), (830, 40, "#0d2420", 0.4), (950, 34, "#071512", 0.5)):
        ridge(p, rng, base, height, colour, rough)
        glow(p, W / 2, base + 60, 1100, "#d1fae5", 16)


PICTURES = {"nebula": nebula, "night-lights": night_lights, "sunset": sunset, "deep-ocean": deep_ocean, "neon-grid": neon_grid, "forest-mist": forest_mist}


def main():
    app = QGuiApplication(sys.argv)
    os.makedirs(OUT, exist_ok=True)
    for name, draw in PICTURES.items():
        image = QImage(W, H, QImage.Format_RGB32)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        draw(painter, random.Random(name))
        painter.end()
        image.save(os.path.join(OUT, name + ".jpg"), "JPG", 84)
        print("made", name)
    del app


if __name__ == "__main__":
    main()
