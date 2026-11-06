"""Designs for the chat, now playing, meme and widget overlays. They share the alert animations, fonts and packs (alert_styles.py),
plus one set of skins, so all overlays can match. Every skin has a CSS rule in overlay_html.py."""
import re

from . import style_fields
from .alert_styles import ENTERS, EXITS, FONTS, IDLES, LOOKS, PACKS, TEXT_FX, EFFECTS

KINDS = (("Chat", "chat"), ("Now playing", "music"), ("Memes", "meme"), ("Widgets", "widgets"))
KIND_KEYS = tuple(v for _, v in KINDS)
SKINS = (("Classic", "classic"), ("Glass bubbles", "glass"), ("Compact", "compact"), ("Streamer panel", "panel")) + tuple(
    (label, value) for label, value in LOOKS if value != "glass") + (("Text only", "plain"),)
ENTERS_ALL = (("Slide in gently", "nudge"),) + ENTERS
CORNERS = (("Bottom left", "bottom-left"), ("Bottom right", "bottom-right"), ("Top left", "top-left"), ("Top right", "top-right"))
SPOTS = (("Middle", "mid-center"), ("Top centre", "top-center"), ("Bottom centre", "bottom-center")) + CORNERS
ALIGNS = (("Left", "left"), ("Centre", "center"), ("Right", "right"))
EDGES = (("Bottom", "bottom"), ("Top", "top"))
NEWEST = (("At the end", "end"), ("At the start", "start"))
NAME_COLOURS = (("Platform colour", "platform"), ("Theme colour", "accent"), ("White", "white"))
SIDES = (("Right", "right"), ("Left", "left"))

COMMON = {"skin": "classic", "enter": "pop", "exit": "fade", "idle": "none", "text": "none", "font": "Poppins", "size": 100, "opacity": 100,
          "useColors": False, "c1": "#8b5cf6", "c2": "#22d3ee", "c3": "#f472b6"}
DEFAULTS = {
    "chat": dict(COMMON, enter="nudge", align="left", edge="bottom", newest="end", width=100, maxLines=8, showTag=True, nameColour="white",
                 hideCommands=False, keep=False),
    "music": dict(COMMON, enter="rise", exit="drop", position="bottom-left", showEq=True, showArtist=True),
    "meme": dict(COMMON, exit="out", effect="none", position="mid-center", picture=100, showCaption=True, showWho=True),
    "widgets": dict(COMMON, countersAt="top-left", panelSide="right", goalsAt="bottom-left", latestAt="bottom-right"),
}
for _kind, _design in DEFAULTS.items():
    _design.update(style_fields.defaults_for(_kind))
CHOICES = {"skin": SKINS, "enter": ENTERS_ALL, "exit": EXITS, "idle": IDLES, "text": TEXT_FX, "font": FONTS, "effect": EFFECTS, "align": ALIGNS,
           "edge": EDGES, "newest": NEWEST, "nameColour": NAME_COLOURS, "panelSide": SIDES, "countersAt": CORNERS, "goalsAt": CORNERS, "latestAt": CORNERS}
POSITION_CHOICES = {"music": CORNERS, "meme": SPOTS}
NUMBERS = {"size": (60, 180), "opacity": (30, 100), "width": (30, 100), "maxLines": (2, 20), "picture": (30, 100)}
FLAGS = ("useColors", "showTag", "hideCommands", "keep", "showEq", "showArtist", "showCaption", "showWho")
HEX = re.compile(r"#[0-9a-fA-F]{6}")

SAMPLES = {
    "chat": [{"platform": "youtube", "name": "Neha", "text": "Namaste doston! \U0001F64F"}, {"platform": "twitch", "name": "sneha_plays", "text": "hello from Twitch chat!"},
             {"platform": "kick", "name": "kickviewer", "text": "bhai kya clutch tha"}, {"platform": "youtube", "name": "Rahul", "text": "GG, next match?"}],
    "music": {"title": "Midnight Drive", "artist": "StreamBeats", "playing": True},
    "meme": {"name": "bruh", "user": "Rahul", "caption": "bruh moment", "image": ""},
    "widgets": {"counters": [{"label": "Deaths", "value": 7}, {"label": "Wins", "value": 3}],
                "poll": {"question": "Which game next?", "active": True, "total": 12, "endsIn": 45, "result": "",
                         "options": [{"text": "Valorant", "votes": 8}, {"text": "GTA", "votes": 4}]},
                "goals": [{"title": "Sub goal", "value": 32, "target": 50}], "latest": [{"label": "Latest tip", "value": "Rahul ₹100"}]},
}


