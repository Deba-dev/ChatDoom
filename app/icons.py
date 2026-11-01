"""Small monochrome icons drawn in code (no icon font dependency)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def _pix(draw):
    pix = QPixmap(16, 16)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#e8e8ee"))
    pen.setWidthF(1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    draw(painter)
    painter.end()
    return QIcon(pix)


def edit_icon():
    def draw(p):
        p.drawLine(3, 13, 12, 4)
        p.drawLine(11, 3, 14, 6)
        p.drawLine(2, 14, 5, 11)
    return _pix(draw)


def nav_icon(index):
    drawers = (
        _nav_connect,
        _nav_chat,
        _nav_voice,
        _nav_mod,
        _nav_discord,
        _nav_pay,
        _nav_yt,
        _nav_obs,
        _nav_music,
        _nav_commands,
        _nav_tools,
    )
    if 0 <= index < len(drawers):
        return _pix(drawers[index])
    return QIcon()


def utility_icon(name):
    return _pix({"mute": _util_mute, "skip": _util_skip, "test": _util_mic}.get(name, lambda p: None))


def _nav_connect(p):
    p.drawEllipse(2, 6, 5, 5)
    p.drawEllipse(9, 6, 5, 5)
    p.drawLine(7, 8, 9, 8)


def _nav_chat(p):
    p.drawRoundedRect(2, 3, 12, 9, 2, 2)
    p.drawLine(5, 12, 7, 14)
    p.drawLine(7, 14, 9, 12)


def _nav_voice(p):
    p.drawLine(3, 10, 3, 6)
    p.drawLine(6, 12, 6, 4)
    p.drawLine(9, 9, 9, 7)
    p.drawLine(12, 11, 12, 5)


def _nav_mod(p):
    p.drawLine(8, 2, 3, 14)
    p.drawLine(8, 2, 13, 14)
    p.drawLine(5, 9, 11, 9)


def _nav_discord(p):
    p.drawLine(8, 2, 3, 5)
    p.drawLine(8, 2, 13, 5)
    p.drawLine(3, 5, 3, 11)
    p.drawLine(13, 5, 13, 11)
    p.drawLine(3, 11, 8, 14)
    p.drawLine(13, 11, 8, 14)


def _nav_pay(p):
    p.drawEllipse(8, 8, 6, 6)
    p.drawLine(8, 5, 8, 3)
    p.drawLine(11, 8, 13, 8)


def _nav_yt(p):
    p.drawRoundedRect(2, 5, 12, 8, 2, 2)
    p.drawLine(7, 7, 7, 11)
    p.drawLine(7, 7, 10, 9)
    p.drawLine(7, 11, 10, 9)


def _nav_obs(p):
    p.drawRect(2, 4, 12, 8)
    p.drawLine(5, 7, 8, 9)
    p.drawLine(8, 9, 11, 7)


def _util_mute(p):
    p.drawLine(3, 6, 3, 10)
    p.drawLine(5, 4, 5, 12)
    p.drawLine(7, 5, 7, 11)
    p.drawLine(9, 3, 9, 13)
    p.drawLine(11, 7, 14, 4)
    p.drawLine(11, 9, 14, 12)


def _util_skip(p):
    p.drawLine(5, 4, 11, 8)
    p.drawLine(5, 12, 11, 8)
    p.drawLine(12, 4, 12, 12)


def _util_mic(p):
    p.drawRoundedRect(6, 3, 4, 7, 2, 2)
    p.drawLine(8, 10, 8, 12)
    p.drawLine(5, 12, 11, 12)


def _nav_music(p):
    p.drawEllipse(3, 10, 4, 4)
    p.drawEllipse(10, 8, 4, 4)
    p.drawLine(7, 12, 7, 3)
    p.drawLine(14, 10, 14, 2)
    p.drawLine(7, 3, 14, 2)


def _nav_commands(p):
    p.drawRoundedRect(2, 3, 12, 10, 2, 2)
    p.drawLine(8, 5, 8, 9)
    p.drawPoint(8, 11)


def _nav_tools(p):
    for y, x in ((4, 10), (8, 5), (12, 9)):
        p.drawLine(2, y, 14, y)
        p.drawEllipse(x - 1, y - 1, 2, 2)
