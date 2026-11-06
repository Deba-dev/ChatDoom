"""Small monochrome icons drawn in code (no icon font dependency)."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def _pix(draw):
    pix = QPixmap(48, 48)                    # drawn large so the icons stay sharp when shown at any size
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(3, 3)
    pen = QPen(QColor("#ffffff"))
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
        _nav_alerts,
        _nav_loyalty,
        _nav_engage,
    )
    if 0 <= index < len(drawers):
        return _pix(drawers[index])
    return QIcon()


NAV_DRAWERS = {"connect": 0, "chat": 1, "voice": 2, "shield": 3, "discord": 4, "money": 5, "play": 6, "screen": 7, "music": 8,
               "commands": 9, "tools": 10}
PLATFORM_COLORS = {"youtube": ("#ff5a5f", "#d90429"), "twitch": ("#a970ff", "#6441a5"), "kick": ("#7dff4d", "#22b800")}


def _tile(size, c1, c2, round_share=0.27):
    pix = QPixmap(size * 2, size * 2)          # twice the size, for sharp edges on high-resolution screens
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * round_share, size * round_share)
    return pix, p


def platform_glyph(p, key, size, color=QColor("#ffffff")):
    """White platform symbol, centred in a square of the given size."""
    s = float(size)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    if key == "youtube":
        p.drawRoundedRect(QRectF(s * 0.18, s * 0.28, s * 0.64, s * 0.44), s * 0.12, s * 0.12)
        p.setBrush(QColor("#e11d2e"))
        p.drawPolygon(QPolygonF([QPointF(s * 0.43, s * 0.40), QPointF(s * 0.43, s * 0.60), QPointF(s * 0.61, s * 0.50)]))
    elif key == "twitch":
        path = QPainterPath()
        path.moveTo(s * 0.26, s * 0.20)
        for x, y in ((0.78, 0.20), (0.78, 0.56), (0.62, 0.72), (0.50, 0.72), (0.40, 0.82), (0.40, 0.72), (0.26, 0.72)):
            path.lineTo(s * x, s * y)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QColor("#6441a5"))
        p.drawRect(QRectF(s * 0.44, s * 0.32, s * 0.06, s * 0.20))
        p.drawRect(QRectF(s * 0.60, s * 0.32, s * 0.06, s * 0.20))
    elif key == "kick":
        path = QPainterPath()
        for i, (x, y) in enumerate(((0.24, 0.20), (0.42, 0.20), (0.42, 0.38), (0.54, 0.38), (0.54, 0.20), (0.76, 0.20), (0.76, 0.34),
                                    (0.64, 0.34), (0.64, 0.44), (0.54, 0.44), (0.54, 0.56), (0.64, 0.56), (0.64, 0.66), (0.76, 0.66),
                                    (0.76, 0.80), (0.54, 0.80), (0.54, 0.62), (0.42, 0.62), (0.42, 0.80), (0.24, 0.80))):
            (path.lineTo if i else path.moveTo)(s * x, s * y)
        path.closeSubpath()
        p.setBrush(QColor("#062b00"))
        p.drawPath(path)


def platform_tile(key, size=56):
    """Glossy rounded platform badge, like the app's home screen cards."""
    c1, c2 = PLATFORM_COLORS.get(key, ("#8b5cf6", "#5b21b6"))
    pix, p = _tile(size, c1, c2)
    platform_glyph(p, key, size)
    p.end()
    return pix


def stat_tile(name, colors, size=56):
    """Rounded colour badge with a white symbol for the stat cards."""
    pix, p = _tile(size, colors[0], colors[1], 0.30)
    pen = QPen(QColor("#ffffff"))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setWidthF(1.5)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen)
    k = size * 0.5 / 16.0
    p.translate(size * 0.25, size * 0.25)
    p.scale(k, k)
    {"layers": _stat_layers, "check": _stat_check, "power": _stat_power, "people": _stat_people, "star": _stat_star}.get(
        name, lambda q: _nav_by_name(name, q))(p)
    p.end()
    return pix


def _nav_by_name(name, p):
    drawers = (_nav_connect, _nav_chat, _nav_voice, _nav_mod, _nav_discord, _nav_pay, _nav_yt, _nav_obs, _nav_music, _nav_commands, _nav_tools)
    drawers[NAV_DRAWERS.get(name, 0)](p)


def _stat_layers(p):
    p.drawPolygon(QPolygonF([QPointF(8, 1.5), QPointF(15, 5), QPointF(8, 8.5), QPointF(1, 5)]))
    p.drawPolyline(QPolygonF([QPointF(1, 8), QPointF(8, 11.5), QPointF(15, 8)]))
    p.drawPolyline(QPolygonF([QPointF(1, 11), QPointF(8, 14.5), QPointF(15, 11)]))


def _stat_check(p):
    pen = p.pen()
    pen.setWidthF(2.4)
    p.setPen(pen)
    p.drawPolyline(QPolygonF([QPointF(2, 8.5), QPointF(6.5, 13), QPointF(14, 3.5)]))


def _stat_power(p):
    pen = p.pen()
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.drawArc(QRectF(2, 2.5, 12, 12), 125 * 16, -250 * 16 + 0)
    p.drawLine(QPointF(8, 0.5), QPointF(8, 7.5))


def _stat_people(p):
    p.drawEllipse(QRectF(5, 1.5, 6, 6))
    p.drawArc(QRectF(2, 9, 12, 11), 0, 180 * 16)


def _stat_star(p):
    p.drawPolygon(QPolygonF([QPointF(8, 1), QPointF(10, 6), QPointF(15, 6.3), QPointF(11.2, 9.6), QPointF(12.5, 14.6), QPointF(8, 11.9),
                             QPointF(3.5, 14.6), QPointF(4.8, 9.6), QPointF(1, 6.3), QPointF(6, 6)]))


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
    p.drawPolygon(QPolygonF([QPointF(8, 1.5), QPointF(13.5, 3.5), QPointF(13.5, 8), QPointF(12, 11.5), QPointF(8, 14.5), QPointF(4, 11.5),
                             QPointF(2.5, 8), QPointF(2.5, 3.5)]))
    p.drawPolyline(QPolygonF([QPointF(5.5, 8), QPointF(7.5, 10), QPointF(10.8, 6)]))


def _nav_discord(p):
    p.drawRoundedRect(QRectF(1.5, 3, 13, 10), 4.5, 4.5)
    pen = p.pen()
    p.setBrush(pen.color())
    p.drawEllipse(QPointF(5.6, 8), 0.9, 1.1)
    p.drawEllipse(QPointF(10.4, 8), 0.9, 1.1)
    p.setBrush(Qt.NoBrush)


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


def _nav_alerts(p):
    p.drawArc(4, 2, 8, 9, 0, 180 * 16)
    p.drawLine(4, 6, 4, 11)
    p.drawLine(12, 6, 12, 11)
    p.drawLine(2, 12, 14, 12)
    p.drawLine(7, 14, 9, 14)


def _nav_loyalty(p):
    p.drawEllipse(2, 2, 12, 12)
    p.drawLine(8, 5, 8, 11)
    p.drawLine(6, 7, 10, 7)
    p.drawLine(6, 9, 10, 9)


def _nav_engage(p):
    p.drawRoundedRect(2, 3, 12, 8, 2, 2)
    p.drawLine(5, 11, 4, 14)
    p.drawLine(5, 7, 7, 7)
    p.drawLine(9, 7, 11, 7)


def _nav_tools(p):
    for y, x in ((4, 10), (8, 5), (12, 9)):
        p.drawLine(2, y, 14, y)
        p.drawEllipse(x - 1, y - 1, 2, 2)