def clean(kind, raw, base=None):
    """A complete, safe design. Anything unknown falls back, so an older or newer saved file can never break an overlay."""
    base = dict(base or DEFAULTS[kind])
    raw = raw if isinstance(raw, dict) else {}
    out = dict(base)
    choices = dict(CHOICES, position=POSITION_CHOICES.get(kind, ()))
    for key, options in choices.items():
        if key in base and raw.get(key) in [v for _, v in options]:
            out[key] = raw[key]
    for key in ("c1", "c2", "c3"):
        if HEX.fullmatch(str(raw.get(key) or "")):
            out[key] = raw[key]
    for key in FLAGS:
        if key in base and key in raw:
            out[key] = bool(raw[key])
    for key, (low, high) in NUMBERS.items():
        if key in base:
            try:
                out[key] = min(high, max(low, int(raw.get(key, out[key]))))
            except (TypeError, ValueError):
                pass
    return style_fields.clean_fields(raw, out, kind)


def design_for(settings, kind):
    saved = settings.get("ov_designs")
    saved = saved if isinstance(saved, dict) else {}
    base = dict(DEFAULTS[kind])
    if kind == "chat":                                 # the chat look chosen before this page existed
        base["skin"] = settings.get("ov_chat_style") or "glass"
        base = clean(kind, base)
    return clean(kind, saved.get(kind), base)


def all_designs(settings):
    return {kind: design_for(settings, kind) for kind in KIND_KEYS}


def save_design(settings, kind, design):
    saved = settings.get("ov_designs")
    saved = dict(saved) if isinstance(saved, dict) else {}
    saved[kind] = clean(kind, design)
    settings.set("ov_designs", saved)
    if kind == "chat" and saved[kind]["skin"] in ("glass", "compact", "panel", "sakura"):
        settings.set("ov_chat_style", saved[kind]["skin"])


def reset_design(settings, kind):
    saved = settings.get("ov_designs")
    saved = dict(saved) if isinstance(saved, dict) else {}
    saved.pop(kind, None)
    settings.set("ov_designs", saved)


def pack_for(kind, values):
    """An alert pack, made calm enough for this overlay. Chat lines and widgets stay on screen a long time, so they do not keep moving."""
    out = {"skin": values["look"], "enter": values["enter"], "exit": values["exit"], "font": values["font"], "text": values["text"]}
    if kind == "meme":
        out["idle"], out["effect"] = values["idle"], values["effect"]
    elif kind == "music":
        out["idle"] = values["idle"] if values["idle"] in ("float", "breathe", "glow", "none") else "none"
    if kind == "widgets":
        out["text"] = "none"
    if kind == "chat" and values["text"] in ("type", "shake", "flicker", "rainbow"):
        out["text"] = "none"
    return out


def match_all(settings, kind):
    """Gives every overlay, alerts included, the look of the one being edited."""
    from . import alert_styles
    source = design_for(settings, kind)
    shared = {k: source[k] for k in ("skin", "font", "useColors", "c1", "c2", "c3")}
    for other in KIND_KEYS:
        save_design(settings, other, dict(design_for(settings, other), **shared))
    if source["skin"] in [v for _, v in alert_styles.LOOKS]:
        main = alert_styles.main_design(settings)
        main.update(look=source["skin"], font=source["font"], useColors=source["useColors"], c1=source["c1"], c2=source["c2"], c3=source["c3"])
        settings.set("ov_alert_design", main)
        settings.set("ov_alert_style", main["look"])


__all__ = ["KINDS", "SKINS", "PACKS", "DEFAULTS", "CHOICES", "POSITION_CHOICES", "SAMPLES", "clean", "design_for", "all_designs", "save_design", "pack_for", "match_all"]
