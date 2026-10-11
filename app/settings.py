"""Settings stored as JSON in %APPDATA%/ChatVoice."""
import json
import os

from .config import CLOUD_URL, YT_BOT_HANDLE, YT_BOT_TITLE, YT_BOT_URL
from .secure import protect, unprotect

SECRET_KEYS = ("cloud_token", "g_client_secret", "ov_external_url", "yt_bot_token",
               "platform_youtube_session", "platform_twitch_session")   # stored encrypted on Windows


def data_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    d = os.path.join(base, "ChatVoice")
    os.makedirs(d, exist_ok=True)
    return d


DEFAULTS = {
    "youtube": "", "twitch": "", "kick": "", "kick_room": "",
    "platform_youtube_session": "", "platform_twitch_session": "",
    "platform_youtube_name": "", "platform_twitch_name": "",
    "engine": "neural", "hi_voice": "hi-IN-SwaraNeural", "en_voice": "hi-IN-MadhurNeural",
    "per_viewer": False, "rate": 0, "volume": 100, "read_name": True, "muted": False,
    "skip_links": True, "skip_cmds": True, "ignore_bots": True, "mods_only": False,
    "read_super": True, "read_mode": "all", "translate_chat": False, "max_len": 150,
    "theme": "Neon Violet", "lite_mode": False,
    "inv_youtube": "", "inv_twitch": "", "inv_kick": "", "inv_role_youtube": "", "inv_role_twitch": "", "inv_role_kick": "",
    "cloud_url": CLOUD_URL, "cloud_token": "", "guild_id": "", "guild_name": "", "webhook_url": "",
    "announce_auto": False, "announce_title": "🔴 LIVE NOW", "announce_text": "I'm live! Come hang out", "post_super": False,
    "discord_announced_videos": [],
    "pay_gateway": "razorpay", "tip_link": "", "ov_port": 8765, "ov_seconds": 8, "ov_show_message": True, "ov_sound": False, "ov_chat_seconds": 20,
    "ov_alert_style": "neon", "ov_chat_style": "glass", "ov_sound_file": "",
    "ov_alert_tips": True, "ov_alert_superchats": True, "ov_alert_memberships": True,
    "ov_alert_youtube_subscribers": True, "ov_alert_follows": True, "ov_alert_subscriptions": True, "ov_alert_raids": True,
    "yt_subscriber_cursor": 0, "yt_subscriber_seen": [],
    "ov_external_url": "",
    "yt_bot_url": YT_BOT_URL, "yt_bot_token": "", "yt_channel_id": "", "yt_channel_title": "", "yt_bot_handle": YT_BOT_HANDLE,
    "yt_bot_title": YT_BOT_TITLE, "yt_used": 0, "yt_used_day": "", "yt_limit": 60, "yt_mod_on": True,
    "music_folder": "", "music_volume": 40, "music_shuffle": True, "music_duck": True, "music_duck_pct": 30, "music_autoplay": False,
    "update_repo": "Deba-dev/ChatDoom", "auto_update_check": True, "update_last": 0, "tips_on": False, "tip_min": 20, "tip_cursor": None, "g_client_id": "", "g_client_secret": "",
    "mod_del_blocked": True, "mod_del_links": True, "mod_del_spam": False, "mod_dry_run": True, "mod_budget": 60,
    "mod_timeout_after": 3, "mod_timeout_secs": 300, "yt_actions_date": "", "yt_actions_count": 0,
    "role_verified": "", "role_regular": "", "role_supporter": "", "regular_msgs": 50, "dedupe_secs": 20, "user_cooldown": 4, "queue_max": 6,
    "chat_font": "", "chat_size": 13, "chat_weight": 400, "chat_color": "#f4f4f8",
    "chat_line": 10, "chat_track": 0, "chat_opacity": 100, "chat_transform": "normal", "chat_italic": False, "chat_align": "left",
}


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "settings.json")
        self.data = dict(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            for k in SECRET_KEYS:
                if k in loaded:
                    loaded[k] = unprotect(loaded[k])
            self.data.update(loaded)
            if self.data.get("update_repo", "").strip().casefold() == "deba-dev/chatvoice":
                self.data["update_repo"] = DEFAULTS["update_repo"]
            if str(self.data.get("yt_bot_title", "")).strip().casefold() == "chat voice":
                self.data["yt_bot_title"] = DEFAULTS["yt_bot_title"]
            for k, default in (("cloud_url", CLOUD_URL), ("yt_bot_url", YT_BOT_URL)):      # older settings files saved an empty address
                if not str(self.data.get(k, "")).strip():
                    self.data[k] = default
        except Exception:
            pass

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                out = dict(self.data)
                for k in SECRET_KEYS:
                    out[k] = protect(out.get(k, ""))
                json.dump(out, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
