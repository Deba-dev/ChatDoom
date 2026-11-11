"""Alert designs: every look, animation, effect and font an on-screen alert can use, and the ready-made packs.

The overlay page (overlay_html.py) has one CSS rule per value here, so add a value in both places."""
import os
import re
import urllib.parse

from . import alert_sounds, style_fields

LOOKS = (("Neon energy", "neon"), ("Cherry blossom", "sakura"), ("Brush / ink", "brush"), ("Sharp frame", "frame"),
         ("Frosted glass", "glass"), ("Comic pop", "comic"), ("Cyber grid", "cyber"), ("Clean minimal", "minimal"),
         ("Arcade pixels", "arcade"), ("Royal gold", "royal"), ("Ribbon banner", "ribbon"), ("Paper note", "paper"),
         ("Hacker terminal", "terminal"), ("Soft bubble", "bubble"), ("Event ticket", "ticket"), ("Hologram", "holo"),
         ("Lava", "lava"), ("Ice crystal", "ice"))
ENTERS = (("Pop in", "pop"), ("Slide from left", "left"), ("Slide from right", "right"), ("Drop from top", "drop"),
          ("Rise from below", "rise"), ("Flip over", "flip"), ("Zoom in", "zoom"), ("Spin in", "spin"), ("Bounce in", "bounce"),
          ("Glitch in", "glitch"), ("Blur in", "blur"), ("Swing in", "swing"), ("Unfold", "unfold"), ("Warp in", "warp"))
EXITS = (("Float away", "out"), ("Fade out", "fade"), ("Slide left", "left"), ("Slide right", "right"), ("Fall down", "drop"),
         ("Fly up", "rise"), ("Shrink", "zoom"), ("Spin away", "spin"), ("Blur out", "blur"), ("Flip away", "flip"))
IDLES = (("Gentle float", "float"), ("Pulse", "pulse"), ("Wobble", "wobble"), ("Glow", "glow"), ("Tilt", "tilt"),
         ("Breathe", "breathe"), ("Jitter", "jitter"), ("Stay still", "none"))
TEXT_FX = (("No text animation", "none"), ("Wave", "wave"), ("Bouncing letters", "bounce"), ("Typewriter", "type"),
           ("Rainbow", "rainbow"), ("Shake", "shake"), ("Glow", "glow"), ("Letters pop in", "pop"), ("Flicker", "flicker"),
           ("Letters slide in", "slide"))
EFFECTS = (("Sparkles", "sparkles"), ("Confetti", "confetti"), ("Hearts", "hearts"), ("Stars", "stars"), ("Money", "money"),
           ("Fire", "fire"), ("Party", "party"), ("Snow", "snow"), ("Flowers", "flowers"), ("Lightning", "bolts"), ("None", "none"))
# Google Fonts names, loaded by the overlay. The ones marked (Hindi) also have Devanagari letters.
FONTS = (("Poppins (built in)", "Poppins"), ("Baloo 2 (Hindi)", "Baloo 2"), ("Mukta (Hindi)", "Mukta"), ("Hind (Hindi)", "Hind"),
         ("Teko (Hindi)", "Teko"), ("Rozha One (Hindi)", "Rozha One"), ("Yatra One (Hindi)", "Yatra One"), ("Bangers", "Bangers"),
         ("Bebas Neue", "Bebas Neue"), ("Anton", "Anton"), ("Orbitron", "Orbitron"), ("Press Start 2P", "Press Start 2P"),
         ("Russo One", "Russo One"), ("Audiowide", "Audiowide"), ("Righteous", "Righteous"), ("Lobster", "Lobster"),
         ("Pacifico", "Pacifico"), ("Permanent Marker", "Permanent Marker"), ("Creepster", "Creepster"), ("Cinzel", "Cinzel"),
         ("Fredoka", "Fredoka"), ("Oswald", "Oswald"), ("Montserrat", "Montserrat"), ("VT323", "VT323"))
POSITIONS = (("Top centre", "top-center"), ("Top left", "top-left"), ("Top right", "top-right"), ("Middle", "mid-center"),
             ("Middle left", "mid-left"), ("Middle right", "mid-right"), ("Bottom centre", "bottom-center"),
             ("Bottom left", "bottom-left"), ("Bottom right", "bottom-right"))
