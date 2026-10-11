"""Stream-safe music player: plays the streamer's own no-copyright / licensed files, shows 'now playing' in OBS,
and lowers itself while CHATDOOM is reading a chat message aloud."""
import os
import random
import re
import shutil
import stat
import zipfile
from pathlib import PurePosixPath

from PySide6.QtCore import QObject, QUrl, Signal

from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

AUDIO_EXT = (".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus")
MAX_IMPORT_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000


def describe(path):
    """'Artist - Title.mp3' -> (artist, title); anything else -> ('', filename)."""
    base = re.sub(r"\s+", " ", os.path.splitext(os.path.basename(path))[0].replace("_", " ")).strip()
    if " - " in base:
        artist, title = base.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", base


def scan(folder, limit=1500):
    out = []
    if not folder or not os.path.isdir(folder):
        return out
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))[:50]
        if root[len(folder):].count(os.sep) >= 2:                  # two folders deep is plenty
            dirs[:] = []
        for f in sorted(files, key=str.lower):
            if f.lower().endswith(AUDIO_EXT):
                p = os.path.join(root, f)
                artist, title = describe(p)
                out.append({"path": p, "artist": artist, "title": title})
                if len(out) >= limit:
                    return out
    return out


def import_downloads(paths, folder):
    """Copy supported tracks and safely import audio files from official album ZIP downloads."""
    os.makedirs(folder, exist_ok=True)
    imported = []
    total_size = 0

    def destination(name):
        base, ext = os.path.splitext(os.path.basename(name))
        target = os.path.join(folder, os.path.basename(name))
        suffix = 1
        while os.path.exists(target):
            target = os.path.join(folder, "%s (%d)%s" % (base, suffix, ext))
            suffix += 1
        return target

    def copy_file(source, name, expected_size=None):
        nonlocal total_size
        size = os.path.getsize(source) if expected_size is None else expected_size
        if size <= 0 or total_size + size > MAX_IMPORT_BYTES:
            raise ValueError("Music imports are limited to 512 MB at a time")
        target = destination(name)
        temporary = target + ".importing"
        try:
            shutil.copyfile(source, temporary)
            if os.path.getsize(temporary) != size:
                raise OSError("The imported audio file changed while it was being copied")
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        total_size += size
        imported.append(target)

    for source in paths:
        if not os.path.isfile(source):
            continue
        if source.lower().endswith(AUDIO_EXT):
            copy_file(source, os.path.basename(source))
            continue
        if not zipfile.is_zipfile(source):
            continue
        try:
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_ARCHIVE_FILES:
                    raise ValueError("The album archive contains too many files")
                for entry in entries:
                    path = PurePosixPath(entry.filename.replace("\\", "/"))
                    mode = entry.external_attr >> 16
                    if (entry.is_dir() or path.is_absolute() or ".." in path.parts or
                            stat.S_ISLNK(mode) or not path.name.lower().endswith(AUDIO_EXT)):
                        continue
                    size = entry.file_size
                    if size <= 0 or total_size + size > MAX_IMPORT_BYTES:
                        raise ValueError("Music imports are limited to 512 MB at a time")
                    target = destination(path.name)
                    temporary = target + ".importing"
                    try:
                        with archive.open(entry) as src, open(temporary, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        if os.path.getsize(temporary) != size:
                            raise OSError("The album archive contains an incomplete audio file")
                        os.replace(temporary, target)
                    finally:
                        if os.path.exists(temporary):
                            os.remove(temporary)
                    total_size += size
                    imported.append(target)
        except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
            raise ValueError("Could not import %s: %s" % (os.path.basename(source), error)) from error
    return imported


class QtBackend(QObject):
    ended = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.mediaStatusChanged.connect(lambda st: self.ended.emit() if st == QMediaPlayer.MediaStatus.EndOfMedia else None)
        self.player.errorOccurred.connect(lambda err, text: self.failed.emit(text or "cannot play this file"))

    def load(self, path):
        self.player.setSource(QUrl.fromLocalFile(path))

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()

    def set_volume(self, v):
        self.audio.setVolume(v)


class MusicPlayer(QObject):
    changed = Signal()
    notice = Signal(str)

    def __init__(self, settings, push, backend=None):
        super().__init__()
        self.s, self.push = settings, push
        self.tracks, self.index, self.playing, self.ducked = [], -1, False, False
        self.history, self.order, self._fails = [], [], 0
        self.backend = backend or QtBackend()
        self.backend.ended.connect(self._ended)
        self.backend.failed.connect(self._failed)
        self._apply_volume()
        if self.s.get("music_folder"):
            self.load_folder(self.s.get("music_folder"))

    # ----- library -----
    def load_folder(self, folder):
        self.s.set("music_folder", folder)
        self.stop()
        self.tracks = scan(folder)
        self.index, self.history = -1, []
        self._reshuffle()
        self.changed.emit()
        return len(self.tracks)

    def _reshuffle(self):
        self.order = list(range(len(self.tracks)))
        if self.s.get("music_shuffle"):
            random.shuffle(self.order)

    def current(self):
        return self.tracks[self.index] if 0 <= self.index < len(self.tracks) else None

    # ----- controls -----
    def play_index(self, i):
        if not 0 <= i < len(self.tracks):
            return
        if self.index >= 0 and self.index != i:
            self.history.append(self.index)
        self.index = i
        self.backend.load(self.tracks[i]["path"])
        self.backend.play()
        self.playing = True
        self._publish()

    def toggle(self):
        if not self.tracks:
            return
        if self.index < 0:
            return self.next()
        if self.playing:
            self.backend.pause()
            self.playing = False
        else:
            self.backend.play()
            self.playing = True
        self._publish()

    def pause(self):
        if self.playing:
            self.backend.pause()
            self.playing = False
            self._publish()

    def stop(self):
        if self.index >= 0:
            self.backend.stop()
        self.playing = False
        self._publish()

    def next(self):
        if not self.tracks:
            return
        if len(self.order) != len(self.tracks):
            self._reshuffle()
        pos = self.order.index(self.index) if self.index in self.order else -1
        if pos + 1 >= len(self.order):
            self._reshuffle()
            pos = -1
        self.play_index(self.order[pos + 1])

    def prev(self):
        if self.history:
            i = self.history.pop()
            self.index = -1                              # do not push the current song onto the history again
            self.play_index(i)

    def _ended(self):
        self._fails = 0                       # a song played to the end, so files are fine
        self.next()

    def _failed(self, text):
        self._fails += 1
        bad = self.current()
        if self._fails >= max(1, len(self.tracks)):
            self._fails = 0
            self.playing = False
            self.notice.emit("None of the music files could be played (%s)" % text)
            self._publish()
            return
        self.notice.emit("Skipped a file that cannot be played: %s" % (bad["title"] if bad else text))
        self.next()

    # ----- volume -----
    def _apply_volume(self):
        v = int(self.s.get("music_volume")) / 100.0
        if self.ducked and self.s.get("music_duck"):
            v *= int(self.s.get("music_duck_pct")) / 100.0
        self.backend.set_volume(max(0.0, min(1.0, v)))

    def set_volume(self, v):
        self.s.set("music_volume", int(v))
        self._apply_volume()

    def duck(self, on):
        """Called while CHATDOOM reads a message aloud."""
        self.ducked = bool(on)
        self._apply_volume()

    def refresh_settings(self):
        self._apply_volume()

    # ----- sharing -----
    def state(self):
        t = self.current()
        return {"title": t["title"] if t else "", "artist": t["artist"] if t else "", "playing": bool(self.playing and t)}

    def _publish(self):
        self.push("music", self.state())
        self.changed.emit()
