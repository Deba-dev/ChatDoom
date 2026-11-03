"""Addresses of the CHATDOOM services. Streamers never type these: they are built into the app.
If you host your own copy of the cloud or the YouTube bot, change them here before building the installer."""
CLOUD_URL = "https://cloud.zunimilabs.online"                           # Discord roles, payment alerts (Cloudflare Worker, own domain)
YT_BOT_URL = CLOUD_URL                                                  # the YouTube moderator bot now runs on the same Worker (/v1)
OLD_YT_BOT_URLS = ("https://chatvoice-q31b.onrender.com",)               # saved by older versions; moved to YT_BOT_URL on start
OLD_CLOUD_URLS = ("https://chatvoice-cloud.debarshiparasar7.workers.dev", "https://zunimilabs.online")  # earlier Worker addresses; moved on start
YT_BOT_HANDLE = "@ChatVoice-V1"                                         # shown in the "add the bot" instructions
YT_BOT_TITLE = "CHATDOOM Moderator"
