"""Everything the streamer can do from the Live chat page: the click menu on a message, owner controls, filters and the send box."""
import html
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QVBoxLayout)

from . import translation
from .chat_feed import SHOW_CHOICES, mentions, with_emotes
from .commands import PLATFORM_NAMES
from .discord import run_bg
from .models import viewer_key
from .platforms import youtube_id
from .viewer_memory import short_date
from .voice_ui import VoicePicker

TIMEOUTS = (("1 minute", 60), ("5 minutes", 300), ("10 minutes", 600), ("1 hour", 3600), ("24 hours", 86400))
ALL_CHATS = "all"
ACCOUNT_TARGETS = ("youtube", "twitch", "kick")
YOUTUBE_REPLY_NOTE = "YouTube has no reply feature for apps, so this starts your message with @name."
TWITCH_MODES = (("Slow mode", "slow_mode"), ("Followers only", "follower_mode"), ("Subscribers only", "subscriber_mode"), ("Emote only", "emote_mode"))
TRANSLATE_NOTE_GAP = 60


def esc(text):
    return html.escape(str(text))


def compact(box, letters=8):
    """A long stream name must not stretch the window: the list still shows it in full when opened."""
    box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    box.setMinimumContentsLength(letters)


def span(colour, text):
    return "<span style='color:%s'>%s</span>" % (colour, text)


