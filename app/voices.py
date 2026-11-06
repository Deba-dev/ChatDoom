"""The voice catalog: every neural voice, how it is named in the app, and the ready-made ways to shape it."""
from .voice_list import VOICE_ROWS

FAVOURITES = (
    ("Hindi female - Swara", "hi-IN-SwaraNeural"),
    ("Hindi male - Madhur", "hi-IN-MadhurNeural"),
    ("Indian English female - Neerja", "en-IN-NeerjaNeural"),
    ("Indian English male - Prabhat", "en-IN-PrabhatNeural"),
)
BY_ID = {row[3]: row for row in VOICE_ROWS}
PINNED = ("Hindi (India)", "English (India)", "English (United States)", "English (United Kingdom)")
GENDERS = (("Any voice", ""), ("Female", "Female"), ("Male", "Male"))

# name, speed step, pitch in Hz
PRESETS = (
    ("Natural", 0, 0), ("Deep", -1, -25), ("Giant", -3, -45), ("Calm and slow", -2, -8), ("Announcer", 1, -12),
    ("Bright", 1, 15), ("Fast talker", 5, 0), ("Chipmunk", 4, 45),
)
PITCH_LIMIT = 50
RATE_LOW, RATE_HIGH = -5, 10

SAMPLES = {
    "hi": "नमस्ते दोस्तों, आपकी चैट मैं पढ़ूँगी।", "ru": "Привет всем, спасибо за стрим!", "ko": "안녕하세요, 방송 재미있어요!",
    "ja": "こんにちは、配信ありがとう！", "zh": "大家好，感谢观看直播！", "es": "Hola a todos, gracias por el directo.",
    "fr": "Bonjour à tous, merci pour le live.", "de": "Hallo zusammen, danke für den Stream.", "pt": "Olá pessoal, obrigado pela live.",
    "ar": "مرحبا بالجميع، شكرا على البث.", "bn": "সবাইকে নমস্কার, স্ট্রিমের জন্য ধন্যবাদ।", "ta": "அனைவருக்கும் வணக்கம், நன்றி!",
    "te": "అందరికీ నమస్కారం, ధన్యవాదాలు!",
}
SAMPLE_ENGLISH = "Hello everyone, this is how I will read your chat."


def label(voice):
    row = BY_ID.get(voice)
    if not row:
        return voice
    return "%s (%s)" % (row[1], row[2])


def full_label(voice):
    row = BY_ID.get(voice)
    return "%s, %s" % (label(voice), row[0]) if row else voice


def languages():
    """Every language, the ones most CHATDOOM streamers use first."""
    found = sorted({row[0] for row in VOICE_ROWS})
    return [name for name in PINNED if name in found] + [name for name in found if name not in PINNED]


def in_language(language, gender=""):
    return [row[3] for row in VOICE_ROWS if row[0] == language and (not gender or row[2] == gender)]


def language_of(voice):
    row = BY_ID.get(voice)
    return row[0] if row else ""


def for_language(code, gender=""):
    """The first voice for a language code like 'ko', or '' when there is none."""
    prefix = code.lower() + "-"
    rows = [row for row in VOICE_ROWS if row[3].lower().startswith(prefix)]
    picked = [row for row in rows if row[2] == gender] or rows
    return picked[0][3] if picked else ""


def sample_for(voice):
    return SAMPLES.get(voice.split("-", 1)[0].lower(), SAMPLE_ENGLISH)
