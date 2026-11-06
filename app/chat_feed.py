"""The Live chat box: remembers every line so it can be filtered, finds which message was clicked, and draws picture emotes."""
import hashlib
import html
import re
import threading
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QTextCursor, QTextDocument
from PySide6.QtWidgets import QPushButton, QTextEdit

MAX_LINES = 1000
EMOTE_HOSTS = ("ggpht.com", "googleusercontent.com", "ytimg.com", "youtube.com", "jtvnw.net", "kick.com")
EMOTE_BYTES = 512 * 1024
EMOTE_PIXELS = 56
CLICK_SLOP = 4
SHOW_CHOICES = (("All messages", "all"), ("Chat only", "chat"), ("Paid and members", "paid"), ("Moderators", "mods"),
                ("Mentions and my words", "mentions"), ("New viewers", "new"), ("Skipped", "skipped"))


@dataclass
class Line:
    id: int
    html: str
    kind: str = "system"           # system | chat | skipped
    message: object = None
    stream: str = ""
    highlighted: bool = False
    new: bool = False
    under: list = field(default_factory=list)      # extra lines shown below it, like a translation


@dataclass
class ChatView:
    """What the streamer asked to see."""
    stream: str = ""
    show: str = "all"
    words: str = ""
    hide_skipped: bool = False

    def shows(self, line):
        filtered = self.stream or self.show != "all" or self.words
        if line.kind == "system":
            return not filtered
        if line.kind == "skipped" and self.hide_skipped and self.show != "skipped":
            return False
        if self.stream and line.stream != self.stream:
            return False
        m = line.message
        if self.show == "chat" and line.kind != "chat":
            return False
        if self.show == "paid" and not (m and m.kind in ("super", "member")):
            return False
        if self.show == "mods" and not (m and m.mod):
            return False
        if self.show == "mentions" and not line.highlighted:
            return False
        if self.show == "new" and not line.new:
            return False
        if self.show == "skipped" and line.kind != "skipped":
            return False
        if self.words:
            found = "%s %s" % (m.author, m.text) if m else ""
            return self.words.lower() in found.lower()
        return True


def allowed_emote(url):
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in EMOTE_HOSTS)


def mentions(text, words):
    low = (text or "").lower()
    return any(w and re.search(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", low) for w in words)


def with_emotes(text, emotes, picture):
    """Escapes text for the feed and swaps emote words for pictures. picture(url) gives the image source, or "" to leave the word."""
    safe = html.escape(text or "")
    if not emotes:
        return safe
    words = sorted(emotes, key=len, reverse=True)
    # :name: can touch other text. A plain word like Kappa must stand alone, or "Kappa" would match inside "Kappas".
    pattern = re.compile("|".join(re.escape(html.escape(w)) if w.startswith(":") else r"(?<!\S)" + re.escape(html.escape(w)) + r"(?!\S)" for w in words))
    plain = {html.escape(w): emotes[w] for w in words}

    def swap(match):
        source = picture(plain.get(match.group(0), ""))
        return '<img src="%s" width="%d" height="%d">' % (source, picture.size, picture.size) if source else match.group(0)
    return pattern.sub(swap, safe)


class EmoteStore(QObject):
    """Downloads emote pictures once, off the main thread."""
    ready = Signal(str, bytes)

    def __init__(self):
        super().__init__()
        self.names = {}
        self.size = 20

    def __call__(self, url):
        if not allowed_emote(url):
            return ""
        name = self.names.get(url)
        if name is None:
            name = self.names[url] = "emote:" + hashlib.sha1(url.encode()).hexdigest()[:16]
            threading.Thread(target=self._fetch, args=(url, name), daemon=True).start()
        return name

    def _fetch(self, url, name):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "CHATDOOM/1.0"})
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(EMOTE_BYTES + 1)
            if len(data) <= EMOTE_BYTES:
                self.ready.emit(name, data)
        except Exception:
            pass                                  # the blank space stays; chat itself is not affected


