"""Built-in alert sounds. Every one is made here from plain tones and noise, so there is nothing to download and nothing to license.
A sound is a list of notes: (start seconds, length seconds, start hz, end hz, wave, loudness). Hz of 0 with wave "noise" is a burst of hiss."""
import io
import math
import random
import struct
import wave

RATE = 22050
PREFIX = "builtin:"
RANDOM = PREFIX + "random"
SILENT = "none"


def _run(notes, start=0.0, gap=0.1, length=0.16, kind="sine", level=0.5):
    return [(start + i * gap, length, f, f, kind, level) for i, f in enumerate(notes)]


SOUNDS = {
    "Chime": _run((660, 880, 1320), gap=0.12, length=0.35),
    "Soft bell": [(0, 1.0, 880, 880, "bell", 0.5), (0.18, 1.0, 1320, 1320, "bell", 0.3)],
    "Doorbell": [(0, 0.5, 784, 784, "bell", 0.5), (0.34, 0.8, 622, 622, "bell", 0.5)],
    "Sparkle": _run((1568, 1976, 2349, 2637, 3136), gap=0.06, length=0.22, kind="bell", level=0.3),
    "Bubble pop": [(0, 0.09, 300, 900, "sine", 0.6), (0.11, 0.09, 420, 1200, "sine", 0.5)],
    "Coin": [(0, 0.08, 988, 988, "square", 0.3), (0.08, 0.4, 1319, 1319, "square", 0.3)],
    "Coins pouring": _run((1319, 1568, 1319, 1760, 1568, 1976), gap=0.07, length=0.12, kind="square", level=0.22),
    "Cash register": [(0, 0.12, 1800, 1800, "bell", 0.5), (0.12, 0.09, 0, 0, "noise", 0.2), (0.2, 0.6, 2400, 2400, "bell", 0.5)],
    "Level up": _run((523, 659, 784, 1047, 1319), gap=0.09, length=0.14, kind="square", level=0.25),
    "Power up": [(0, 0.5, 220, 1760, "square", 0.25)],
    "Victory": _run((523, 523, 523, 698, 880), gap=0.13, length=0.16, kind="saw", level=0.28) + [(0.65, 0.55, 1047, 1047, "saw", 0.28)],
    "Fanfare": _run((392, 523, 659), gap=0.14, length=0.2, kind="saw", level=0.28) + [(0.42, 0.7, 784, 784, "saw", 0.32), (0.42, 0.7, 523, 523, "saw", 0.22)],
    "Hype horn": [(0, 0.28, 440, 440, "saw", 0.4), (0, 0.28, 554, 554, "saw", 0.3), (0.32, 0.6, 440, 460, "saw", 0.4), (0.32, 0.6, 554, 574, "saw", 0.3)],
    "Drum roll hit": [(i * 0.05, 0.05, 0, 0, "noise", 0.14 + i * 0.012) for i in range(14)] + [(0.72, 0.3, 120, 60, "sine", 0.7), (0.72, 0.18, 0, 0, "noise", 0.4)],
    "Boom": [(0, 0.7, 110, 35, "sine", 0.8), (0, 0.16, 0, 0, "noise", 0.4)],
    "Thunder": [(0, 1.1, 0, 0, "noise", 0.5), (0, 1.0, 70, 40, "sine", 0.6)],
    "Whoosh": [(0, 0.5, 0, 0, "swell", 0.5)],
    "Laser": [(0, 0.3, 1800, 200, "square", 0.25)],
    "Sci-fi scan": _run((880, 1175, 880, 1175, 1568), gap=0.09, length=0.1, kind="triangle", level=0.4),
    "Robot beep": _run((1000, 700, 1300), gap=0.11, length=0.09, kind="square", level=0.25),
    "Alarm": [(i * 0.22, 0.2, 700, 1100, "square", 0.22) for i in range(4)],
    "Warp": [(0, 0.8, 120, 2200, "triangle", 0.4)],
    "Magic harp": _run((523, 659, 784, 988, 1175, 1319, 1568, 1976), gap=0.055, length=0.5, kind="bell", level=0.22),
    "Happy marimba": _run((784, 988, 1175, 988, 1568), gap=0.11, length=0.22, kind="bell", level=0.45),
    "Sad trombone": [(0, 0.3, 392, 392, "saw", 0.3), (0.32, 0.3, 370, 370, "saw", 0.3), (0.64, 0.3, 349, 349, "saw", 0.3), (0.96, 0.8, 330, 300, "saw", 0.3)],
    "Heartbeat": [(0, 0.14, 80, 50, "sine", 0.8), (0.2, 0.16, 70, 45, "sine", 0.7)],
}
KEYS = {name: name.lower().replace(" ", "-") for name in SOUNDS}
BY_KEY = {key: name for name, key in KEYS.items()}

