"""Speech queue: neural voices (edge-tts, online) with Windows voices (offline) as fallback."""
import asyncio
import os
import re
import tempfile
import threading
import time
import zlib
from collections import deque

from PySide6.QtCore import QLocale, QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from . import hinglish, voices
from .translation import script_language, translate_to_english

try:
    from PySide6.QtTextToSpeech import QTextToSpeech
except Exception:  # offline voices unavailable
    QTextToSpeech = None

VOICES = list(voices.FAVOURITES)
POOL_HI = ["hi-IN-SwaraNeural", "hi-IN-MadhurNeural"]
POOL_ALL = [v for _, v in VOICES]
READ_FORMAT = "{name}: {message}"
PAID_FORMAT = "{name} sent {amount}. {message}"
GAP_MS = 150
LETTER_RUN = re.compile(r"(\w)\1{3,}")
NAME_TAIL = re.compile(r"[\W_]*\d+[\W_]*$")


def fill(template, name, message, amount=""):
    """Plain replacing, so a stray { in the streamer's wording can never break speech."""
    return template.replace("{name}", name).replace("{message}", message).replace("{amount}", amount).strip()


def speakable_name(name):
    """Rahul_1234 is read as Rahul."""
    cleaned = NAME_TAIL.sub("", name or "").replace("_", " ").strip()
    return cleaned or name


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
        self.current_clip = None
        self.current_spoken = ""
        self._windows_fallback = False
        self._tts_started = False
        self._generated.connect(self._on_generated)
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self._on_watchdog)

    # ----- public -----
    def say(self, author, text, amount="", who=None):
        """Queue a message. Oldest are dropped when chat is faster than speech. who: platform, mod, member and emotes, for choosing the voice."""
        who = who or {}
        text = self._tidy((text or "").strip(), who)
        speak_translation = self.s.get("translate_speak")
        translate = bool(self.s.get("translate_chat")) and speak_translation is not False and bool(text)
        if not translate:
            text = hinglish.normalize(text).strip()
        if not text and not amount:
            return
        if self.s.get("muted"):
            return
        self.queue.append((author, text, amount, translate, "", who))
        self._trim()
        self._pump()

    def _tidy(self, text, who):
        if self.s.get("say_emoji") == "skip":
            text = hinglish.strip_emoji(text, who.get("emotes"))
        else:
            text = hinglish.squeeze_emoji(text)
        if self.s.get("say_squeeze"):
            text = LETTER_RUN.sub(r"\1\1\1", text)
        return text

    def preview(self, voice, text=""):
        """Plays a voice now, in front of the queue, whichever engine is chosen."""
        if self.s.get("muted"):
            self.note.emit("Voice is muted. Click Unmute to hear a preview.")
            return
        self.queue.appendleft(("", text or voices.sample_for(voice), "", False, "", {"voice": voice}))
        self._pump()

    def windows_voices(self):
        """Names of the voices installed in Windows, for the voice page."""
        if QTextToSpeech is None:
            return []
        try:
            engine = self.tts or QTextToSpeech(self)
            self.tts = engine
            if not getattr(self, "_tts_hooked", False):
                engine.stateChanged.connect(self._on_tts_state)
                self._tts_hooked = True
            return [v.name() for v in engine.availableVoices()]
        except Exception:
            return []

    def announce(self, text="", sound=""):
        """Queue a command answer or meme: the sound clip first, then the line in the chat voice (no name, never translated)."""
        if self.s.get("muted"):
            return
        text = hinglish.normalize(text or "").strip()
        if sound:
            self.queue.append(("", "", "", False, sound, {}))
        if text:
            self.queue.append(("", text, "", False, "", {"alert": True}))
        self._trim()
        self._pump()

    def _trim(self):
        while len(self.queue) > self.s.get("queue_max"):
            # drop the oldest normal message first; paid messages are kept
            drop = next((i for i, q in enumerate(self.queue) if not q[2]), 0)
            del self.queue[drop]

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
    def _chosen_voice(self, author, who):
        """A voice set for this viewer, then for their role, then for their platform. Empty when none applies."""
        if who.get("voice"):
            return who["voice"]
        own = self.s.get("viewer_voices")
        if isinstance(own, dict) and own.get((author or "").lower()):
            return own[(author or "").lower()]
        for flag, key in (("alert", "voice_alerts"), ("paid", "voice_paid"), ("member", "voice_member"), ("mod", "voice_mod")):
            if who.get(flag) and self.s.get(key):
                return self.s.get(key)
        return self.s.get("voice_" + who["platform"]) if who.get("platform") else ""

    def _voice_for(self, author, spoken, who=None):
        chosen = self._chosen_voice(author, who or {})
        if chosen:
            return chosen
        if self.s.get("voice_match_language"):
            match = voices.for_language(script_language(spoken)) if script_language(spoken) not in ("", "hi") else ""
            if match:
                return match
        if self.s.get("per_viewer"):
            mine = self.s.get("voice_pool") or POOL_ALL
            pool = (POOL_HI if hinglish.has_devanagari(spoken) else None) or mine
            return pool[zlib.crc32(author.encode("utf-8")) % len(pool)]
        return self.s.get("hi_voice") if hinglish.has_devanagari(spoken) else self.s.get("en_voice")

    def _pump(self):
        if self.busy or not self.queue:
            return
        author, text, amount, translate, sound, who = self.queue.popleft()
        self.busy = True
        self.busy_changed.emit(True)
        self.token += 1
        self._windows_fallback = False
        self.watchdog.start(45000)
        if sound:
            self.current_spoken = ""
            return self._play_clip(sound)
        self.current_spoken = self._format_spoken(author, text, amount)
        if self.s.get("engine") != "neural" and not translate and not who.get("voice"):
            return self._speak_windows(self.current_spoken)
        threading.Thread(target=self._generate, args=(self.token, author, text, amount, translate, who),
                         daemon=True).start()

    def _format_spoken(self, author, text, amount):
        text = hinglish.normalize(text).strip()
        if len(text) > self.s.get("max_len"):
            text = text[:self.s.get("max_len")] + "..."
        name = speakable_name(author) if self.s.get("say_clean_names") else author
        if amount:
            return fill(self.s.get("say_paid_format") or PAID_FORMAT, name, text, amount)
        return fill(self.s.get("say_format") or READ_FORMAT, name, text) if self.s.get("read_name") and author else text

    def _generate(self, token, author, text, amount, translate, who=None):
        who = who or {}
        translated = False
        if translate:
            try:
                text = text[:min(500, int(self.s.get("max_len")))]
                text, translated = translate_to_english(text, self.s)
            except Exception as error:
                self.note.emit("Translation unavailable (%s). Speaking the original message." % str(error)[:100])
                text = hinglish.normalize(text).strip()
        spoken = self._format_spoken(author, text, amount)
        voice = self._voice_for(author, spoken, who)
        if self.s.get("engine") != "neural" and not who.get("voice"):
            self._generated.emit(token, "", "", spoken)
            return
        path = os.path.join(tempfile.gettempdir(), "chatvoice_%d_%d.mp3" % (os.getpid(), int(time.time() * 1000)))
        try:
            import edge_tts
            pct = int(self.s.get("rate") or 0) * 10
            pitch = int(self.s.get("pitch") or 0)
            asyncio.run(edge_tts.Communicate(spoken, voice, rate="%+d%%" % pct, pitch="%+dHz" % pitch).save(path))
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
        self._ensure_player()
        self.current_file = path
        try:
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.play()
        except Exception as error:
            self._fallback_to_windows("Neural audio playback failed (%s)" % str(error)[:80])

    def _ensure_player(self):
        if self.player is None:
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.mediaStatusChanged.connect(self._on_status)
            self.player.errorOccurred.connect(self._on_player_error)
        self.audio.setVolume(self.s.get("volume") / 100.0)
        wanted = self.s.get("voice_device")
        if wanted:                                # for example a virtual cable, to keep the voice on its own OBS track
            for device in QMediaDevices.audioOutputs():
                if device.description() == wanted:
                    self.audio.setDevice(device)
                    break

    def _play_clip(self, path):
        """A meme sound: played as it is, and never deleted afterwards (it lives in the memes folder)."""
        self._ensure_player()
        self.current_clip = path
        try:
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.play()
        except Exception as error:
            self._clip_failed(str(error))

    def _clip_failed(self, detail):
        self.note.emit("Meme sound could not be played (%s)" % (detail or "unknown error")[:80])
        self.current_clip = None
        self._finish()

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._finish()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia and self.current_clip:
            self._clip_failed("unsupported file")
        elif status == QMediaPlayer.MediaStatus.InvalidMedia and self.current_file:
            self._fallback_to_windows("Neural audio could not be played")

    def _on_player_error(self, error, error_string):
        if self.current_clip:
            self._clip_failed(error_string or self.player.errorString())
        elif self.current_file:
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
        if self.s.get("engine") == "neural" and not self._windows_fallback and not self.current_clip:
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
            self._tts_hooked = True
        if self.tts.state() == QTextToSpeech.State.Error or not self.tts.availableVoices():
            self.note.emit("No Windows voice found - add one in Windows Settings > Speech")
            return self._finish()
        self.tts.setVolume(self.s.get("volume") / 100.0)
        self.tts.setRate(max(-1.0, min(1.0, self.s.get("rate") / 5.0)))
        self.tts.setPitch(max(-1.0, min(1.0, int(self.s.get("pitch") or 0) / 50.0)))
        want = "hi" if hinglish.has_devanagari(spoken) else "en"
        named = self.s.get("win_voice")
        installed = self.tts.availableVoices()
        for v in [x for x in installed if x.name() == named] or [x for x in installed if x.locale().name().lower().startswith(want)]:
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
        self.current_clip = None
        was = self.busy
        self.busy = False
        self.watchdog.stop()
        if was:
            self.busy_changed.emit(False)
        gap = self.s.get("say_gap_ms")
        QTimer.singleShot(GAP_MS if gap is None else int(gap), self._pump)
