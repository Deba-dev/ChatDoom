"""Blocked-word matching that viewers can't easily dodge.

Catches b.c / b c / b-c, bhennnn, bh3n / ch0d, small caps and other lookalike letters, fullwidth letters,
zalgo marks, and a word typed in Devanagari when it was blocked in English letters (and the other way round).
No words live in this file: the streamer's own lists are passed in.
"""
import re
import unicodedata
from itertools import groupby

ZALGO = re.compile("[̀-ͯ҃-҉᪰-᫿᷀-᷿⃐-⃿︠-︯]")
LOOKALIKE = str.maketrans({
    # small caps
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f", "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k",
    "ʟ": "l", "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ǫ": "q", "ʀ": "r", "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v",
    "ᴡ": "w", "ʏ": "y", "ᴢ": "z",
    # Cyrillic and Greek letters that look Latin
    "а": "a", "в": "b", "с": "c", "ԁ": "d", "е": "e", "һ": "h", "н": "h", "і": "i", "ј": "j", "к": "k", "м": "m",
    "о": "o", "р": "p", "ѕ": "s", "т": "t", "у": "y", "х": "x", "ɡ": "g",
    "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x",
})
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
TOKEN = re.compile(r"[\w@$]+")
HAS_LETTER = re.compile(r"[^\W\d_]")
LATIN = re.compile(r"[a-z0-9]+")
DEVANAGARI = re.compile("[ऀ-ॿ]")
EDGE_L, EDGE_R = r"(?<![a-z0-9])", r"(?![a-z0-9])"
RUN_GAP = 3                     # at most this many dots/spaces/dashes between the letters of b . c
LOOSE_MIN = 5                   # blocked words this long (without a's) also match with a's dropped; shorter ones would hit normal words

VOWELS = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
          "ऋ": "ri", "ऑ": "o", "ऍ": "e"}
MATRAS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri",
          "ॉ": "o", "ॅ": "e"}
CONSONANTS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
              "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh",
              "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v",
              "श": "sh", "ष": "sh", "स": "s", "ह": "h"}
WITH_NUKTA = {"क": "k", "ख": "kh", "ग": "g", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f", "य": "y"}
NUKTA, VIRAMA = "़", "्"


def canonical(text):
    """One plain spelling of a message: no zalgo, lookalikes and leetspeak turned into normal letters, long letter runs cut to 2."""
    text = unicodedata.normalize("NFKD", text or "")                 # fullwidth and fancy letters become plain ones
    text = unicodedata.normalize("NFC", ZALGO.sub("", text))
    text = text.casefold().translate(LOOKALIKE)
    text = TOKEN.sub(lambda t: t.group().translate(LEET) if HAS_LETTER.search(t.group()) else t.group(), text)
    return re.sub(r"(.)\1{2,}", r"\1\1", text)                        # bhennnnn -> bhenn (blocked words go through the same)


def phon(text):
    """Spellings that sound the same: ph/f, w/v."""
    return text.replace("ph", "f").replace("w", "v")


def translit(text):
    """Devanagari in plain English letters, the way Hinglish chat spells it (चोद -> choda). Other letters stay."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in CONSONANTS:
            nxt = text[i + 1:i + 2]
            roman = CONSONANTS[c]
            if nxt == NUKTA:
                roman = WITH_NUKTA.get(c, roman)
                i += 1
                nxt = text[i + 1:i + 2]
            out.append(roman)
            if nxt in MATRAS:
                out.append(MATRAS[nxt])
                i += 1
            elif nxt == VIRAMA:
                i += 1
            else:
                out.append("a")
        elif c in VOWELS:
            out.append(VOWELS[c])
        elif c in "ँं":                                     # chandrabindu, anusvara
            out.append("n")
        elif c == "ः":
            out.append("h")
        elif c not in (NUKTA, VIRAMA):
            out.append(c)
        i += 1
    return "".join(out)


def skeleton(text):
    """For matching across scripts: without the a's (Hindi drops them unpredictably) and without doubled letters."""
    text = phon(text).replace("ee", "i").replace("oo", "u").replace("z", "j").replace("a", "")
    return re.sub(r"(.)\1+", r"\1", text)


def joined_runs(text):
    """Single letters split by dots, dashes or spaces glued back together: 'b . c' -> 'bc'. Normal words are left alone."""
    runs, cur, last_end = [], [], -99
    for t in LATIN.finditer(text):
        tok = t.group()
        if len(tok) == 1 and cur and t.start() - last_end <= RUN_GAP:
            cur.append(tok)
        else:
            if len(cur) > 1:
                runs.append("".join(cur))
            cur = [tok] if len(tok) == 1 else []
        last_end = t.end()
    if len(cur) > 1:
        runs.append("".join(cur))
    return runs


def _core(word):
    """Regex for a blocked word in English letters: each letter may repeat, gaps inside a phrase may be anything."""
    parts = []
    for ch, grp in groupby(word):
        k = len(list(grp))
        if not ch.isalnum():
            parts.append(r"[\W_]*")
        else:
            parts.append(re.escape(ch) + ("+" if k == 1 else "{%d,}" % k))
    return "".join(parts)


def _edged(core):
    return re.compile(EDGE_L + core + EDGE_R)


class WordGuard:
    def __init__(self, blocked=(), allowed=()):
        self.latin = []        # (whole-word regex, regex for inside a b.c run)
        self.hindi = []        # Devanagari words, found anywhere in the text
        self.cross_latin = []  # English-letter words, found in Devanagari text
        self.cross_hindi = []  # Devanagari words, found in English-letter text
        self.loose = []        # long English-letter words, also found with a's dropped (madrchod)
        for word in blocked:
            w = phon(canonical(word)).strip()
            if not w:
                continue
            if DEVANAGARI.search(w):
                self.hindi.append(w)
                sk = skeleton(translit(w))
                if len(sk) >= 3:
                    self.cross_hindi.append((_edged(re.escape(sk)), re.compile(re.escape(sk))))
            else:
                core = _core(w)
                self.latin.append((_edged(core), re.compile(core)))
                sk = skeleton(w)
                if len(sk) >= 3:
                    self.cross_latin.append(_edged(re.escape(sk)))
                if len(sk) >= LOOSE_MIN:
                    self.loose.append(_edged(re.escape(sk)))
        self.allowed = []
        for word in allowed:
            w = phon(canonical(word)).strip()
            if w:
                self.allowed.append(_edged(re.escape(w)) if not DEVANAGARI.search(w) else re.compile(re.escape(w)))

    def hit(self, text):
        """True when the text has a blocked word in any of its disguises (allowed words are removed first)."""
        if not (self.latin or self.hindi):
            return False
        t = phon(canonical(text))
        for allowed in self.allowed:
            t = allowed.sub(" ", t)
        runs = joined_runs(t)
        for whole, inside in self.latin:
            if whole.search(t) or any(inside.search(r) for r in runs):
                return True
        if any(w in t for w in self.hindi):
            return True
        if self.cross_latin and DEVANAGARI.search(t):
            sk = skeleton(translit(t))
            if any(p.search(sk) for p in self.cross_latin):
                return True
        if self.cross_hindi or self.loose:
            sk, sk_runs = skeleton(t), [skeleton(r) for r in runs]
            if any(p.search(sk) for p in self.loose):
                return True
            for whole, inside in self.cross_hindi:
                if whole.search(sk) or any(inside.search(r) for r in sk_runs):
                    return True
        return False
