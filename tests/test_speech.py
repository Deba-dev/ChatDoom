import os
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtMultimedia import QMediaPlayer

from app.speech import Speaker


class Settings:
    def get(self, key):
        return {"engine": "neural", "volume": 100}.get(key)


class Player:
    def stop(self):
        pass

    def setSource(self, _source):
        pass

    def errorString(self):
        return "decoder unavailable"


class SpeakerPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.speaker = Speaker(Settings())
        self.speaker.busy = True
        self.speaker.current_spoken = "Viewer: hello"
        self.speaker.player = Player()
        self.spoken = []
        self.notes = []
        self.speaker._speak_windows = self.spoken.append
        self.speaker.note.connect(self.notes.append)

    def tearDown(self):
        self.speaker.watchdog.stop()
        self.speaker.deleteLater()
        self.app.processEvents()

    def test_media_error_falls_back_to_windows_voice(self):
        with tempfile.NamedTemporaryFile(delete=False) as audio_file:
            path = audio_file.name
        self.speaker.current_file = path

        self.speaker._on_player_error(QMediaPlayer.Error.FormatError, "decoder unavailable")

        self.assertEqual(self.spoken, ["Viewer: hello"])
        self.assertFalse(os.path.exists(path))
        self.assertIn("using Windows voice", self.notes[-1])

    def test_invalid_media_falls_back_to_windows_voice(self):
        self.speaker.current_file = "missing-audio-file.mp3"

        self.speaker._on_status(QMediaPlayer.MediaStatus.InvalidMedia)

        self.assertEqual(self.spoken, ["Viewer: hello"])
        self.assertIn("could not be played", self.notes[-1])

    def test_neural_timeout_uses_windows_voice(self):
        self.speaker._on_watchdog()

        self.assertEqual(self.spoken, ["Viewer: hello"])
        self.assertIn("timed out", self.notes[-1])


class QueueSettings:
    def get(self, key):
        return {"engine": "windows", "volume": 100, "queue_max": 6, "max_len": 150, "read_name": True}.get(key)


class MemeQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.speaker = Speaker(QueueSettings())
        self.clips, self.spoken, self.notes = [], [], []
        self.speaker._play_clip = lambda path: (self.clips.append(path), setattr(self.speaker, "current_clip", path))
        self.speaker._speak_windows = self.spoken.append
        self.speaker.note.connect(self.notes.append)

    def tearDown(self):
        self.speaker.watchdog.stop()
        self.speaker.deleteLater()
        self.app.processEvents()

    def test_meme_plays_clip_then_reads_line_without_a_name(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as clip:
            path = clip.name
        self.speaker.announce("bruh moment", path)
        self.assertEqual(self.clips, [path])
        self.assertEqual(self.spoken, [])

        self.speaker._finish()
        self.speaker._pump()

        self.assertEqual(self.spoken, ["bruh moment"])
        self.assertTrue(os.path.exists(path), "meme clips live in the memes folder and must never be deleted")
        os.remove(path)

    def test_broken_clip_moves_on_to_the_next_message(self):
        self.speaker.announce("", "broken.mp3")
        self.speaker.say("Viewer", "hello")
        self.speaker.player = Player()
        self.speaker._on_player_error(QMediaPlayer.Error.FormatError, "decoder unavailable")
        self.speaker._pump()

        self.assertEqual(self.spoken, ["Viewer: hello"])
        self.assertIn("Meme sound could not be played", self.notes[-1])


if __name__ == "__main__":
    unittest.main()
