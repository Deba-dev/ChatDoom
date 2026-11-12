"""The Voice page: the picker for all neural voices and the page's tabs."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSlider, QWidget

from . import translation, voices
from .discord import run_bg

ROLE_VOICES = (("Paid messages", "Super Chats, Bits and tips.", "voice_paid"), ("Members", "Membership messages.", "voice_member"),
               ("Moderators", "Your moderators and you.", "voice_mod"), ("Alerts and command answers", "Lines CHATDOOM says itself.", "voice_alerts"))
PLATFORM_VOICES = (("YouTube chat", "voice_youtube"), ("Twitch chat", "voice_twitch"), ("Kick chat", "voice_kick"))
TEST_LINES = (("Russian", "Привет всем, отличный стрим"), ("Korean", "안녕하세요 방송 재미있어요"), ("Chinese", "大家好，今天的直播很棒"), ("Japanese", "こんにちは、配信ありがとう"))
SAME = "Same as the normal voice"


class VoicePicker(QWidget):
    """Language, then male or female, then the voice, with a button to hear it. value() is the voice id, or "" for the empty choice."""
    changed = Signal(str)

    def __init__(self, speaker, voice="", empty=""):
        super().__init__()
        self.speaker, self.empty = speaker, empty
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.language = QComboBox()
        if empty:
            self.language.addItem(empty, "")
        for name in voices.languages():
            self.language.addItem(name, name)
        self.gender = QComboBox()
        for name, value in voices.GENDERS:
            self.gender.addItem(name, value)
        self.voice = QComboBox()
        self.play = QPushButton("Play")
        self.play.setObjectName("quiet")
        self.play.setCursor(Qt.PointingHandCursor)
        self.play.clicked.connect(lambda: self.value() and self.speaker.preview(self.value()))
        row.addWidget(self.language, 3)
        row.addWidget(self.gender, 1)
        row.addWidget(self.voice, 3)
        row.addWidget(self.play)
        self.language.setCurrentIndex(max(0, self.language.findData(voices.language_of(voice))))
        self._fill(voice)
        self.language.currentIndexChanged.connect(lambda _: self._fill(""))
        self.gender.currentIndexChanged.connect(lambda _: self._fill(self.value()))
        self.voice.currentIndexChanged.connect(lambda _: self.changed.emit(self.value()))

    def _fill(self, wanted):
        language = self.language.currentData()
        self.voice.blockSignals(True)
        self.voice.clear()
        for voice in voices.in_language(language, self.gender.currentData()) if language else []:
            self.voice.addItem(voices.label(voice), voice)
        self.voice.setCurrentIndex(max(0, self.voice.findData(wanted)))
        self.voice.blockSignals(False)
        chosen = bool(language)
        self.gender.setEnabled(chosen)
        self.voice.setEnabled(chosen)
        self.play.setEnabled(chosen)
        self.changed.emit(self.value())

    def value(self):
        return self.voice.currentData() or ""


def bound_picker(w, key, empty=""):
    picker = VoicePicker(w.speaker, w.s.get(key) or "", empty)
    picker.changed.connect(lambda v: w.s.set(key, v) if v or empty else None)
    return picker


def _button(text, kind="quiet"):
    b = QPushButton(text)
    b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    return b


def _voices_tab(w):
    engine, lay = w._voice_section("Voice engine", "Choose the speech engine used to read your chat.")
    eng = QComboBox()
    eng.addItem("Neural voices (online, best quality)", "neural")
    eng.addItem("Windows voices (offline)", "windows")
    eng.setCurrentIndex(max(0, eng.findData(w.s.get("engine"))))
    eng.currentIndexChanged.connect(lambda _: w.s.set("engine", eng.currentData()))
    lay.addWidget(w._voice_field("Voice engine", "Neural voices need the internet. Windows voices work offline.", eng))
    win = QComboBox()
    win.addItem("Choose by language", "")
    for name in w.speaker.windows_voices():
        win.addItem(name, name)
    win.setCurrentIndex(max(0, win.findData(w.s.get("win_voice"))))
    win.currentIndexChanged.connect(lambda _: w.s.set("win_voice", win.currentData()))
    lay.addWidget(w._voice_field("Windows voice", "Used when the Windows engine is on, and as the backup if the internet drops.", win))

    languages, lay = w._voice_section("Main voices", "%d neural voices in %d languages and regions. Pick one, then press Play to hear it." % (len(voices.BY_ID), len(voices.languages())))
    lay.addWidget(w._voice_field("Hindi", "For messages in Devanagari.", bound_picker(w, "hi_voice")))
    lay.addWidget(w._voice_field("Hinglish / English", "For messages in Latin script.", bound_picker(w, "en_voice")))
    return engine, languages


def _who_tab(w):
    roles, lay = w._voice_section("Voices by role", "Give some messages their own voice. A viewer's own voice comes first, then these, then the platform.")
    for title, note, key in ROLE_VOICES:
        lay.addWidget(w._voice_field(title, note, bound_picker(w, key, SAME)))
    platforms, lay = w._voice_section("Voices by platform", "Hear which platform a message came from.")
    for title, key in PLATFORM_VOICES:
        lay.addWidget(w._voice_field(title, "", bound_picker(w, key, SAME)))

    viewers, lay = w._voice_section("Voices for viewers", "To give one viewer their own voice, click their message in Live chat.")
    lay.addWidget(w._voice_switch("Match the viewer's language", "Russian, Korean, Japanese and Chinese messages use a voice of that language.", "voice_match_language"))
    lay.addWidget(w._voice_switch("Different voice for each viewer", "Each viewer keeps the same voice from the list below.", "per_viewer"))
    pool = QListWidget()
    pool.setMaximumHeight(130)
    picker = VoicePicker(w.speaker, "en-IN-NeerjaNeural")

    def save():
        w.s.set("voice_pool", [pool.item(i).data(Qt.UserRole) for i in range(pool.count())])

    def add(voice):
        if voice and voice not in [pool.item(i).data(Qt.UserRole) for i in range(pool.count())]:
            item = QListWidgetItem(voices.full_label(voice))
            item.setData(Qt.UserRole, voice)
            pool.addItem(item)

    for voice in w.s.get("voice_pool") or []:
        add(voice)
    add_btn, remove_btn = _button("Add this voice"), _button("Remove selected")
    add_btn.clicked.connect(lambda: (add(picker.value()), save()))
    remove_btn.clicked.connect(lambda: (pool.takeItem(pool.currentRow()), save()))
    lay.addWidget(w._voice_field("Voices to share out", "Empty uses the four Indian voices.", picker))
    lay.addWidget(pool)
    row = QHBoxLayout()
    row.addWidget(add_btn)
    row.addWidget(remove_btn)
    row.addStretch(1)
    lay.addLayout(row)
    return roles, platforms, viewers


def _reading_tab(w):
    options, lay = w._voice_section("Voice options", "Small choices for how messages are spoken.")
    read_mode = QComboBox()
    read_mode.addItem("Read all chat", "all")
    read_mode.addItem("Read only !tts messages", "tts")
    read_mode.addItem("Read paid messages only", "paid")
    read_mode.setCurrentIndex(max(0, read_mode.findData(w.s.get("read_mode") or "all")))
    read_mode.currentIndexChanged.connect(lambda _: w.set_read_mode(read_mode.currentData()))
    w.read_mode_box = read_mode
    lay.addWidget(w._voice_field("Chat reading mode",
                                 "!tts only: viewers type !tts and their message to have it read. Tips, Super Chats, Bits, memberships and mods are "
                                 "always read. Paid only skips mods too. Switch fast with the All chat button at the top or Ctrl+Alt+T.", read_mode))
    bots = QLineEdit(", ".join(w.s.get("bot_names") or []))
    bots.setPlaceholderText("e.g. MyChannelHelper, Sumo")
    bots.editingFinished.connect(lambda: w.s.set("bot_names", [b.strip() for b in bots.text().split(",") if b.strip()]))
    lay.addWidget(w._voice_field("More bots to never read",
                                 "Nightbot, StreamElements, names ending in bot and CHATDOOM's own replies are already skipped. Add other bot names here, separated by commas.", bots))
    lay.addWidget(w._voice_switch("Say the viewer's name first", "Speak the viewer's name before reading their message.", "read_name"))
    lay.addWidget(w._voice_switch("Tidy viewer names", "Read Rahul_1234 as Rahul.", "say_clean_names"))
    lay.addWidget(w._voice_switch("Read paid messages", "Allow Super Chats, Bits, memberships, and tips to be read.", "read_super"))
    lay.addWidget(w._voice_switch("Shorten stretched words", "Read heyyyyyyy as heyyy.", "say_squeeze"))
    emoji = QComboBox()
    emoji.addItem("Read emoji aloud", "read")
    emoji.addItem("Skip emoji", "skip")
    emoji.setCurrentIndex(max(0, emoji.findData(w.s.get("say_emoji") or "read")))
    emoji.currentIndexChanged.connect(lambda _: w.s.set("say_emoji", emoji.currentData()))
    lay.addWidget(w._voice_field("Emoji", "Read says \"smiling face\" for an emoji, once for a row of the same one. Skip also leaves out channel emotes.", emoji))
    length = w._voice_meter("Longest message", "Longer messages are cut off here.", "max_len", 30, 500, lambda v: "%d letters" % v)

    wording, wlay = w._voice_section("Your own wording", "{name} is the viewer, {message} is what they said, {amount} is the amount paid.")
    for title, key, default in (("Normal messages", "say_format", "{name}: {message}"), ("Paid messages", "say_paid_format", "{name} sent {amount}. {message}")):
        edit = QLineEdit(w.s.get(key) or default)
        edit.setMaxLength(120)
        edit.setPlaceholderText(default)
        edit.editingFinished.connect(lambda k=key, e=edit, d=default: w.s.set(k, e.text().strip() or d))
        wlay.addWidget(w._voice_field(title, "", edit))
    lay.addWidget(length)
    return options, wording


def _playback_tab(w):
    playback, lay = w._voice_section("Sound of the voice", "Pick a ready-made style, or set speed and pitch yourself.")
    preset = QComboBox()
    preset.addItem("Choose a style", None)
    for name, rate, pitch in voices.PRESETS:
        preset.addItem(name, (rate, pitch))
    lay.addWidget(w._voice_field("Style", "Sets speed and pitch together.", preset))
    speed = w._voice_meter("Speed", "Controls how quickly messages are spoken.", "rate", voices.RATE_LOW, voices.RATE_HIGH, lambda v: "%.1f×" % (1 + v * 0.1))
    pitch = w._voice_meter("Pitch", "Lower is deeper. Neural voices use this fully; Windows voices only partly.", "pitch", -voices.PITCH_LIMIT, voices.PITCH_LIMIT, lambda v: "%+d" % v)

    def use_preset(_):
        values = preset.currentData()
        if values:
            speed.findChild(QSlider).setValue(values[0])
            pitch.findChild(QSlider).setValue(values[1])

    preset.currentIndexChanged.connect(use_preset)
    lay.addWidget(speed)
    lay.addWidget(pitch)
    lay.addWidget(w._voice_meter("Volume", "Controls the voice output level.", "volume", 0, 100, lambda v: "%d%%" % v))
    lay.addWidget(w._voice_meter("Pause between messages", "A short gap so messages do not run together.", "say_gap_ms", 0, 2000, lambda v: "%.1f s" % (v / 1000)))
    device = QComboBox()
    device.addItem("Windows default", "")
    for output in QMediaDevices.audioOutputs():
        device.addItem(output.description(), output.description())
    device.setCurrentIndex(max(0, device.findData(w.s.get("voice_device"))))
    device.currentIndexChanged.connect(lambda _: w.s.set("voice_device", device.currentData()))
    lay.addWidget(w._voice_field("Play the voice through", "Choose a virtual cable to give the voice its own OBS track. The next message uses it.", device))

    queue, qlay = w._voice_section("Message queue", "Controls how many chat messages can wait to be spoken.")
    spin = w._bind_spin("queue_max", 1, 20)
    spin.setMaximumWidth(88)
    qlay.addWidget(w._voice_field("Maximum messages in queue", "Older messages are removed when chat becomes too fast.", spin))
    return playback, queue


def _translate_tab(w):
    card, lay = w._voice_section("Translate chat", "Turn it on and off here or with the Translate button on the Live chat page.")
    row = w._voice_switch("Translate chat", "Needs your Discord cloud connection. All CHATDOOM users share a daily limit, so tick only the languages you need.", "translate_chat")
    w.translate_switch = row.switch
    w.translate_switch.toggled.connect(lambda _: w.sync_translate_button())
    lay.addWidget(row)
    chosen = list(w.s.get("translate_langs") or [])
    languages, llay = w._voice_section("Languages to translate", "Everything else stays as the viewer wrote it, so Hindi and Hinglish are left alone.")

    def toggle(code, on):
        now = [c for c in (w.s.get("translate_langs") or []) if c != code]
        w.s.set("translate_langs", now + [code] if on else now)

    for name, code in translation.CHOICES:
        llay.addWidget(w._voice_switch(name, "", "", code in chosen, lambda on, c=code: toggle(c, on)))
    llay.addWidget(w._voice_switch("Any other language", "Also translate every other language CHATDOOM can detect, including Hindi. This uses up the daily limit much faster.", "translate_others"))

    result, rlay = w._voice_section("What happens to a translation", "Choose where it goes.")
    target = QComboBox()
    for name, code in translation.TARGETS:
        target.addItem(name, code)
    target.setCurrentIndex(max(0, target.findData(w.s.get("translate_target") or "en")))
    target.currentIndexChanged.connect(lambda _: w.s.set("translate_target", target.currentData()))
    rlay.addWidget(w._voice_field("Translate into", "", target))
    rlay.addWidget(w._voice_switch("Show it in Live chat", "A line appears under the message.", "translate_show"))
    rlay.addWidget(w._voice_switch("Read it aloud", "The voice reads the translation instead of the original.", "translate_speak"))
    test = _button("Test translation", "primary")
    w.translate_result = QLabel("")
    w.translate_result.setObjectName("voiceNote")
    w.translate_result.setWordWrap(True)
    test.clicked.connect(lambda: test_translation(w))
    rlay.addWidget(test, 0, Qt.AlignLeft)
    rlay.addWidget(w.translate_result)
    return card, languages, result


def test_translation(w):
    """One real translation per language, so the streamer can see it working before going live."""
    w.translate_result.setText("Testing...")
    settings = w.s

    def work():
        lines = []
        for name, text in TEST_LINES:
            try:
                words, _, done = translation.translate_message(text, settings, force=True)
                lines.append("%s: %s" % (name, words) if done else "%s: not translated" % name)
            except Exception as error:
                lines.append("%s: failed (%s)" % (name, str(error)[:90]))
        return {"lines": lines}

    run_bg(w.bridge, "voice:translate-test", work)


def _words_tab(w):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    from . import hinglish
    words, lay = w._voice_section("Word list", "Manage words and pronunciation used when reading Hinglish chat.")
    edit, reload_words = _button("Edit word list", "primary"), _button("Reload word list")
    edit.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(w.words_path)))
    reload_words.clicked.connect(lambda: w.feed.append("<span style='color:#8a93a8'>Loaded %d short-form words</span>" % hinglish.load_words(w.words_path)))
    row = QHBoxLayout()
    row.addWidget(edit)
    row.addWidget(reload_words)
    row.addStretch(1)
    lay.addLayout(row)
    return (words,)


def fill_voice_page(w, page):
    tabs = (("Voices", _voices_tab), ("Who speaks", _who_tab), ("Reading", _reading_tab), ("Playback", _playback_tab), ("Translate", _translate_tab), ("Word list", _words_tab))
    for title, build in tabs:
        tab = page.add_tab(title)
        for card in build(w):
            tab.addWidget(card)
    page.finish()
    w.bridge.done.connect(lambda tag, result: w.translate_result.setText("\n".join(result.get("lines") or [result.get("error", "")])) if tag == "voice:translate-test" else None)
