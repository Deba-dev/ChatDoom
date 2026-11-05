"""Commands page: make your own !commands, and memes that viewers play with !name."""
import html
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .commands import MEME_IMAGES, MEME_SOUNDS, VARIABLES, clean_name, import_file
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import FormScrollArea, bind_switch, field_row, hrow, info_box, option_switch_row, section_card

MODES = (("Reply in chat", "reply"), ("Read aloud", "speak"), ("Reply in chat and read aloud", "both"))
WHO = (("Everyone", False), ("Moderators and the streamer", True))
MAX_REPLY = 400


def _combo(options, current):
    box = QComboBox()
    for text, value in options:
        box.addItem(text, value)
    box.setCurrentIndex(max(0, box.findData(current)))
    return box


def _button(text, kind="quiet"):
    btn = QPushButton(text)
    btn.setObjectName(kind)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


class _ItemDialog(QDialog):
    """Shared name / who / cooldown fields and checks for the command and meme editors."""

    def __init__(self, parent, title, item, taken):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        self.item, self.taken = dict(item or {}), taken
        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(8)
        self.name = QLineEdit(clean_name(self.item.get("name")))
        self.name.setMaxLength(31)
        self.name.setPlaceholderText("name")
        bang = QLabel("!")
        bang.setObjectName("settingName")
        self.lay.addWidget(field_row("Command", "One word that viewers type after !. Letters, numbers, - and _.", hrow(bang, self.name)))

    def showEvent(self, event):
        super().showEvent(event)
        need = self.lay.totalHeightForWidth(self.width())        # wrapped hints are taller than the plain size hint says
        if need > self.height():
            self.resize(self.width(), need)

    def finish(self, cooldown):
        self.who = _combo(WHO, bool(self.item.get("mods_only")))
        self.lay.addWidget(field_row("Who can use it", "Moderators and the streamer also skip cooldowns.", self.who))
        self.cooldown = QSpinBox()
        self.cooldown.setRange(0, 3600)
        self.cooldown.setSuffix(" s")
        self.cooldown.setValue(int(self.item.get("cooldown", cooldown)))
        self.lay.addWidget(field_row("Cooldown", "Time before anyone can use it again.", self.cooldown))
        self.error = QLabel("")
        self.error.setStyleSheet("color:#ff8fa3;")
        self.error.setWordWrap(True)
        self.lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.lay.addWidget(buttons)

    def _check_name(self):
        name = clean_name(self.name.text())
        if not name:
            return self._fail("Type a command name, like discord or bruh (no spaces).")
        if name in self.taken:
            return self._fail("!%s is already used by another command or meme." % name)
        return name

    def _fail(self, text):
        self.error.setText(text)
        return ""

    def _common(self, name):
        self.item.update(name=name, mods_only=bool(self.who.currentData()), cooldown=self.cooldown.value())


class CommandDialog(_ItemDialog):
    def __init__(self, parent, item, taken):
        super().__init__(parent, "Edit command" if item else "New command", item, taken)
        self.response = QPlainTextEdit(self.item.get("response", ""))
        self.response.setPlaceholderText("Join our Discord: https://discord.gg/... see you there {user}!")
        self.response.setFixedHeight(84)
        self.lay.addWidget(field_row("Response", "What the command answers. You can use " +
                                     ", ".join(v for v, _ in VARIABLES) + ".", self.response))
        self.mode = _combo(MODES, self.item.get("mode") or "reply")
        self.lay.addWidget(field_row("Answer by", "Chat replies need a signed-in account on the Connect page, or the YouTube bot.", self.mode))
        self.finish(5)

    def _save(self):
        name = self._check_name()
        if not name:
            return
        text = self.response.toPlainText().strip()
        if not text:
            return self._fail("Type the response.")
        if len(text) > MAX_REPLY:
            return self._fail("Keep the response under %d characters (it is %d)." % (MAX_REPLY, len(text)))
        self._common(name)
        self.item.update(response=text, mode=self.mode.currentData())
        self.accept()