LAYOUTS = (("Picture above the text", "above"), ("Picture beside the text", "side"), ("Picture behind the text", "behind"))
ALERT_TYPES = (("Tips", "tip"), ("Super Chats and Bits", "superchat"), ("Memberships", "membership"), ("YouTube subscribers", "subscriber"),
               ("Follows", "follow"), ("Subscriptions", "subscription"), ("Gifted subs", "gift"), ("Raids", "raid"))
TYPE_KEYS = tuple(v for _, v in ALERT_TYPES)

DEFAULT = {"look": "neon", "enter": "pop", "exit": "out", "idle": "float", "text": "none", "effect": "sparkles", "font": "Poppins",
           "size": 100, "position": "top-center", "layout": "above", "useColors": False, "c1": "#8b5cf6", "c2": "#22d3ee", "c3": "#f472b6",
           "template": "", "image": "", "sound": "", "soundVolume": 80, "seconds": 0, **style_fields.defaults_for("alert")}
CHOICES = {"look": LOOKS, "enter": ENTERS, "exit": EXITS, "idle": IDLES, "text": TEXT_FX, "effect": EFFECTS, "font": FONTS,
           "position": POSITIONS, "layout": LAYOUTS}

SAMPLES = {
    "tip": {"platform": "tip", "category": "tip", "name": "Rahul", "amount": "₹100", "message": "Great stream bhai, keep it up!"},
    "superchat": {"platform": "youtube", "category": "superchat", "name": "Neha", "amount": "₹500", "message": "Clutch tha yaar!"},
    "membership": {"platform": "youtube", "category": "membership", "name": "Aman", "amount": "Level 1", "message": ""},
    "subscriber": {"platform": "youtube", "category": "subscriber", "name": "Priya", "amount": "", "message": ""},
    "follow": {"platform": "twitch", "category": "follow", "name": "sneha_plays", "amount": "", "message": ""},
    "subscription": {"platform": "twitch", "category": "subscription", "name": "kickviewer", "amount": "Tier 1", "message": ""},
    "gift": {"platform": "twitch", "category": "gift", "name": "BigBoss", "amount": "5 subs", "message": ""},
    "raid": {"platform": "twitch", "category": "raid", "name": "FriendlyStreamer", "amount": "120 viewers", "message": ""},
}

# One click sets the whole look. Fonts and text are chosen to match each pack.
PACKS = (
    ("Neon night", {"look": "neon", "enter": "pop", "exit": "out", "idle": "float", "text": "glow", "effect": "sparkles", "font": "Orbitron"}),
    ("Desi festival", {"look": "royal", "enter": "unfold", "exit": "fade", "idle": "glow", "text": "pop", "effect": "flowers", "font": "Rozha One"}),
    ("Comic hit", {"look": "comic", "enter": "bounce", "exit": "drop", "idle": "wobble", "text": "bounce", "effect": "stars", "font": "Bangers"}),
    ("Retro arcade", {"look": "arcade", "enter": "drop", "exit": "drop", "idle": "jitter", "text": "flicker", "effect": "stars", "font": "Press Start 2P"}),
    ("Cyber breach", {"look": "cyber", "enter": "glitch", "exit": "blur", "idle": "jitter", "text": "shake", "effect": "bolts", "font": "Audiowide"}),
    ("Terminal", {"look": "terminal", "enter": "unfold", "exit": "fade", "idle": "none", "text": "type", "effect": "none", "font": "VT323"}),
    ("Cherry blossom", {"look": "sakura", "enter": "rise", "exit": "fade", "idle": "breathe", "text": "wave", "effect": "flowers", "font": "Pacifico"}),
    ("Royal gold", {"look": "royal", "enter": "zoom", "exit": "zoom", "idle": "glow", "text": "glow", "effect": "money", "font": "Cinzel"}),
    ("Lava burst", {"look": "lava", "enter": "warp", "exit": "drop", "idle": "pulse", "text": "shake", "effect": "fire", "font": "Anton"}),
    ("Ice cold", {"look": "ice", "enter": "blur", "exit": "blur", "idle": "breathe", "text": "slide", "effect": "snow", "font": "Montserrat"}),
    ("Party time", {"look": "bubble", "enter": "spin", "exit": "spin", "idle": "tilt", "text": "rainbow", "effect": "party", "font": "Fredoka"}),
    ("Clean pro", {"look": "minimal", "enter": "left", "exit": "left", "idle": "none", "text": "none", "effect": "none", "font": "Montserrat"}),
    ("Hologram", {"look": "holo", "enter": "flip", "exit": "flip", "idle": "float", "text": "flicker", "effect": "sparkles", "font": "Russo One"}),
    ("Street ink", {"look": "brush", "enter": "swing", "exit": "right", "idle": "tilt", "text": "pop", "effect": "confetti", "font": "Permanent Marker"}),
)
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def clean(raw, base=None):
    """A complete, safe design. Anything unknown (say, from a newer or older version) falls back to the base design."""
    base = base or DEFAULT
    raw = raw if isinstance(raw, dict) else {}
    out = dict(base)
    for key, options in CHOICES.items():
        if raw.get(key) in [v for _, v in options]:
            out[key] = raw[key]
    for key in ("c1", "c2", "c3"):
        if HEX.fullmatch(str(raw.get(key) or "")):
            out[key] = raw[key]
    if "useColors" in raw:
        out["useColors"] = bool(raw["useColors"])
    for key, low, high in (("size", 60, 160), ("seconds", 0, 60), ("soundVolume", 0, 100)):
        try:
            out[key] = min(high, max(low, int(raw.get(key, out[key]))))
        except (TypeError, ValueError):
            pass
    for key, limit in (("template", 160), ("image", 220), ("sound", 220)):
        if key in raw:
            out[key] = str(raw.get(key) or "")[:limit]
    return style_fields.clean_fields(raw, out, "alert")


