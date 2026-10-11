"""Language detection and authenticated CHATDOOM cloud translation."""
import json
import urllib.error
import urllib.parse
import urllib.request

from langdetect import DetectorFactory, detect

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


def detect_source_language(text):
    return detect(text)


def translate_to_english(text, settings):
    source = LANGUAGE_CODES.get(detect_source_language(text))
    if not source:
        raise ValueError("the detected language is not supported by the translation model")
    if source == "en":
        return text, False

    base = str(settings.get("cloud_url") or "").strip().rstrip("/")
    token = str(settings.get("cloud_token") or "").strip()
    parsed = urllib.parse.urlsplit(base)
    if not token or not parsed.netloc or not (
            parsed.scheme == "https" or
            (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost"))):
        raise ValueError("connect CHATDOOM to its cloud service on the Discord page first")

    data = json.dumps({"text": text[:500], "source_lang": source}).encode("utf-8")
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
    return translated.strip(), True