class MemeDialog(_ItemDialog):
    def __init__(self, parent, item, taken, memes_dir):
        super().__init__(parent, "Edit meme" if item else "New meme", item, taken)
        self.memes_dir = memes_dir
        self.picked = {"sound": self.item.get("sound", ""), "image": self.item.get("image", "")}   # file name in the folder, or a new full path
        self.text = QLineEdit(self.item.get("text", ""))
        self.text.setMaxLength(200)
        self.text.setPlaceholderText("Bruh moment! (optional)")
        self.lay.addWidget(field_row("Line to read aloud", "The voice reads it after the sound; it is also the caption on the meme overlay. "
                                     "{user} works here too.", self.text))
        self.file_labels = {}
        for key, title, note, kinds in (
                ("sound", "Sound clip", "MP3, WAV, OGG, M4A... played through CHATDOOM, so OBS hears it like the voice. Up to 45 seconds.", MEME_SOUNDS),
                ("image", "Picture or GIF", "PNG, JPG, GIF or WEBP, shown on the /meme overlay in OBS.", MEME_IMAGES)):
            label = QLabel()
            label.setObjectName("settingNote")
            choose = _button("Choose...")
            choose.clicked.connect(lambda _=False, k=key, t=title, x=kinds: self._pick(k, t, x))
            clear = _button("Remove")
            clear.clicked.connect(lambda _=False, k=key: self._set_file(k, ""))
            self.file_labels[key] = label
            self.lay.addWidget(field_row(title, note, hrow(label, choose, clear)))
            label.parentWidget().layout().setStretchFactor(label, 1)
            self._set_file(key, self.picked[key])
        self.cost = QSpinBox()
        self.cost.setRange(0, 1000000)
        self.cost.setSuffix(" points")
        self.cost.setValue(int(self.item.get("cost") or 0))
        self.lay.addWidget(field_row("Cost", "Loyalty points a viewer spends to play it (0 = free). Moderators play for free.", self.cost))
        self.finish(15)

    def _set_file(self, key, value):
        self.picked[key] = value
        self.file_labels[key].setText(os.path.basename(value) if value else "None")

    def _pick(self, key, title, kinds):
        pattern = " ".join("*" + k for k in kinds)
        path, _ = QFileDialog.getOpenFileName(self, "Choose a " + title.lower(), "", "%s (%s)" % (title, pattern))
        if path:
            self._set_file(key, path)

    def _save(self):
        name = self._check_name()
        if not name:
            return
        if not (self.text.text().strip() or self.picked["sound"] or self.picked["image"]):
            return self._fail("Add a sound, a picture or a line to read (any one is enough).")
        files = {}
        for key, value in self.picked.items():
            if value and os.path.isabs(value):         # a new file picked in this dialog: copy it into the memes folder
                try:
                    files[key] = import_file(value, self.memes_dir)
                except OSError as error:
                    return self._fail("Could not copy %s: %s" % (os.path.basename(value), error))
            else:
                files[key] = value
        self._common(name)
        self.item.update(text=self.text.text().strip(), sound=files["sound"], image=files["image"], cost=self.cost.value())
        self.accept()