def main_design(settings):
    return clean(settings.get("ov_alert_design"), dict(DEFAULT, look=settings.get("ov_alert_style") or "neon"))


def custom_designs(settings):
    saved = settings.get("ov_alert_custom")
    return {k: v for k, v in saved.items() if k in TYPE_KEYS and isinstance(v, dict)} if isinstance(saved, dict) else {}


def design_for(settings, kind):
    main, custom = main_design(settings), custom_designs(settings)
    return clean(custom[kind], main) if kind in custom else main


# ---------- tips by amount: a bigger tip can get a bigger alert ----------
MAX_TIERS = 5
TIER_MAX_FROM = 10000000
TIER_STARTS = (100, 500, 2000, 5000, 10000)    # what "Add tier" suggests, in rupees
# What a new tier looks like, from small to big, so each step up is visibly bigger
TIER_PRESETS = (
    {"look": "neon", "effect": "sparkles", "size": 110, "enter": "pop", "seconds": 8},
    {"look": "royal", "effect": "money", "size": 120, "enter": "zoom", "idle": "glow", "text": "glow", "font": "Cinzel", "seconds": 10},
    {"look": "lava", "effect": "fire", "size": 135, "enter": "warp", "idle": "pulse", "text": "shake", "font": "Anton", "seconds": 12},
    {"look": "holo", "effect": "party", "size": 150, "enter": "flip", "idle": "float", "text": "rainbow", "font": "Russo One", "seconds": 14},
    {"look": "royal", "effect": "money", "size": 160, "enter": "unfold", "idle": "glow", "text": "pop", "font": "Rozha One", "seconds": 16,
     "position": "mid-center"},
)


def tip_tiers(settings):
    """The saved tiers, tidy and sorted by amount: [{"from": rupees, "design": {...}}]. Broken entries are dropped."""
    raw = settings.get("ov_tip_tiers")
    out, seen = [], set()
    for t in raw if isinstance(raw, list) else []:
        try:
            start = int(t.get("from"))
        except (AttributeError, TypeError, ValueError):
            continue
        if not 1 <= start <= TIER_MAX_FROM or start in seen:
            continue
        seen.add(start)
        out.append({"from": start, "design": t.get("design") if isinstance(t.get("design"), dict) else {}})
    return sorted(out, key=lambda t: t["from"])[:MAX_TIERS]


def tier_design(settings, index):
    """A tier's full design: what it changed, on top of the Tips design."""
    tiers = tip_tiers(settings)
    return clean(tiers[index]["design"], design_for(settings, "tip"))


