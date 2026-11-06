"""Language detection and authenticated CHATDOOM cloud translation."""
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from langdetect import DetectorFactory, detect, detect_langs

from . import hinglish

DetectorFactory.seed = 0

LANGUAGE_CODES = {
    "af": "af", "ar": "ar", "bg": "bg", "bn": "bn", "ca": "ca", "cs": "cs", "cy": "cy", "da": "da",
    "de": "de", "el": "el", "en": "en", "es": "es", "et": "et", "fa": "fa",
    "fi": "fi", "fr": "fr", "gu": "gu", "he": "he", "hi": "hi", "hr": "hr",
    "hu": "hu", "id": "id", "it": "it", "ja": "ja", "jv": "jv", "ka": "ka",
    "kk": "kk", "km": "km", "kn": "kn", "ko": "ko", "lo": "lo", "lt": "lt",
    "lv": "lv", "mk": "mk", "ml": "ml", "mn": "mn", "mr": "mr", "ms": "ms",
    "my": "my", "ne": "ne", "nl": "nl", "no": "no", "pa": "pa", "pl": "pl", "pt": "pt",
    "ro": "ro", "ru": "ru", "si": "si", "sk": "sk", "sl": "sl", "sq": "sq",
    "so": "so", "sv": "sv", "sw": "sw", "ta": "ta", "te": "te", "th": "th", "tl": "tl",
    "tr": "tr", "uk": "uk", "ur": "ur", "vi": "vi", "zh-cn": "zh", "zh-tw": "zh",
    "iw": "he",
}

CHOICES = (("Russian", "ru"), ("Korean", "ko"), ("Chinese", "zh"), ("Japanese", "ja"))
DEFAULT_LANGUAGES = tuple(code for _, code in CHOICES)
TARGETS = (("English", "en"), ("Hindi", "hi"))
MIN_LATIN_WORDS = 4
MIN_LATIN_CONFIDENCE = 0.9
MIN_SURE_CYRILLIC_WORDS = 3
CACHE_MAX = 500

_cache = {}
_flying = {}
_cache_lock = threading.Lock()


def script_language(text):
    """The language a writing system gives away, with no guessing: langdetect mixes up short Korean, Japanese and Chinese chat.
    Empty when the script does not settle it."""
    kana = hangul = han = cyrillic = devanagari = 0
    for c in text:
        o = ord(c)
        if 0x3040 <= o <= 0x30FF:
            kana += 1
        elif 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF:
            hangul += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            han += 1
        elif 0x0400 <= o <= 0x04FF:
            cyrillic += 1
        elif 0x0900 <= o <= 0x097F:
            devanagari += 1
    if kana:
        return "ja"
    if hangul:
        return "ko"
    if han:
        return "zh"
    if devanagari:
        return "hi"
    if cyrillic:
        return "ru"
    return ""


def detect_source_language(text):
    """A langdetect language name for any message. Cyrillic needs a few words before Ukrainian or Bulgarian can be told from Russian."""
    script = script_language(text)
    if script in ("ja", "ko", "hi"):
        return script
    if script == "zh":
        return "zh-cn"
    if script == "ru" and len(text.split()) < MIN_SURE_CYRILLIC_WORDS:
        return "ru"
    return detect(text)


def worth_translating(text):
    """Short Latin-script chat fools langdetect with full confidence ("HELLO" is "Vietnamese"), and Hinglish has no
    language code at all, so only clear cases go to the cloud. Other scripts are safe to detect."""
    if any(c.isalpha() and ord(c) > 0x24F for c in text):
        return True
    words = re.findall(r"[^\W\d_]+", text.lower())
    if len(words) < MIN_LATIN_WORDS or 3 * sum(w in hinglish.word_map for w in words) >= len(words):
        return False
    return detect_langs(text)[0].prob >= MIN_LATIN_CONFIDENCE


def wanted(source, settings):
    """Only the languages the streamer ticked are translated, so the shared daily allowance goes on them."""
    if settings.get("translate_others"):
        return True
    chosen = settings.get("translate_langs")
    return source in (DEFAULT_LANGUAGES if chosen is None else chosen)


def target_language(settings):
    target = settings.get("translate_target") or "en"
    return target if target in LANGUAGE_CODES else "en"


def _cloud_translate(text, source, target, settings):
    base = str(settings.get("cloud_url") or "").strip().rstrip("/")
    token = str(settings.get("cloud_token") or "").strip()
    parsed = urllib.parse.urlsplit(base)
    if not token or not parsed.netloc or not (
            parsed.scheme == "https" or
            (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost"))):
        raise ValueError("connect CHATDOOM to its cloud service on the Discord page first")

    data = json.dumps({"text": text[:500], "source_lang": source, "target_lang": target}).encode("utf-8")
    request = urllib.request.Request(
        base + "/api/translate", data=data, method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "Authorization": "Bearer " + token, "User-Agent": "CHATDOOM/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            result = json.loads(error.read())
            message = result.get("error") or "translation service returned HTTP %d" % error.code
        except Exception:
            message = "translation service returned HTTP %d" % error.code
        raise RuntimeError(message)
    except Exception as error:
        raise RuntimeError("could not reach the translation service (%s)" % str(error)[:80])

    translated = result.get("translation")
    if not isinstance(translated, str) or not translated.strip():
        raise RuntimeError(result.get("error") or "translation service returned no translated text")
    return translated.strip()


def _once(key, work):
    """The chat feed and the voice ask for the same message at the same moment: only one of them reaches the cloud."""
    while True:
        with _cache_lock:
            if key in _cache:
                return _cache[key]
            wait = _flying.get(key)
            if wait is None:
                done = _flying[key] = threading.Event()
                break
        wait.wait(25)
    try:
        answer = work()
        with _cache_lock:
            if len(_cache) >= CACHE_MAX:
                _cache.clear()
            _cache[key] = answer
        return answer
    finally:
        with _cache_lock:
            _flying.pop(key, None)
        done.set()


def translate_message(text, settings, force=False):
    """(translated text, source language, True) or (text, "", False). force: the streamer asked for this one message."""
    if not worth_translating(text) and not force:
        return text, "", False
    source = LANGUAGE_CODES.get(detect_source_language(text))
    if not source:
        raise ValueError("the detected language is not supported by the translation model")
    target = target_language(settings)
    if source == target or not (force or wanted(source, settings)):
        return text, source, False
    return _once((text, target), lambda: _cloud_translate(text, source, target, settings)), source, True


def translate_to_english(text, settings):
    """The voice's call. Named for what it did first: the target language is now a setting."""
    words, _, done = translate_message(text, settings)
    return words, done
