"""The fine-detail options for alerts and overlays, as one list. The design pages build their controls from it, clean() checks saved values
against it, and overlay_html.py turns them into CSS. To add an option: add a row here, then use it in overlay_html.py."""
import re

ALL = ("alert", "chat", "music", "meme", "widgets")
OVERLAYS = ALL[1:]
HEX = re.compile(r"#[0-9a-fA-F]{6}")
CSS_LIMIT = 4000
MAX_MY_STYLES = 20

SHADOWS = (("Skin's own", "skin"), ("None", "none"), ("Soft", "soft"), ("Strong", "strong"), ("Glow", "glow"))
WEIGHTS = (("Skin's own", "skin"), ("Regular", "400"), ("Medium", "500"), ("Semi bold", "600"), ("Bold", "700"), ("Extra bold", "800"), ("Black", "900"))
CASES = (("As typed", "none"), ("UPPERCASE", "uppercase"), ("lowercase", "lowercase"), ("Capitalize", "capitalize"))
TEXT_SHADOWS = (("Skin's own", "skin"), ("None", "none"), ("Soft", "soft"), ("Strong", "strong"), ("Thick outline", "outline"))
TAG_STYLES = (("Full name", "full"), ("Short (YT, TW, KK)", "short"), ("Coloured dot", "dot"))
NAME_ENDS = (("Nothing", "none"), ("Colon", "colon"), ("Arrow", "arrow"))
ABOVE_BELOW = (("Below the picture", "below"), ("Above the picture", "above"))
BAR_STYLES = (("Gradient", "gradient"), ("Solid", "solid"), ("Stripes", "stripes"))
GOAL_TEXTS = (("32 / 50", "both"), ("Only 64%", "percent"), ("32 / 50 and 64%", "all"))
COUNTER_ORDER = (("Number first", "number"), ("Label first", "label"))

