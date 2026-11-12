"""Settings stored as JSON in %APPDATA%/ChatVoice."""
import json
import os
import tempfile
import threading

from .config import CLOUD_URL, OLD_CLOUD_URLS, OLD_YT_BOT_HANDLES, OLD_YT_BOT_URLS, YT_BOT_HANDLE, YT_BOT_TITLE, YT_BOT_URL
from .secure import protect, unprotect

SECRET_KEYS = ("cloud_token", "g_client_secret", "ov_external_url", "yt_bot_token",
               "platform_youtube_session", "platform_twitch_session", "platform_kick_session")   # stored encrypted on Windows


def data_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    d = os.path.join(base, "ChatVoice")
    os.makedirs(d, exist_ok=True)
    return d


DEFAULTS = {
    "youtube": "", "twitch": "", "kick": "", "kick_room": "",
    "extra_streams": [],                 # added streams: [{"id", "platform", "target", "room", "label"}]
    "commands_on": True, "memes_on": True, "commands": [], "memes": [], "meme_gap": 5, "meme_seconds": 6,
    "points_on": True, "points_name": "coins", "points_per_msg": 5, "points_msg_cooldown": 60, "points_bonus": 10,
    "points_bonus_minutes": 10, "gamble_on": True, "gamble_min": 10, "gamble_cooldown": 60,
    "poll_numbers": True, "giveaway_keyword": "join", "giveaway_cost": 0, "counters": [],
    "welcome_on": False, "welcome_mode": "ever", "welcome_text": "Welcome {user}! Thanks for stopping by.", "welcome_speak": True,
    "welcome_reply": False, "timers_on": True, "timers": [], "sr_on": True, "sr_max": 10, "sr_per_viewer": 1,
    "summary_post": False, "hk_skip": "Ctrl+Alt+S", "hk_mute": "Ctrl+Alt+M", "hk_tts": "Ctrl+Alt+T", "hk_counter": "", "hk_music": "",
    "background": "aurora", "toasts": True,
    "platform_youtube_session": "", "platform_twitch_session": "", "platform_kick_session": "",
    "platform_youtube_name": "", "platform_twitch_name": "", "platform_kick_name": "",
    "engine": "neural", "hi_voice": "hi-IN-SwaraNeural", "en_voice": "hi-IN-MadhurNeural",
    "per_viewer": False, "rate": 0, "volume": 100, "read_name": True, "muted": False,
    "skip_links": True, "skip_cmds": True, "ignore_bots": True, "mods_only": False, "blocked_name_action": "anonymous",
    "raid_on": True, "raid_new_chatters": 15, "raid_cooldown_min": 3, "raid_mode": "paid", "raid_discord": False, "hk_safe": "Ctrl+Alt+H",
    "memory_cards": "regulars",
    "read_super": True, "read_mode": "all", "translate_chat": False, "max_len": 150,
    "theme": "Toxic Neon", "lite_mode": False, "theme_custom": {"a1": "#7c3aed", "a2": "#c026d3", "bg": "#05031a"},
    "bg_image": "builtin:nebula", "bg_dim": 55, "yt_bot_posts": True,
    "inv_youtube": "", "inv_twitch": "", "inv_kick": "", "inv_role_youtube": "", "inv_role_twitch": "", "inv_role_kick": "",
    "cloud_url": CLOUD_URL, "cloud_token": "", "guild_id": "", "guild_name": "", "webhook_url": "",
    "announce_auto": False, "announce_title": "🔴 LIVE NOW", "announce_text": "I'm live! Come hang out", "post_super": False,
    "discord_announced_videos": [],
    "pay_gateway": "razorpay", "tip_link": "", "ov_port": 8765, "ov_seconds": 8, "ov_show_message": True, "ov_sound": False, "ov_chat_seconds": 20,
    "ov_alert_style": "neon", "ov_chat_style": "glass", "ov_sound_file": "", "ov_alert_design": {}, "ov_alert_custom": {}, "ov_tip_tiers": [], "ov_designs": {}, "ov_my_styles": {},
    "ui_scale": 100, "show_stats": True, "autostart": False, "start_hidden": False, "start_page": 0, "last_page": 0, "auto_connect": False, "start_muted": False,
    "close_to_tray": True, "esc_to_tray": True, "esc_ask": True, "tray_hint_shown": False, "window_mode": "windowed", "window_geometry": "", "always_on_top": False, "confirm_quit": False, "toast_seconds": 4, "flash_paid": True,
    "levels_on": True, "level_base": 100, "level_xp_msg": 10, "level_xp_bonus": 20, "level_announce": True, "level_text": "{user} reached level {level}!",
    "shop_on": False, "shop_items": [], "say_on": False, "say_cost": 100, "say_cooldown": 30, "queue_limit": 50,
    "goals": [], "goals_overlay": True, "latest_overlay": False,
    "ov_alert_tips": True, "ov_alert_superchats": True, "ov_alert_memberships": True,
    "ov_alert_youtube_subscribers": True, "ov_alert_follows": True, "ov_alert_subscriptions": True, "ov_alert_raids": True,
    "yt_subscriber_cursor": 0, "yt_subscriber_seen": [],
    "ov_external_url": "",
    "yt_bot_url": YT_BOT_URL, "yt_bot_token": "", "yt_channel_id": "", "yt_channel_title": "", "yt_bot_handle": YT_BOT_HANDLE,
    "yt_bot_title": YT_BOT_TITLE, "yt_used": 0, "yt_used_day": "", "yt_limit": 60, "yt_mod_on": True,
    "music_folder": "", "music_volume": 40, "music_shuffle": True, "music_duck": True, "music_duck_pct": 30, "music_autoplay": False,
    "update_repo": "Deba-dev/ChatDoom", "auto_update_check": True, "update_last": 0, "update_pending": "", "tips_on": False, "tip_min": 20, "tip_cursor": None, "g_client_id": "", "g_client_secret": "",
    "mod_del_blocked": True, "mod_del_links": True, "mod_del_spam": False, "mod_dry_run": True, "mod_budget": 60, "mod_explain": True,
    "mod_timeout_after": 3, "mod_timeout_secs": 300, "yt_actions_date": "", "yt_actions_count": 0,
    "role_verified": "", "role_regular": "", "role_supporter": "", "regular_msgs": 50, "dedupe_secs": 20, "user_cooldown": 4, "queue_max": 6, "detailed_logs": False, "bot_names": [],
    "chat_font": "", "chat_size": 13, "chat_weight": 400, "chat_color": "#f4f4f8",
    "chat_line": 10, "chat_track": 0, "chat_opacity": 100, "chat_transform": "normal", "chat_italic": False, "chat_align": "left",
    "pitch": 0, "voice_paid": "", "voice_member": "", "voice_mod": "", "voice_alerts": "", "voice_youtube": "", "voice_twitch": "", "voice_kick": "",
    "voice_pool": [], "viewer_voices": {}, "voice_match_language": False, "voice_device": "", "win_voice": "",
    "say_format": "{name}: {message}", "say_paid_format": "{name} sent {amount}. {message}", "say_emoji": "read", "say_squeeze": True,
    "say_clean_names": False, "say_gap_ms": 150,
    "translate_langs": ["ru", "ko", "zh", "ja"], "translate_others": False, "translate_target": "en", "translate_speak": True, "translate_show": True,
    "chat_show_time": False, "chat_highlights": [], "chat_mark_new": True, "chat_hide_skipped": False, "chat_muted": [],
    "auto_detect_streams": True, "auto_connect_live": True, "yt_stream_formats": {}, "youtube_auto_id": "",
    "platform_twitch_login": "", "platform_kick_login": "",
    "ov_sound_volume": 80, "ov_type_sounds": {},
}


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "settings.json")
        self.data = dict(DEFAULTS)
        self._lock = threading.Lock()
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            for k in SECRET_KEYS:
                if k in loaded:
                    loaded[k] = unprotect(loaded[k])
            self.data.update(loaded)
            if self.data.get("theme") == "Neon Violet" and not self.data.get("theme_neon_seen"):
                self.data["theme"] = "Toxic Neon"       # the old default moves to the new look once; it can be picked again
            self.data["theme_neon_seen"] = True
            if self.data.get("update_repo", "").strip().casefold() == "deba-dev/chatvoice":
                self.data["update_repo"] = DEFAULTS["update_repo"]
            if str(self.data.get("yt_bot_title", "")).strip().casefold() in ("chat voice", "chatdoom moderator"):
                self.data["yt_bot_title"] = DEFAULTS["yt_bot_title"]
            if str(self.data.get("yt_bot_handle", "")).strip().casefold() in OLD_YT_BOT_HANDLES:    # the bot's channel was renamed
                self.data["yt_bot_handle"] = DEFAULTS["yt_bot_handle"]
            for k, default in (("cloud_url", CLOUD_URL), ("yt_bot_url", YT_BOT_URL)):      # older settings files saved an empty address
                if not str(self.data.get(k, "")).strip():
                    self.data[k] = default
            if str(self.data.get("yt_bot_url", "")).strip().rstrip("/") in OLD_YT_BOT_URLS:     # the bot moved off Render
                self.data["yt_bot_url"] = YT_BOT_URL
            for k, default in (("cloud_url", CLOUD_URL), ("yt_bot_url", YT_BOT_URL)):      # the Worker moved to its own domain
                if str(self.data.get(k, "")).strip().rstrip("/") in OLD_CLOUD_URLS:
                    self.data[k] = default
        except Exception:
            pass

    def update(self, values):
        """Saves many settings at once."""
        if values:
            last = list(values)[-1]
            self.data.update(values)
            self.set(last, values[last])

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        tmp = None
        try:
            with self._lock:        # written beside the old file, then swapped in: a closing app can never leave half a file
                out = dict(self.data)
                for k in SECRET_KEYS:
                    out[k] = protect(out.get(k, ""))
                fd, tmp = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=os.path.dirname(self.path) or ".")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(out, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.path)
                tmp = None
        except Exception:
            pass
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