def tier_index(settings, rupees):
    """Which tier a tip of this many rupees gets, or None for the normal Tips design."""
    best = None
    for i, t in enumerate(tip_tiers(settings)):
        if rupees >= t["from"]:
            best = i
    return best


def add_tier(settings, start=None):
    """Adds a tier from the next suggested amount (or the one given). Returns its index, or None when full or taken."""
    tiers = tip_tiers(settings)
    if len(tiers) >= MAX_TIERS:
        return None
    taken = {t["from"] for t in tiers}
    if start is None:
        start = next((v for v in TIER_STARTS if v not in taken), max(taken or {0}) * 2 or 100)
    start = int(start)
    if start in taken or not 1 <= start <= TIER_MAX_FROM:
        return None
    preset = TIER_PRESETS[min(len(tiers), len(TIER_PRESETS) - 1)]
    tiers.append({"from": start, "design": clean(preset, design_for(settings, "tip"))})
    tiers.sort(key=lambda t: t["from"])
    settings.set("ov_tip_tiers", tiers)
    return next(i for i, t in enumerate(tiers) if t["from"] == start)


def set_tier(settings, index, start=None, design=None):
    """Changes one tier's amount and/or design. Returns its new index (tiers stay sorted), or None if the amount is taken."""
    tiers = tip_tiers(settings)
    tier = tiers[index]
    if start is not None:
        start = int(start)
        if not 1 <= start <= TIER_MAX_FROM or any(t["from"] == start for i, t in enumerate(tiers) if i != index):
            return None
        tier["from"] = start
    if design is not None:
        tier["design"] = design
    tiers.sort(key=lambda t: t["from"])
    settings.set("ov_tip_tiers", tiers)
    return tiers.index(tier)


def remove_tier(settings, index):
    tiers = tip_tiers(settings)
    if 0 <= index < len(tiers):
        tiers.pop(index)
        settings.set("ov_tip_tiers", tiers)


def overlay_tip_tiers(settings, sounds_dir, memes_dir):
    """For the overlay: [{"from": rupees, "design": full design}] sorted by amount."""
    out = []
    for i, t in enumerate(tip_tiers(settings)):
        d = for_overlay(tier_design(settings, i), sounds_dir, memes_dir)
        d["tier"] = True
        d["ownSound"] = bool(t["design"].get("sound"))      # a tier's own sound beats the Tips alert sound
        out.append({"from": t["from"], "design": d})
    return out


def _inside(folder, name):
    """Only a plain file directly in the folder may reach the overlay."""
    name = os.path.basename(name or "")
    path = os.path.realpath(os.path.join(folder, name))
    return bool(name) and os.path.dirname(path) == os.path.realpath(folder) and os.path.isfile(path)


def sound_for_overlay(value, sounds_dir):
    """What the overlay needs for a saved sound: a built-in, a Soundboard file, a random pick or no sound at all."""
    if value == alert_sounds.SILENT:
        return {"soundUrl": "", "noSound": True}
    if value == alert_sounds.RANDOM:
        return {"soundUrl": "", "soundRandom": alert_sounds.all_urls()}
    if alert_sounds.is_builtin(value):
        return {"soundUrl": alert_sounds.url_for(value)}
    return {"soundUrl": "/sounds/" + urllib.parse.quote(os.path.basename(value)) if _inside(sounds_dir, value) else ""}


def for_overlay(design, sounds_dir, memes_dir):
    d = dict(design)
    d["imageUrl"] = "/memes/" + urllib.parse.quote(os.path.basename(d["image"])) if _inside(memes_dir, d["image"]) else ""
    d.update(sound_for_overlay(d["sound"], sounds_dir))
    del d["image"], d["sound"]
    return d


def type_sounds(settings):
    saved = settings.get("ov_type_sounds")
    return {k: str(v) for k, v in saved.items() if k in TYPE_KEYS and v} if isinstance(saved, dict) else {}


def overlay_type_sounds(settings, sounds_dir):
    return {kind: sound_for_overlay(value, sounds_dir) for kind, value in type_sounds(settings).items()}


def overlay_designs(settings, sounds_dir, memes_dir):
    out = {"default": for_overlay(main_design(settings), sounds_dir, memes_dir)}
    for kind in custom_designs(settings):
        out[kind] = for_overlay(design_for(settings, kind), sounds_dir, memes_dir)
    return out
