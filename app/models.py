from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Message:
    platform: str          # "youtube" | "twitch" | "kick" | "test"
    author: str
    text: str
    kind: str = "chat"     # "chat" | "super" | "member"
    amount: str = ""       # e.g. "₹100.00" or "50 bits"
    mod: bool = False      # moderator / owner / broadcaster
    uid: str = ""          # stable platform user id (used for Discord linking)
    bot: bool = False      # provider explicitly identified this account as a bot
    event_id: str = ""     # stable provider event id, used to prevent duplicate paid alerts
    stream: str = ""       # which connected stream it came from: "youtube" for the main card, "extra:3" for an added one
    emotes: dict = field(default_factory=dict)   # picture emotes in the text: {word as written in text: https image address}
    rupees: Optional[float] = None   # a tip's amount in rupees, for alert designs by amount (None: not a rupee tip)


def viewer_key(m):
    """Stable id of a viewer across messages: the platform plus their account id (or name when there is none)."""
    return "%s:%s" % (m.platform, m.uid or (m.author or "").lower())
