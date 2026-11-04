r"""Makes every logo file the app uses from ONE picture, so the desktop icon and the in-app logo can never differ.

To change the logo: replace branding/chatdoom-logo-source.png, then run   py -3.12 tools\make_icons.py
Writes assets/chatdoom-logo.png, robot.png, icon.png and icon.ico. tests/test_app.py fails if they are out of date.
Needs only PySide6 (no Pillow), so it runs anywhere the app runs.
"""
import hashlib
import os
import struct
import sys
from collections import deque

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QIODevice, QRect, QRectF, Qt        # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "branding", "chatdoom-logo-source.png")
STAMP = os.path.join(ROOT, "branding", "source.sha256")
ASSETS = os.path.join(ROOT, "assets")
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
BRIGHT = 150                      # the black backdrop is cleared up to this brightness; anything enclosed stays solid

# Picture areas as shares of the source, so a same-layout logo of another size still works
ROBOT_BOX = (0.03, 0.04, 0.92, 0.545)       # robot, chat bubbles and sparkles, without the name plate
ICON_BOX = (0.215, 0.04, 0.585, 0.545)      # the robot alone, for icons


def source_hash():
    with open(SOURCE, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def clear_backdrop(img):
    """Turn the black around the logo transparent. Glow fades out softly; black inside the logo (the visor) stays."""
    img = img.convertToFormat(QImage.Format_RGBA8888)
    w, h, stride = img.width(), img.height(), img.bytesPerLine()
    px = bytearray(img.constBits().tobytes())
    outside = bytearray(w * h)
    todo = deque()
    for x in range(w):
        todo.extend((x, (h - 1) * w + x))
    for y in range(h):
        todo.extend((y * w, y * w + w - 1))
    while todo:
        i = todo.pop()
        if outside[i]:
            continue
        y, x = divmod(i, w)
        o = y * stride + x * 4
        if max(px[o], px[o + 1], px[o + 2]) >= BRIGHT:
            continue
        outside[i] = 1
        if x:
            todo.append(i - 1)
        if x < w - 1:
            todo.append(i + 1)
        if y:
            todo.append(i - w)
        if y < h - 1:
            todo.append(i + w)
    for y in range(h):
        for x in range(w):
            if outside[y * w + x]:
                o = y * stride + x * 4
                level = max(px[o], px[o + 1], px[o + 2])
                alpha = level * 255 // BRIGHT
                if alpha:
                    for c in range(3):
                        px[o + c] = min(255, px[o + c] * 255 // alpha)
                px[o + 3] = alpha
    return QImage(bytes(px), w, h, stride, QImage.Format_RGBA8888).copy()


def box(img, shares):
    x, y, w, h = shares
    return QRect(int(x * img.width()), int(y * img.height()), int(w * img.width()), int(h * img.height()))


def fade_bottom(img, share=0.05):
    """Soften the cut edge along the bottom of a crop."""
    img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    g = QLinearGradient(0, img.height() * (1 - share), 0, img.height())
    g.setColorAt(0, QColor(0, 0, 0, 255))
    g.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(QRect(0, int(img.height() * (1 - share)), img.width(), img.height()), g)
    p.end()
    return img


def robot_art(clear):
    art = clear.copy(box(clear, ROBOT_BOX)).convertToFormat(QImage.Format_ARGB32_Premultiplied)
    w, h = art.width(), art.height()
    p = QPainter(art)
    p.setCompositionMode(QPainter.CompositionMode_Clear)        # bits of the name plate's glow that reach into the crop
    p.fillRect(QRect(0, int(h * 0.90), int(w * 0.235), h), Qt.transparent)
    p.fillRect(QRect(int(w * 0.845), int(h * 0.80), w, h), Qt.transparent)
    p.end()
    return fade_bottom(art, 0.04)


def icon_image(robot, size):
    """App icon: the robot on a dark rounded tile, which stays readable on any wallpaper and at 16 pixels."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#2a1470"))
    g.setColorAt(1, QColor("#0a0620"))
    p.fillPath(tile, g)
    p.setClipPath(tile)
    fit = robot.scaled(int(size * 0.98), int(size * 0.98), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    p.drawImage((size - fit.width()) // 2, size - fit.height(), fit)
    p.end()
    return img


def png_bytes(img):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path, images):
    """A standard .ico with PNG entries (Windows Vista and later), so no extra library is needed."""
    entries, blobs = [], []
    offset = 6 + 16 * len(images)
    for size, img in images:
        data = png_bytes(img)
        side = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(blobs))


def main():
    app = QGuiApplication(sys.argv[:1])
    src = QImage(SOURCE)
    if src.isNull():
        raise SystemExit("Could not read " + SOURCE)
    clear = clear_backdrop(src)
    clear.scaledToWidth(640, Qt.SmoothTransformation).save(os.path.join(ASSETS, "chatdoom-logo.png"))
    robot_art(clear).scaledToWidth(760, Qt.SmoothTransformation).save(os.path.join(ASSETS, "robot.png"))
    head = clear.copy(box(clear, ICON_BOX)).convertToFormat(QImage.Format_ARGB32_Premultiplied)
    p = QPainter(head)
    p.setCompositionMode(QPainter.CompositionMode_Clear)        # the chat bubble and heart would be cut off by the tile's edge
    p.fillRect(QRect(int(head.width() * 0.885), 0, head.width(), int(head.height() * 0.68)), Qt.transparent)
    p.end()
    head = fade_bottom(head, 0.03)
    icon_image(head, 512).save(os.path.join(ASSETS, "icon.png"))
    write_ico(os.path.join(ASSETS, "icon.ico"), [(s, icon_image(head, s)) for s in ICO_SIZES])
    with open(STAMP, "w", encoding="ascii") as f:
        f.write(source_hash() + "\n")
    print("Logo files written to", ASSETS)
    del app


if __name__ == "__main__":
    main()