# key, type, default, label, note, extra (choices, or low and high, or a text limit), which designs have it, card title
FIELDS = (
    # ----- background and frame -----
    ("useBg", "flag", False, "Use my own background", "Replaces the skin's background.", None, ALL, "Background and frame"),
    ("bgColor", "color", "#0c0a20", "Background colour", "", None, ALL, "Background and frame"),
    ("bgOpacity", "num", 85, "Background strength", "0 is fully see-through.", (0, 100), ALL, "Background and frame"),
    ("blur", "num", 0, "Blur behind", "Frosted glass effect, in pixels.", (0, 24), ALL, "Background and frame"),
    ("borderWidth", "num", 0, "Border thickness", "0 keeps the skin's border.", (0, 14), ALL, "Background and frame"),
    ("borderColor", "color", "#22d3ee", "Border colour", "", None, ALL, "Background and frame"),
    ("radius", "num", -1, "Rounded corners", "-1 keeps the skin's corners.", (-1, 70), ALL, "Background and frame"),
    ("padding", "num", 100, "Inner space", "100 is the skin's normal space.", (40, 220), ALL, "Background and frame"),
    ("shadow", "choice", "skin", "Shadow", "", SHADOWS, ALL, "Background and frame"),
    ("shadowColor", "color", "#8b5cf6", "Shadow colour", "Used by Glow.", None, ALL, "Background and frame"),
    # ----- text detail -----
    ("weight", "choice", "skin", "Thickness", "", WEIGHTS, ALL, "Text detail"),
    ("letterSpacing", "num", 0, "Letter spacing", "In pixels.", (-3, 14), ALL, "Text detail"),
    ("lineHeight", "num", 0, "Line height", "0 keeps the normal height.", (0, 220), ALL, "Text detail"),
    ("textCase", "choice", "none", "Letter case", "", CASES, ALL, "Text detail"),
    ("italic", "flag", False, "Italic", "", None, ALL, "Text detail"),
    ("useInk", "flag", False, "Use my own text colour", "", None, ALL, "Text detail"),
    ("ink", "color", "#ffffff", "Text colour", "", None, ALL, "Text detail"),
    ("textShadow", "choice", "skin", "Text shadow", "An outline keeps text readable over a bright game.", TEXT_SHADOWS, ALL, "Text detail"),
    # ----- motion and place -----
    ("speed", "num", 100, "Animation speed", "200 is twice as fast.", (25, 300), ALL, "Motion and place"),
    ("offsetX", "num", 0, "Move sideways", "In pixels.", (-800, 800), ALL, "Motion and place"),
    ("offsetY", "num", 0, "Move up or down", "In pixels.", (-500, 500), ALL, "Motion and place"),
    ("tilt", "num", 0, "Tilt", "In degrees.", (-25, 25), ALL, "Motion and place"),
    # ----- chat -----
    ("tagStyle", "choice", "full", "Platform tag", "", TAG_STYLES, ("chat",), "Chat lines"),
    ("nameEnd", "choice", "none", "After the name", "", NAME_ENDS, ("chat",), "Chat lines"),
    ("stacked", "flag", False, "Message under the name", "", None, ("chat",), "Chat lines"),
    ("showTime", "flag", False, "Show the time", "", None, ("chat",), "Chat lines"),
    ("lineGap", "num", 6, "Space between lines", "In pixels.", (0, 40), ("chat",), "Chat lines"),
    ("nameSize", "num", 100, "Name size", "Percent.", (60, 220), ("chat",), "Chat lines"),
    ("textSize", "num", 100, "Message size", "Percent.", (60, 220), ("chat",), "Chat lines"),
    ("useMsgColour", "flag", False, "Use my own message colour", "", None, ("chat",), "Chat lines"),
    ("msgColour", "color", "#e8e8f0", "Message colour", "", None, ("chat",), "Chat lines"),
    ("usePlatformColours", "flag", False, "Use my own platform colours", "Used for tags and platform-coloured names.", None, ("chat",), "Platform colours"),
    ("youtubeColour", "color", "#ff4d4d", "YouTube", "", None, ("chat",), "Platform colours"),
    ("twitchColour", "color", "#9146ff", "Twitch", "", None, ("chat",), "Platform colours"),
    ("kickColour", "color", "#53fc18", "Kick", "", None, ("chat",), "Platform colours"),
    ("highlightMods", "flag", False, "Highlight moderators", "", None, ("chat",), "Highlights and filters"),
    ("modColour", "color", "#34d399", "Moderator colour", "", None, ("chat",), "Highlights and filters"),
    ("highlightWord", "text", "", "Highlight lines with this word", "Your name, for example.", 40, ("chat",), "Highlights and filters"),
    ("wordColour", "color", "#fbbf24", "Highlight colour", "", None, ("chat",), "Highlights and filters"),
    ("hideLinks", "flag", False, "Hide messages with links", "", None, ("chat",), "Highlights and filters"),
    ("hideUsers", "text", "", "Hide these viewers", "Names separated by commas, like your bot.", 300, ("chat",), "Highlights and filters"),
    ("maxChars", "num", 0, "Cut long messages at", "Characters. 0 shows all of it.", (0, 500), ("chat",), "Highlights and filters"),
    # ----- now playing -----
    ("prefix", "text", "", "Label above the song", "Like Now playing.", 30, ("music",), "Song details"),
    ("maxWidth", "num", 560, "Widest size", "In pixels.", (200, 1100), ("music",), "Song details"),
    ("titleSize", "num", 100, "Title size", "Percent.", (60, 220), ("music",), "Song details"),
    ("artistSize", "num", 100, "Artist size", "Percent.", (60, 220), ("music",), "Song details"),
    ("marquee", "flag", False, "Scroll the title", "", None, ("music",), "Song details"),
    ("eqBars", "num", 4, "Moving bars", "", (2, 8), ("music",), "Song details"),
    ("autoHide", "num", 0, "Hide after", "Seconds after a song starts. 0 stays on screen.", (0, 60), ("music",), "Song details"),
    # ----- memes -----
    ("captionAt", "choice", "below", "Caption", "", ABOVE_BELOW, ("meme",), "Meme details"),
    ("captionSize", "num", 100, "Caption size", "Percent.", (60, 220), ("meme",), "Meme details"),
    ("pictureRadius", "num", 18, "Picture corners", "", (0, 70), ("meme",), "Meme details"),
    ("pictureGlow", "flag", True, "Glow around the picture", "", None, ("meme",), "Meme details"),
    # ----- widgets -----
    ("showCounters", "flag", True, "Counters", "", None, ("widgets",), "What shows"),
    ("showPoll", "flag", True, "Polls", "", None, ("widgets",), "What shows"),
    ("showPrediction", "flag", True, "Predictions", "", None, ("widgets",), "What shows"),
    ("showGiveaway", "flag", True, "Giveaway", "", None, ("widgets",), "What shows"),
    ("showQueue", "flag", True, "Viewer queue", "", None, ("widgets",), "What shows"),
    ("showGoals", "flag", True, "Goals", "", None, ("widgets",), "What shows"),
    ("showLatest", "flag", True, "Latest supporters", "", None, ("widgets",), "What shows"),
    ("groupGap", "num", 16, "Space between panels", "In pixels.", (0, 50), ("widgets",), "Panels and bars"),
    ("panelWidth", "num", 440, "Panel width", "In pixels.", (240, 900), ("widgets",), "Panels and bars"),
    ("titleSizeW", "num", 100, "Panel title size", "Percent.", (60, 220), ("widgets",), "Panels and bars"),
    ("queueNames", "num", 5, "Names in the queue", "", (1, 10), ("widgets",), "Panels and bars"),
    ("barStyle", "choice", "gradient", "Bar style", "", BAR_STYLES, ("widgets",), "Panels and bars"),
    ("barHeight", "num", 13, "Goal bar height", "In pixels.", (4, 44), ("widgets",), "Panels and bars"),
    ("barRadius", "num", 7, "Goal bar corners", "", (0, 22), ("widgets",), "Panels and bars"),
    ("goalText", "choice", "both", "Goal numbers", "", GOAL_TEXTS, ("widgets",), "Panels and bars"),
    ("countersRow", "flag", False, "Counters side by side", "", None, ("widgets",), "Panels and bars"),
    ("counterOrder", "choice", "number", "Counter order", "", COUNTER_ORDER, ("widgets",), "Panels and bars"),
    ("latestRow", "flag", False, "Latest supporters side by side", "", None, ("widgets",), "Panels and bars"),
    # ----- code -----
    ("css", "css", "", "Custom CSS", "Added to the overlay page last, so it wins. For people who know CSS.", CSS_LIMIT, ALL, "Custom CSS"),
)


def fields_for(kind):
    return [f for f in FIELDS if kind in f[6]]


def defaults_for(kind):
    return {f[0]: f[2] for f in fields_for(kind)}


def clean_fields(raw, out, kind):
    """Copies valid values from raw into out. Anything invalid keeps the value already in out."""
    for key, kind_of, _default, _label, _note, extra, _kinds, _card in fields_for(kind):
        if key not in raw:
            continue
        value = raw[key]
        if kind_of == "flag":
            out[key] = bool(value)
        elif kind_of == "color":
            if HEX.fullmatch(str(value or "")):
                out[key] = value
        elif kind_of == "choice":
            if value in [v for _, v in extra]:
                out[key] = value
        elif kind_of == "num":
            try:
                out[key] = min(extra[1], max(extra[0], int(value)))
            except (TypeError, ValueError):
                pass
        else:
            out[key] = str(value or "")[:extra]
    return out
