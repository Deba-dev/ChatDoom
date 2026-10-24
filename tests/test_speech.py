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


if __name__ == "__main__":
    unittest.main()
