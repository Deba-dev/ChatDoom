from dataclasses import dataclass


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