class ChatFeed(QTextEdit):
    """Live chat text. The hint is drawn in the full box so a large font wraps instead of being clipped."""
    picked = Signal(int, QPoint)                  # a line id and where the streamer clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hint = ""
        self.lines = deque(maxlen=MAX_LINES)
        self.by_id = {}
        self.view = ChatView()
        self.emotes = EmoteStore()
        self.emotes.ready.connect(self._emote_ready)
        self.after_redraw = None
        self._next = 1
        self._pressed = None
        self._blank = QImage(1, 1, QImage.Format.Format_ARGB32)
        self._blank.fill(QColor(0, 0, 0, 0))
        self.setMouseTracking(True)
        self.latest = QPushButton("Jump to latest", self)
        self.latest.setObjectName("primary")
        self.latest.setCursor(Qt.PointingHandCursor)
        self.latest.hide()
        self.latest.clicked.connect(self.scroll_to_end)
        self.verticalScrollBar().valueChanged.connect(self._scrolled)
        self.verticalScrollBar().rangeChanged.connect(lambda *_: self._scrolled())

    # ----- adding lines -----
    def append(self, text, kind="system", message=None, stream="", highlighted=False, new=False):
        line = Line(self._next, text, kind, message, stream, highlighted, new)
        self._next += 1
        if len(self.lines) == self.lines.maxlen:
            self.by_id.pop(self.lines[0].id, None)
        self.lines.append(line)
        self.by_id[line.id] = line
        if self.view.shows(line):
            self._draw(line)
        return line.id

    def _draw(self, line):
        super().append(line.html)
        self.document().lastBlock().setUserState(line.id)
        for extra in line.under:
            super().append(extra)
            self.document().lastBlock().setUserState(line.id)

    def add_under(self, line_id, text):
        """A second line below a message. Later messages may already be below it, so it goes in place."""
        line = self.by_id.get(line_id)
        if line is None:
            return
        line.under.append(text)
        block = self.document().lastBlock()
        while block.isValid() and block.userState() != line_id:
            block = block.previous()
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertBlock()
        cursor.insertHtml(text)
        cursor.block().setUserState(line_id)

    def replace_line(self, line_id, text):
        line = self.by_id.get(line_id)
        if line is not None:
            line.html = text
            self.redraw()

    def clear(self):
        self.lines.clear()
        self.by_id.clear()
        super().clear()

    def set_view(self, **changes):
        for key, value in changes.items():
            setattr(self.view, key, value)
        self.redraw()

    def redraw(self):
        super().clear()
        for line in self.lines:
            if self.view.shows(line):
                self._draw(line)
        if self.after_redraw:
            self.after_redraw()
        self.scroll_to_end()

    def plain_lines(self):
        """All remembered lines as text, for saving the chat to a file."""
        doc = QTextDocument()
        out = []
        for line in self.lines:
            doc.setHtml(line.html)
            out.append(doc.toPlainText())
        return out

    # ----- emotes -----
    def loadResource(self, kind, name):
        if name.scheme() == "emote":
            return self._blank
        return super().loadResource(kind, name)

    def _emote_ready(self, name, data):
        image = QImage.fromData(data)
        if image.isNull():
            return
        image = image.scaled(EMOTE_PIXELS, EMOTE_PIXELS, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    # ----- finding the clicked message -----
    def line_at(self, point):
        cursor = self.cursorForPosition(point)
        end = QTextCursor(cursor)
        end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        if point.y() > self.cursorRect(end).bottom():
            return None                           # the empty space below the last message
        line = self.by_id.get(cursor.block().userState())
        return line if line is not None and line.message is not None else None

    def mousePressEvent(self, event):
        self._pressed = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        at = event.position().toPoint()
        moved = self._pressed is None or (at - self._pressed).manhattanLength() > CLICK_SLOP
        if event.button() == Qt.LeftButton and not moved and not self.textCursor().hasSelection():
            line = self.line_at(at)
            if line:
                self.picked.emit(line.id, event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        over = self.line_at(event.position().toPoint()) is not None
        self.viewport().setCursor(Qt.PointingHandCursor if over else Qt.IBeamCursor)

    def contextMenuEvent(self, event):
        line = self.line_at(event.pos())
        if line:
            self.picked.emit(line.id, event.globalPos())
        else:
            super().contextMenuEvent(event)

    # ----- scrolling -----
    def _at_end(self):
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def scroll_to_end(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _scrolled(self, *_):
        self.latest.setVisible(not self._at_end())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.latest.adjustSize()
        self.latest.move((self.width() - self.latest.width()) // 2, self.height() - self.latest.height() - 12)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.hint or not self.document().isEmpty():
            return
        painter = QPainter(self.viewport())
        painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        painter.setFont(self.font())
        margin = int(self.document().documentMargin())
        painter.drawText(self.viewport().rect().adjusted(margin, margin, -margin, -margin), Qt.TextWordWrap | Qt.AlignTop, self.hint)