class CommandsPage(FormScrollArea):
    def __init__(self, settings, engine, on_test):
        super().__init__()
        self.s, self.engine, self.on_test = settings, engine, on_test
        inner = QWidget()
        inner.setObjectName("page")
        self.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 8, 12, 12)
        lay.setSpacing(14)
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]

        c, cl = section_card("Chat commands", "Viewers type !name in any connected chat. Command messages are never read aloud themselves.")
        cl.addWidget(option_switch_row("Custom commands", "Answer your own !commands, plus !commands which lists them all.",
                                       bind_switch(self.s, "commands_on", accent)))
        cl.addWidget(option_switch_row("Memes", "Let viewers play memes with !name, and list them with !memes.",
                                       bind_switch(self.s, "memes_on", accent)))
        cl.addWidget(info_box("Chat replies are posted with the account you signed in with on the Connect page. YouTube works for your main and "
                              "added YouTube streams; Twitch replies go to your own channel. Kick cannot be replied to yet, so use "
                              "<b>Read aloud</b> for those viewers.", "Where replies go"))
        lay.addWidget(c)

        c, cl = section_card("Custom commands", "Like Nightbot: a fixed answer for things viewers keep asking.")
        self.cmd_list = QVBoxLayout()
        self.cmd_list.setSpacing(4)
        cl.addLayout(self.cmd_list)
        add = _button("Add command", "primary")
        add.clicked.connect(lambda: self.edit_command(None))
        cl.addWidget(hrow(add))
        cl.addWidget(info_box("<br>".join("<b>%s</b> — %s" % (html.escape(v), html.escape(d)) for v, d in VARIABLES), "Words you can use in a response"))
        lay.addWidget(c)

        c, cl = section_card("Memes", "A viewer types !name: CHATDOOM plays the sound, shows the picture on the /meme overlay (OBS overlays page) "
                                      "and reads the line aloud.")
        self.meme_list = QVBoxLayout()
        self.meme_list.setSpacing(4)
        cl.addLayout(self.meme_list)
        add = _button("Add meme", "primary")
        add.clicked.connect(lambda: self.edit_meme(None))
        folder = _button("Open memes folder")
        folder.clicked.connect(lambda: (os.makedirs(self.engine.memes_dir, exist_ok=True),
                                        QDesktopServices.openUrl(QUrl.fromLocalFile(self.engine.memes_dir))))
        cl.addWidget(hrow(add, folder))
        gap = QSpinBox()
        gap.setRange(0, 600)
        gap.setSuffix(" s")
        gap.setValue(int(self.s.get("meme_gap")))
        gap.valueChanged.connect(lambda v: self.s.set("meme_gap", v))
        cl.addWidget(field_row("Gap between memes", "After any meme plays, other memes wait this long so chat cannot spam them.", gap))
        lay.addWidget(c)
        lay.addStretch(1)
        self.refresh()

    # ---------- lists ----------
    def refresh(self):
        for box, kind in ((self.cmd_list, "commands"), (self.meme_list, "memes")):
            while box.count():
                w = box.takeAt(0).widget()
                if w is not None:
                    w.deleteLater()
            items = self.engine.items(kind)
            if not items:
                empty = QLabel("No commands yet." if kind == "commands" else "No memes yet.")
                empty.setObjectName("settingNote")
                box.addWidget(empty)
            for item in items:
                box.addWidget(self._row(kind, item))

    def _row(self, kind, item):
        name = clean_name(item.get("name"))
        if kind == "commands":
            mode = dict((v, t) for t, v in MODES).get(item.get("mode") or "reply", "")
            detail = "%s · %s" % (item.get("response", ""), mode)
        else:
            parts = [("♪ " + item["sound"]) if item.get("sound") else "", ("▣ " + item["image"]) if item.get("image") else "",
                     ("“%s”" % item["text"]) if item.get("text") else ""]
            detail = "  ".join(p for p in parts if p)
        extra = " · mods only" if item.get("mods_only") else ""
        if item.get("cost"):
            extra += " · %d points" % int(item["cost"])
        if item.get("uses"):
            extra += " · used %d×" % int(item["uses"])
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)
        text = QLabel("<b>!%s</b> &nbsp;<span style='opacity:.7'>%s%s</span>" % (html.escape(name), html.escape(detail[:140]), html.escape(extra)))
        text.setTextFormat(Qt.RichText)
        text.setWordWrap(True)
        lay.addWidget(text, 1)
        test = _button("Test")
        test.setToolTip("Run it as if a moderator typed !%s (no chat reply is sent)" % name)
        test.clicked.connect(lambda _=False, n=name: self.on_test(n))
        edit = _button("Edit")
        edit.clicked.connect(lambda _=False, i=item: self.edit_command(i) if kind == "commands" else self.edit_meme(i))
        delete = _button("Delete", "danger")
        delete.clicked.connect(lambda _=False, n=name: self.delete(kind, n))
        for b in (test, edit, delete):
            lay.addWidget(b, 0, Qt.AlignTop)
        row.name = name
        return row

    # ---------- editing ----------
    def _taken(self, keep):
        names = {clean_name(x.get("name")) for kind in ("commands", "memes") for x in self.engine.items(kind)}
        names.discard(keep)
        return names

    def edit_command(self, item):
        dialog = CommandDialog(self, item, self._taken(clean_name((item or {}).get("name"))))
        if dialog.exec() == QDialog.Accepted:
            self._store("commands", item, dialog.item)

    def edit_meme(self, item):
        dialog = MemeDialog(self, item, self._taken(clean_name((item or {}).get("name"))), self.engine.memes_dir)
        if dialog.exec() == QDialog.Accepted:
            self._store("memes", item, dialog.item)

    def _store(self, kind, old, new):
        items = self.engine.items(kind)
        old_name = clean_name((old or {}).get("name"))
        at = next((i for i, x in enumerate(items) if old and clean_name(x.get("name")) == old_name), None)
        if at is None:
            items.append(new)
        else:
            items[at] = new
        self.s.set(kind, items)
        if kind == "memes" and old:
            self._drop_files(old, items)
        self.refresh()

    def delete(self, kind, name):
        items = self.engine.items(kind)
        gone = [x for x in items if clean_name(x.get("name")) == name]
        items = [x for x in items if clean_name(x.get("name")) != name]
        self.s.set(kind, items)
        if kind == "memes":
            for old in gone:
                self._drop_files(old, items)
        self.refresh()

    def _drop_files(self, old, items):
        """Remove a meme's copied files once no meme uses them any more."""
        used = {x.get(k) for x in items for k in ("sound", "image")}
        for key, kinds in (("sound", MEME_SOUNDS), ("image", MEME_IMAGES)):
            path = self.engine.file(old.get(key), kinds)
            if path and old.get(key) not in used:
                try:
                    os.remove(path)
                except OSError:
                    pass
