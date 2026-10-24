"""Speech queue: neural voices (edge-tts, online) with Windows voices (offline) as fallback."""
import asyncio
import os
import tempfile
import threading
import time
import zlib
from collections import deque

from PySide6.QtCore import QLocale, QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from . import hinglish
from .translation import translate_to_english

try:
    from PySide6.QtTextToSpeech import QTextToSpeech
except Exception:  # offline voices unavailable
    QTextToSpeech = None

VOICES = [
    ("Hindi female - Swara", "hi-IN-SwaraNeural"),
    ("Hindi male - Madhur", "hi-IN-MadhurNeural"),
    ("Indian English female - Neerja", "en-IN-NeerjaNeural"),
    ("Indian English male - Prabhat", "en-IN-PrabhatNeural"),
]
POOL_HI = ["hi-IN-SwaraNeural", "hi-IN-MadhurNeural"]
POOL_ALL = [v for _, v in VOICES]


class Speaker(QObject):
    busy_changed = Signal(bool)
    note = Signal(str)                  # info/warning lines for the UI
    _generated = Signal(int, str, str, str)  # token, mp3 path, error, spoken text

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.queue = deque()
        self.busy = False
        self.token = 0
        self.player = None
        self.audio = None
        self.tts = None
        self.current_file = None
        self.current_spoken = ""
        self._windows_fallback = False
        self._tts_started = False
        self._generated.connect(self._on_generated)
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self._on_watchdog)

    # ----- public -----
    def say(self, author, text, amount=""):
        """Queue a message. Oldest are dropped when chat is faster than speech."""
        translate = bool(self.s.get("translate_chat")) and bool((text or "").strip())
        text = (text or "").strip()
        if not translate:
            text = hinglish.normalize(text).strip()
        if not text and not amount:
            return
        if self.s.get("muted"):
            return
        self.queue.append((author, text, amount, translate))
        while len(self.queue) > self.s.get("queue_max"):
            # drop the oldest normal message first; paid messages are kept
            drop = next((i for i, q in enumerate(self.queue) if not q[2]), 0)
            del self.queue[drop]
        self._pump()

    def skip(self):
        """Stop whatever is being spoken and move on."""
        self.token += 1
        self.watchdog.stop()
        if self.player:
            self.player.stop()
        if self.tts:
            self.tts.stop()
        self._finish()

    def clear(self):
        self.queue.clear()
        self.skip()

    # ----- internals -----
    def _voice_for(self, author, spoken):
        if self.s.get("per_viewer"):
            pool = POOL_HI if hinglish.has_devanagari(spoken) else POOL_ALL
            return pool[zlib.crc32(author.encode("utf-8")) % len(pool)]
        return self.s.get("hi_voice") if hinglish.has_devanagari(spoken) else self.s.get("en_voice")

    def _pump(self):
        if self.busy or not self.queue:
            return
        author, text, amount, translate = self.queue.popleft()
        self.busy = True
        self.busy_changed.emit(True)
        self.token += 1
        self._windows_fallback = False
        self.current_spoken = self._format_spoken(author, text, amount)
        self.watchdog.start(45000)
        if self.s.get("engine") != "neural" and not translate:
            return self._speak_windows(self.current_spoken)
        threading.Thread(target=self._generate, args=(self.token, author, text, amount, translate),
                         daemon=True).start()

    def _format_spoken(self, author, text, amount):
        text = hinglish.normalize(text).strip()
        if len(text) > self.s.get("max_len"):
            text = text[:self.s.get("max_len")] + "..."
        if amount:
            return "%s sent %s. %s" % (author, amount, text)
        return ("%s: %s" % (author, text)) if self.s.get("read_name") else text

    def _generate(self, token, author, text, amount, translate):
        translated = False
        if translate:
            try:
                text = text[:min(500, int(self.s.get("max_len")))]
                text, translated = translate_to_english(text, self.s)
            except Exception as error:
                self.note.emit("Translation unavailable (%s). Speaking the original message." % str(error)[:100])
                text = hinglish.normalize(text).strip()
        spoken = self._format_spoken(author, text, amount)
        voice = self.s.get("en_voice") if translated else self._voice_for(author, spoken)
        if self.s.get("engine") != "neural":
            self._generated.emit(token, "", "", spoken)
            return
        path = os.path.join(tempfile.gettempdir(), "chatvoice_%d_%d.mp3" % (os.getpid(), int(time.time() * 1000)))
        try:
            import edge_tts
            pct = int(self.s.get("rate")) * 10
            asyncio.run(edge_tts.Communicate(spoken, voice, rate="%+d%%" % pct).save(path))
            self._generated.emit(token, path, "", spoken)
        except Exception as e:
            self._generated.emit(token, "", str(e)[:80], spoken)

    def _on_generated(self, token, path, err, spoken):
        if token != self.token:           # skipped while generating
            if path:
                self._remove(path)
            return
        self.current_spoken = spoken
        if not path:
            if err:
                return self._fallback_to_windows("Neural voice unavailable (%s)" % err)
            return self._speak_windows(self.current_spoken)
        if self.player is None:
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.mediaStatusChanged.connect(self._on_status)
            self.player.errorOccurred.connect(self._on_player_error)
        self.audio.setVolume(self.s.get("volume") / 100.0)
        self.current_file = path
        try:
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.play()
        except Exception as error:
            self._fallback_to_windows("Neural audio playback failed (%s)" % str(error)[:80])

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._finish()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia and self.current_file:
            self._fallback_to_windows("Neural audio could not be played")

    def _on_player_error(self, error, error_string):
        if self.current_file:
            detail = error_string or self.player.errorString()
            self._fallback_to_windows("Neural audio playback failed (%s)" % (detail or error))

    def _fallback_to_windows(self, reason):
        if not self.busy or self._windows_fallback:
            return
        self._windows_fallback = True
        self.note.emit("%s - using Windows voice" % reason)
        path = self.current_file
        self.current_file = None
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        if path:
            self._remove(path)
        self.watchdog.start(45000)
        self._speak_windows(self.current_spoken)

    def _on_watchdog(self):
        if self.s.get("engine") == "neural" and not self._windows_fallback:
            self.token += 1
            return self._fallback_to_windows("Neural voice timed out")
        self.skip()

    def _speak_windows(self, spoken):
        if QTextToSpeech is None:
            self.note.emit("No Windows voice available")
            return self._finish()
        if self.tts is None:
            self.tts = QTextToSpeech(self)
            self.tts.stateChanged.connect(self._on_tts_state)
        if self.tts.state() == QTextToSpeech.State.Error or not self.tts.availableVoices():
            self.note.emit("No Windows voice found - add one in Windows Settings > Speech")
            return self._finish()
        self.tts.setVolume(self.s.get("volume") / 100.0)
        self.tts.setRate(max(-1.0, min(1.0, self.s.get("rate") / 5.0)))
        want = "hi" if hinglish.has_devanagari(spoken) else "en"
        for v in self.tts.availableVoices():
            if v.locale().name().lower().startswith(want):
                self.tts.setVoice(v)
                break
        self._tts_started = False
        self.tts.say(spoken)

    def _on_tts_state(self, state):
        if state == QTextToSpeech.State.Speaking:
            self._tts_started = True
        elif state == QTextToSpeech.State.Error:
            self._tts_started = False
            self.note.emit("Windows voice playback failed")
            self._finish()
        elif state == QTextToSpeech.State.Ready and self._tts_started:
            self._tts_started = False
            self._finish()

    def _remove(self, path):
        try:
            os.remove(path)
        except Exception:
            pass

    def _finish(self):
        if self.current_file:
            self._remove(self.current_file)
            self.current_file = None
        was = self.busy
        self.busy = False
        self.watchdog.stop()
        if was:
            self.busy_changed.emit(False)
        QTimer.singleShot(150, self._pump)