class ChatActions:
    """Mixed into the main window."""

    def _start_chat(self):
        self.reply_to = None
        self.bans = {}                 # viewer -> YouTube ban id: YouTube can only undo a ban by its id
        self.seen_viewers = set()
        self._translate_noted = 0.0
        self.feed.picked.connect(self.open_chat_menu)
        self.feed.after_redraw = self._apply_chat_style
        self.platform_auth.moderated.connect(self.on_moderated)
        self.bridge.done.connect(self._chat_done)

    # ---------- the bar above the chat ----------
    def _chat_toolbar(self):
        bar = QFrame()
        bar.setObjectName("tile")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 6, 12, 6)
        self.chat_stream = QComboBox()
        self.chat_stream.addItem("All streams", "")
        self.chat_stream.setToolTip("Show one stream's chat")
        self.chat_stream.currentIndexChanged.connect(lambda _: self.feed.set_view(stream=self.chat_stream.currentData() or ""))
        self.chat_show = QComboBox()
        for name, value in SHOW_CHOICES:
            self.chat_show.addItem(name, value)
        self.chat_show.currentIndexChanged.connect(lambda _: self.feed.set_view(show=self.chat_show.currentData()))
        compact(self.chat_stream)
        compact(self.chat_show)
        self.chat_search = QLineEdit()
        self.chat_search.setMinimumWidth(90)
        self.chat_search.setPlaceholderText("Search chat or a viewer")
        self.chat_search.textChanged.connect(lambda t: self.feed.set_view(words=t.strip()))
        self.translate_btn = QPushButton("Translate: off")
        self.translate_btn.setObjectName("quiet")
        self.translate_btn.setCheckable(True)
        self.translate_btn.setCursor(Qt.PointingHandCursor)
        self.translate_btn.setToolTip("Turn translation on or off. Choose the languages on the Voice page, under Translate.")
        self.translate_btn.toggled.connect(self.set_translation)
        options = QPushButton("Options")
        options.setObjectName("quiet")
        options.setCursor(Qt.PointingHandCursor)
        options.setMenu(self._chat_options_menu(options))
        row.addWidget(self.chat_stream)
        row.addWidget(self.chat_show)
        row.addWidget(self.chat_search, 1)
        row.addWidget(self.translate_btn)
        row.addWidget(options)
        self.feed.view.hide_skipped = bool(self.s.get("chat_hide_skipped"))
        self.sync_translate_button()
        return bar

    def _chat_options_menu(self, parent):
        menu = QMenu(parent)
        for text, key in (("Show the time", "chat_show_time"), ("Mark first-time chatters", "chat_mark_new"), ("Hide skipped messages", "chat_hide_skipped")):
            action = QAction(text, menu)
            action.setCheckable(True)
            action.setChecked(bool(self.s.get(key)))
            action.toggled.connect(lambda on, k=key: self._chat_option(k, on))
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction("Words to highlight...", self.edit_highlights)
        menu.addAction("Save chat to a file...", self.save_chat)
        menu.addAction("Clear the chat box", self.feed.clear)
        return menu

    def _chat_option(self, key, on):
        self.s.set(key, on)
        if key == "chat_hide_skipped":
            self.feed.set_view(hide_skipped=on)

    def edit_highlights(self):
        now = ", ".join(self.s.get("chat_highlights") or [])
        text, done = QInputDialog.getText(self, "Words to highlight", "Messages with these words stand out. Separate them with commas. Your own name is always included.", text=now)
        if done:
            self.s.set("chat_highlights", [w.strip() for w in text.split(",") if w.strip()])

    def save_chat(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save chat", "chat-%s.txt" % time.strftime("%Y-%m-%d-%H%M"), "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.feed.plain_lines()))

    def sync_translate_button(self):
        on = bool(self.s.get("translate_chat"))
        self.translate_btn.blockSignals(True)
        self.translate_btn.setChecked(on)
        self.translate_btn.blockSignals(False)
        self.translate_btn.setText("Translate: on" if on else "Translate: off")

    def set_translation(self, on):
        self.s.set("translate_chat", bool(on))
        self.sync_translate_button()
        if hasattr(self, "translate_switch") and self.translate_switch.isChecked() != bool(on):
            self.translate_switch.setChecked(bool(on))

    # ---------- writing messages into the feed ----------
    def _highlight_words(self):
        names = [self.platform_auth.display_name(p) for p in self.platform_auth.SUPPORTED]
        return [w for w in names + list(self.s.get("chat_highlights") or []) if w]

    def _stamp(self):
        return span("#8a93a8", time.strftime("%H:%M")) + " " if self.s.get("chat_show_time") else ""

    def feed_message(self, m, tag, amount, author, text, note=""):
        """One allowed message. Returns its line id. note: a short grey reason, e.g. blocked name."""
        key = viewer_key(m)
        new = key not in self.seen_viewers and m.platform != "test"
        self.seen_viewers.add(key)
        words = with_emotes(text, m.emotes, self.feed.emotes)
        marked = highlighted = mentions(m.text, self._highlight_words())
        star = span("#7cf0c0", "★ ") if new and self.s.get("chat_mark_new") else ""
        line = "%s%s%s <b>%s</b>%s: %s" % (star, self._stamp(), tag, esc(author), amount, words)
        if note:
            line += span("#5d667d", " <i>(%s)</i>" % esc(note))
        if marked:
            line = "<span style='background-color:rgba(255,210,77,0.18)'>%s</span>" % line
        line_id = self.feed.append(line, "chat", m, m.stream, highlighted, new)
        self._translate_line(line_id, m)
        return line_id

    def feed_skipped(self, m, tag, author, text, reason):
        line = span("#5d667d", "%s%s %s: %s <i>(skipped: %s)</i>" % (self._stamp(), tag, esc(author), with_emotes(text, m.emotes, self.feed.emotes), esc(reason)))
        return self.feed.append(line, "skipped", m, m.stream)

    def _translate_line(self, line_id, m, force=False):
        if not force and not (self.s.get("translate_chat") and self.s.get("translate_show")):
            return
        if not force and not (self.s.get("translate_others") or translation.script_language(m.text)):
            return                                # ordinary Latin-script chat: no thread, no cloud call
        settings = self.s
        run_bg(self.bridge, "feed:translate:%d" % line_id, lambda: self._translated(m.text, settings, force))

    @staticmethod
    def _translated(text, settings, force):
        words, source, done = translation.translate_message(text, settings, force)
        return {"text": words, "source": source, "done": done}

    def _chat_done(self, tag, result):
        if not tag.startswith("feed:translate:"):
            return
        if result.get("error"):
            if time.time() - self._translate_noted > TRANSLATE_NOTE_GAP:
                self._translate_noted = time.time()
                self.feed.append(span("#ffb020", "Translation unavailable (%s)." % esc(result["error"])))
            return
        if result.get("done"):
            self.feed.add_under(int(tag.rsplit(":", 1)[1]), span("#8ab4ff", "&nbsp;&nbsp;&#8627; %s <i>(%s)</i>" % (esc(result["text"]), esc(result.get("source") or ""))))

    # ---------- the click menu on a message ----------
    def _mod_target(self, m):
        """(YouTube video id or "", "") when the signed-in account can act on this message's chat, else (None, why not)."""
        name = PLATFORM_NAMES.get(m.platform, m.platform.title())
        if m.platform not in self.platform_auth.SUPPORTED:
            return None, "Owner controls need a platform chat."
        if not self.platform_auth.is_connected(m.platform):
            return None, "Sign in to %s on the Connect page for owner controls." % name
        card = self.cards.get(m.stream) or self.extra_cards.get(m.stream) or self.cards.get(m.platform)
        if m.platform == "youtube":
            video = youtube_id(card.edit.text()) if card else ""
            return (video, "") if video else (None, "This stream has no video link.")
        login = self.s.get("platform_%s_login" % m.platform) or ""
        channel = card.edit.text().strip().lstrip("#").lower() if card else ""
        if login and channel == login.lower() or not login and m.stream in ("", m.platform):
            return "", ""
        return None, "Owner controls work on your own %s channel." % name

    def open_chat_menu(self, line_id, where):
        line = self.feed.by_id.get(line_id)
        if line is not None and line.message is not None:
            self.chat_menu = self.build_chat_menu(line)
            self.chat_menu.popup(where)

    def build_chat_menu(self, line):
        m = line.message
        menu = QMenu(self)
        head = menu.addAction("%s  (%s)" % (m.author, self._tag(m)))
        head.setEnabled(False)
        menu.addSeparator()
        video, why = self._mod_target(m)
        owner = video is not None
        protected = bool(m.mod)
        can_reply = self._reply_target(m)[0] is not None
        reply = menu.addAction("Reply", lambda: self.start_reply(m))
        reply.setEnabled(can_reply)
        if m.platform == "youtube":
            reply.setToolTip(YOUTUBE_REPLY_NOTE)
        remove = menu.addAction("Remove message", lambda: self.mod_action(m, "delete", line_id=line.id))
        timeout = menu.addMenu("Time out")
        for name, seconds in TIMEOUTS:
            timeout.addAction(name, lambda s=seconds, n=name: self.mod_action(m, "timeout", seconds=s, label=n))
        timeout.addAction("Custom...", lambda: self.custom_timeout(m))
        ban = menu.addAction("Hide user from channel" if m.platform == "youtube" else "Ban", lambda: self.confirm_ban(m))
        undo = menu.addAction("Undo time-out or ban", lambda: self.undo_ban(m))
        if m.platform == "youtube":
            undo.setEnabled(owner and viewer_key(m) in self.bans)
            menu.addAction("Make moderator", lambda: self.confirm_moderator(m)).setEnabled(owner and not protected)
        else:
            undo.setEnabled(owner)
        if m.platform == "twitch":
            menu.addAction("Shoutout", lambda: self.mod_action(m, "shoutout")).setEnabled(owner)
        remove.setEnabled(owner and not protected)
        timeout.setEnabled(owner and not protected)
        ban.setEnabled(owner and not protected)
        if why:
            note = menu.addAction(why)
            note.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Translate this message", lambda: self._translate_line(line.id, m, force=True))
        menu.addAction("Read it aloud", lambda: self.speaker.say(m.author, m.text, "", self._who(m)))
        muted = viewer_key(m) in (self.s.get("chat_muted") or [])
        menu.addAction("Let the voice read this viewer again" if muted else "Stop reading this viewer", lambda: self.toggle_muted(m))
        menu.addAction("Choose a voice for this viewer...", lambda: self.pick_viewer_voice(m))
        menu.addAction("Viewer details...", lambda: self.viewer_details(m))
        has_note = bool(self.tools.memory.note(viewer_key(m)))
        menu.addAction("Edit note..." if has_note else "Add note...", lambda: self.edit_note(m))
        menu.addAction("Forget this viewer...", lambda: self.forget_viewer(m))
        menu.addSeparator()
        menu.addAction("Copy message", lambda: QGuiApplication.clipboard().setText(m.text))
        menu.addAction("Copy name", lambda: QGuiApplication.clipboard().setText(m.author))
        return menu

    def _who(self, m):
        return {"platform": m.platform, "mod": bool(m.mod), "paid": m.kind == "super", "member": m.kind == "member", "emotes": m.emotes}

    def start_reply(self, m):
        self.reply_to = m
        self._select_target(m.platform, m.stream)
        self.message_edit.setPlaceholderText("Replying to %s" % m.author)
        if m.platform == "youtube":
            self.message_edit.setText("@%s " % m.author.lstrip("@"))
        self.reply_cancel.show()
        self.message_edit.setFocus()

    def cancel_reply(self):
        self.reply_to = None
        self.reply_cancel.hide()
        self.message_edit.setPlaceholderText("Sign in, then type a chat message...")

    def mod_action(self, m, action, line_id=None, label="", **fields):
        video, why = self._mod_target(m)
        if video is None:
            self.feed.append(span("#ff8a5c", esc(why)))
            return
        self.platform_auth.moderate(m.platform, action, {"message": m, "line": line_id, "label": label}, videoId=video, userId=m.uid, messageId=m.event_id,
                                    text=m.text, **fields)

    def custom_timeout(self, m):
        minutes, done = QInputDialog.getInt(self, "Time out %s" % m.author, "Minutes", 15, 1, 1440)
        if done:
            self.mod_action(m, "timeout", seconds=minutes * 60, label="%d minutes" % minutes)

    def _sure(self, title, text):
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def confirm_ban(self, m):
        if self._sure("Ban %s?" % m.author, "%s will not be able to chat until you unban them." % m.author):
            self.mod_action(m, "ban")

    def confirm_moderator(self, m):
        if self._sure("Make %s a moderator?" % m.author, "They will be able to remove messages and time out viewers in your chat."):
            self.mod_action(m, "addMod")

    def undo_ban(self, m):
        self.mod_action(m, "unban", banId=self.bans.get(viewer_key(m), ""))

    def on_moderated(self, info, result):
        m, action = info.get("message"), info.get("action")
        if result.get("error"):
            self.feed.append(span("#ff8a5c", "Could not do that: %s" % esc(result["error"])))
            return
        name = m.author if m else "chat"
        words = {"delete": "Removed %s's message" % name, "timeout": "Timed out %s for %s" % (name, info.get("label") or "a while"), "ban": "Banned %s" % name,
                 "unban": "Undid the time-out or ban on %s" % name, "addMod": "%s is now a moderator" % name, "shoutout": "Gave %s a shoutout" % name,
                 "clear": "Cleared chat", "chatMode": "Chat mode changed", "announce": "Announcement sent", "endPoll": "Poll ended"}.get(action, "Done")
        self.feed.append(span("#7cf0c0", "&raquo; " + esc(words)))
        if m and action in ("timeout", "ban") and result.get("banId"):
            self.bans[viewer_key(m)] = result["banId"]
        elif m and action == "unban":
            self.bans.pop(viewer_key(m), None)
        line = self.feed.by_id.get(info.get("line"))
        if action == "delete" and line is not None:
            self.feed.replace_line(line.id, span("#5d667d", "<s>%s</s> <i>(removed)</i>" % line.html))

    def toggle_muted(self, m):
        muted = list(self.s.get("chat_muted") or [])
        key = viewer_key(m)
        if key in muted:
            muted.remove(key)
        else:
            muted.append(key)
        self.s.set("chat_muted", muted[-500:])

    def pick_viewer_voice(self, m):
        dialog = QDialog(self)
        dialog.setWindowTitle("Voice for %s" % m.author)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("This viewer's messages always use this voice."))
        saved = dict(self.s.get("viewer_voices") or {})
        key = m.author.lower()
        picker = VoicePicker(self.speaker, saved.get(key, ""), empty="Normal voice")
        layout.addWidget(picker)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            if picker.value():
                saved[key] = picker.value()
            else:
                saved.pop(key, None)
            self.s.set("viewer_voices", saved)

    def viewer_details(self, m):
        key = viewer_key(m)
        said = [line.message.text for line in self.feed.lines if line.message is not None and viewer_key(line.message) == key]
        lines = ["Platform: %s" % PLATFORM_NAMES.get(m.platform, m.platform), "Messages this session: %d" % len(said)]
        if self.s.get("points_on"):
            lines.append("%s: %d" % (str(self.s.get("points_name")).title(), self.tools.points.balance(key)))
        if self.s.get("levels_on"):
            lines.append("Level: %d" % self.tools.points.level(key))
        r = self.tools.memory.record(key)
        if r:
            lines.append("Streams chatted in: %d" % int(r.get("streams") or 0))
            if r.get("first_seen"):
                lines.append("First seen: %s" % short_date(r["first_seen"]))
            if r.get("note"):
                lines.append("Your note: %s" % r["note"])
        lines += ["", "Latest messages:"] + said[-5:]
        QMessageBox.information(self, m.author, "\n".join(lines))

    def edit_note(self, m):
        """A private note about a viewer, shown on their card when they come back. Only the streamer sees it."""
        key = viewer_key(m)
        text, ok = QInputDialog.getText(self, "Note about %s" % m.author,
                                        "Only you see this. It shows on %s's card when they come back:" % m.author,
                                        QLineEdit.Normal, self.tools.memory.note(key))
        if ok:
            self.tools.memory.set_note(key, text, m.author)
            self.feed.append("<span style='color:#8a93a8'>%s</span>" % esc("Note saved for %s." % m.author if text.strip() else "Note removed for %s." % m.author))

    def forget_viewer(self, m):
        ask = QMessageBox.question(self, "Forget this viewer", "Forget %s? Their note, stream count and first-seen date are deleted, "
                                   "and they are welcomed as new next time. Points are kept." % m.author)
        if ask == QMessageBox.Yes:
            self.tools.forget_viewer(viewer_key(m))
            self.feed.append("<span style='color:#8a93a8'>%s</span>" % esc("Forgot %s." % m.author))

    # ---------- where the send box posts ----------
    def _target_label(self, platform, key=""):
        name = PLATFORM_NAMES[platform]
        if not self.platform_auth.is_connected(platform):
            return name + " — sign-in needed"
        return "%s — %s" % (name, self.stream_name(key or platform) or self.platform_auth.display_name(platform) or "signed in")

    def _streams_changed(self):
        """A stream was found, ended or renamed: refresh everything that shows stream names."""
        self._refresh_targets()
        self._refresh_stream_filter()

    def _refresh_targets(self):
        if not hasattr(self, "action_platform"):
            return
        box = self.action_platform
        keep = (box.currentData(), box.currentData(Qt.UserRole + 1))
        box.blockSignals(True)
        box.clear()
        box.addItem("All my chats", ALL_CHATS)
        for platform in ACCOUNT_TARGETS:
            box.addItem(self._target_label(platform), platform)
            box.setItemData(box.count() - 1, platform, Qt.UserRole + 1)
        for card in self.extra_cards.values():
            if card.platform() == "youtube" and card.edit.text().strip():
                box.addItem(self._target_label("youtube", card.key), "youtube")
                box.setItemData(box.count() - 1, card.key, Qt.UserRole + 1)
        at = next((i for i in range(box.count()) if (box.itemData(i), box.itemData(i, Qt.UserRole + 1)) == keep), -1)
        box.setCurrentIndex(at if at >= 0 else max(0, box.findData("youtube")))
        box.blockSignals(False)
        self._action_platform_changed()

    def _refresh_stream_filter(self):
        if not hasattr(self, "chat_stream"):
            return
        box = self.chat_stream
        keep = box.currentData()
        box.blockSignals(True)
        box.clear()
        box.addItem("All streams", "")
        for key, card in list(self.cards.items()) + list(self.extra_cards.items()):
            if card.source.running or key == keep:
                platform = card.platform() if hasattr(card, "platform") else key
                name = self.stream_name(key)
                box.addItem("%s %s" % (PLATFORM_NAMES[platform], name) if name else self._link_name(key, platform), key)
        box.setCurrentIndex(max(0, box.findData(keep)))
        box.blockSignals(False)

    def _link_name(self, key, platform):
        card = self.extra_cards.get(key)
        return "%s %s" % (PLATFORM_NAMES[platform], card.label.text().strip() or "added stream") if card else PLATFORM_NAMES[platform]

    def _select_target(self, platform, key):
        box = self.action_platform
        wanted = key if key in self.extra_cards else platform
        for i in range(box.count()):
            if box.itemData(i, Qt.UserRole + 1) == wanted:
                box.setCurrentIndex(i)
                return

    def _target_video(self):
        key = self.action_platform.currentData(Qt.UserRole + 1)
        card = self.extra_cards.get(key)
        return card.edit.text().strip() if card else ""

    def send_typed(self):
        text = self.message_edit.text().strip()
        if not text:
            return
        platform = self.action_platform.currentData()
        if platform == ALL_CHATS:
            self._broadcast(text)
        else:
            reply = self.reply_to if self.reply_to is not None and self.reply_to.platform == platform else None
            self.platform_auth.send_message(platform, text, self._target_video(), reply_to=reply.event_id if reply and platform != "youtube" else "")
        self.message_edit.clear()
        self.cancel_reply()

    # ---------- chat controls ----------
    def _chat_controls_menu(self):
        menu = QMenu(self)
        platform = self.action_platform.currentData()
        end = menu.addAction("End my poll", lambda: self.platform_auth.end_poll(platform, {"action": "endPoll"}))
        end.setEnabled(platform in self.platform_auth.polls)
        if platform == "twitch":
            menu.addSeparator()
            for name, key in TWITCH_MODES:
                sub = menu.addMenu(name)
                sub.addAction("Turn on", lambda k=key: self._twitch_mode(k, True))
                sub.addAction("Turn off", lambda k=key: self._twitch_mode(k, False))
            menu.addAction("Send an announcement...", self._twitch_announce)
            menu.addAction("Clear all chat...", self._twitch_clear)
        else:
            note = menu.addAction("%s does not offer chat modes to apps" % (PLATFORM_NAMES.get(platform) or "This choice"))
            note.setEnabled(False)
        return menu

    def _show_chat_controls(self):
        self.controls_menu = self._chat_controls_menu()
        self.controls_menu.popup(self.chat_controls_btn.mapToGlobal(self.chat_controls_btn.rect().topLeft()))

    def _twitch_mode(self, key, on):
        settings = {key: on}
        if key == "slow_mode" and on:
            seconds, done = QInputDialog.getInt(self, "Slow mode", "Seconds between messages", 30, 3, 120)
            if not done:
                return
            settings["slow_mode_wait_time"] = seconds
        self.platform_auth.moderate("twitch", "chatMode", {}, settings=settings)

    def _twitch_announce(self):
        text, done = QInputDialog.getText(self, "Announcement", "Twitch shows this as a highlighted message.")
        if done and text.strip():
            self.platform_auth.moderate("twitch", "announce", {}, text=text.strip())

    def _twitch_clear(self):
        if self._sure("Clear all chat?", "This removes every message from your Twitch chat for all viewers."):
            self.platform_auth.moderate("twitch", "clear", {})