# One click gives every alert type a fitting sound.
PACKS = (
    ("Arcade", {"tip": "coin", "superchat": "level-up", "membership": "power-up", "subscriber": "robot-beep", "follow": "bubble-pop",
                "subscription": "level-up", "gift": "coins-pouring", "raid": "alarm"}),
    ("Soft", {"tip": "soft-bell", "superchat": "magic-harp", "membership": "sparkle", "subscriber": "chime", "follow": "bubble-pop",
              "subscription": "happy-marimba", "gift": "sparkle", "raid": "doorbell"}),
    ("Hype", {"tip": "cash-register", "superchat": "hype-horn", "membership": "fanfare", "subscriber": "victory", "follow": "whoosh",
              "subscription": "fanfare", "gift": "drum-roll-hit", "raid": "boom"}),
    ("Sci-fi", {"tip": "laser", "superchat": "warp", "membership": "sci-fi-scan", "subscriber": "robot-beep", "follow": "laser",
                "subscription": "sci-fi-scan", "gift": "power-up", "raid": "thunder"}),
)


def is_builtin(value):
    return str(value or "").startswith(PREFIX)


def choices():
    """(name, saved value) for the sound lists."""
    return [(name, PREFIX + KEYS[name]) for name in SOUNDS]


def url_for(value):
    return "/builtin-sound/%s.wav" % str(value)[len(PREFIX):] if str(value)[len(PREFIX):] in BY_KEY else ""


def all_urls():
    return ["/builtin-sound/%s.wav" % key for key in BY_KEY]


def _wave(kind, phase):
    turn = phase % 1.0
    if kind == "square":
        return 1.0 if turn < 0.5 else -1.0
    if kind == "saw":
        return 2.0 * turn - 1.0
    if kind == "triangle":
        return 4.0 * abs(turn - 0.5) - 1.0
    return math.sin(2 * math.pi * phase)


def _add(buffer, note, noise):
    start, length, f0, f1, kind, level = note
    first, count = int(start * RATE), int(length * RATE)
    phase = 0.0
    for i in range(count):
        at = first + i
        if at >= len(buffer):
            break
        t = i / count
        attack = min(1.0, i / (0.004 * RATE))
        if kind == "bell":
            envelope = attack * math.exp(-5.0 * t)
        elif kind == "swell":
            envelope = math.sin(math.pi * t)
        else:
            envelope = attack * min(1.0, (1.0 - t) * 6.0)
        phase += (f0 + (f1 - f0) * t) / RATE
        if kind in ("noise", "swell"):
            value = noise.uniform(-1, 1)
        elif kind == "bell":
            value = math.sin(2 * math.pi * phase) + 0.35 * math.sin(2 * math.pi * phase * 2.76)
        else:
            value = _wave(kind, phase)
        buffer[at] += value * envelope * level


_made = {}


def wav_bytes(key):
    """The finished WAV file for a sound key, or None for an unknown key. Made once, the first time it is needed."""
    if key not in BY_KEY:
        return None
    if key not in _made:
        notes = SOUNDS[BY_KEY[key]]
        total = int((max(n[0] + n[1] for n in notes) + 0.03) * RATE)
        buffer = [0.0] * total
        noise = random.Random(key)              # the same sound every time
        for note in notes:
            _add(buffer, note, noise)
        peak = max(1.0, max(abs(v) for v in buffer))
        frames = b"".join(struct.pack("<h", int(v / peak * 30000)) for v in buffer)
        out = io.BytesIO()
        with wave.open(out, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes(frames)
        _made[key] = out.getvalue()
    return _made[key]
