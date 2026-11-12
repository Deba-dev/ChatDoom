"""YouTube live chat read straight from youtube.com (no login, no API quota): our own reader, so we don't depend on pytchat.

1. Load https://www.youtube.com/live_chat?v=<id> and pull ytInitialData, the web client context and the "Live chat" (all messages) continuation.
2. Poll youtubei/v1/live_chat/get_live_chat with the continuation; every answer carries the next one.
3. Turn the chat renderers into the same Message objects the rest of the app uses.
"""
import json
import re
import urllib.request

from .models import Message

PAGE_URL = "https://www.youtube.com/live_chat?v=%s&is_popout=1"
POLL_URL = "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?prettyPrint=false"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept-Language": "en-US,en;q=0.9", "Cookie": "SOCS=CAI"}     # SOCS: skip the EU cookie page
POLL_SECS = 1.5         # YouTube says 10 s for push clients; polling a little faster keeps speech close to live
MEMBER_TYPES = ("liveChatMembershipItemRenderer", "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer",
                "liveChatSponsorshipsGiftRedemptionAnnouncementRenderer")


class ChatUnavailable(Exception):
    """The video has no live chat to read (not live, chat off, private...)."""


# ---------- pure parsers (tested with saved samples) ----------
def _json_after(html, marker):
    at = html.find(marker)
    if at < 0:
        return None
    start = html.find("{", at + len(marker))
    return json.JSONDecoder().raw_decode(html[start:])[0] if start >= 0 else None


def parse_page(html):
    """(client context, first continuation) from the live_chat page, or ChatUnavailable with YouTube's own reason."""
    data = _json_after(html, 'window["ytInitialData"]') or _json_after(html, "var ytInitialData")
    if not data:
        raise ChatUnavailable("YouTube sent a page without chat data")
    contents = data.get("contents") or {}
    if "liveChatRenderer" not in contents:
        message = contents.get("messageRenderer", {}).get("text")
        raise ChatUnavailable(runs_plain(message) or "this video has no live chat")
    chat = contents["liveChatRenderer"]
    token = None
    items = (chat.get("header", {}).get("liveChatHeaderRenderer", {}).get("viewSelector", {})
             .get("sortFilterSubMenuRenderer", {}).get("subMenuItems") or [])
    if len(items) > 1:                                      # [Top chat, Live chat]: Live chat has every message
        token = (items[1].get("continuation") or {}).get("reloadContinuationData", {}).get("continuation")
    if not token:
        token, _ = next_continuation(chat)
    if not token:
        raise ChatUnavailable("the chat has no continuation (the stream may have ended)")
    ctx = re.search(r'"INNERTUBE_CONTEXT":(\{.*?\}),"INNERTUBE_CONTEXT_CLIENT_NAME"', html)
    context = json.loads(ctx.group(1)) if ctx else {"client": {"clientName": "WEB", "clientVersion": "2.20261111.01.00"}}
    return context, token


def next_continuation(chat):
    """(next token, seconds to wait) from a liveChatContinuation / liveChatRenderer."""
    for c in chat.get("continuations") or ():
        for kind in ("invalidationContinuationData", "timedContinuationData", "reloadContinuationData"):
            if kind in c:
                wait = int(c[kind].get("timeoutMs") or 0) / 1000
                return c[kind].get("continuation"), min(max(wait, 1.0), POLL_SECS) if wait else POLL_SECS
    return None, POLL_SECS


def runs_plain(block):
    if not isinstance(block, dict):
        return ""
    if "simpleText" in block:
        return block["simpleText"]
    return "".join(r.get("text", "") for r in block.get("runs") or ())


def runs_parts(block):
    """Message runs in the shape youtube_text() reads: text pieces and {id, txt, url} emoji pieces."""
    parts = []
    for run in (block or {}).get("runs") or ():
        if "text" in run:
            parts.append(run["text"])
        elif "emoji" in run:
            e = run["emoji"]
            thumbs = (e.get("image") or {}).get("thumbnails") or [{}]
            url = thumbs[-1].get("url", "")
            parts.append({"id": e.get("emojiId", ""), "txt": (e.get("shortcuts") or [e.get("emojiId", "")])[0],
                          "url": "https:" + url if url.startswith("//") else url})
    return parts


def _is_mod(renderer):
    for badge in renderer.get("authorBadges") or ():
        icon = (badge.get("liveChatAuthorBadgeRenderer") or {}).get("icon", {}).get("iconType")
        if icon in ("MODERATOR", "OWNER"):
            return True
    return False


def parse_actions(actions, text_of):
    """[(Message, timestamp in microseconds or None)] for the chat items in a batch. text_of: youtube_text, to keep emoji handling in one place."""
    out = []
    for action in actions or ():
        item = (action.get("addChatItemAction") or {}).get("item") or {}
        for kind, r in item.items():
            m = _to_message(kind, r, text_of)
            if m is not None:
                ts = r.get("timestampUsec")
                out.append((m, int(ts) if str(ts or "").isdigit() else None))
    return out


def _to_message(kind, r, text_of):
    words = lambda block: text_of(_Parts(runs_parts(block), runs_plain(block)))
    if kind == "liveChatTextMessageRenderer":
        text, emotes = words(r.get("message"))
        return Message("youtube", runs_plain(r.get("authorName")), text, "chat", "", _is_mod(r),
                       r.get("authorExternalChannelId", ""), False, r.get("id", ""), emotes=emotes)
    if kind in ("liveChatPaidMessageRenderer", "liveChatPaidStickerRenderer"):
        text, emotes = words(r.get("message"))
        return Message("youtube", runs_plain(r.get("authorName")), text, "super", runs_plain(r.get("purchaseAmountText")),
                       _is_mod(r), r.get("authorExternalChannelId", ""), False, r.get("id", ""), emotes=emotes)
    if kind in MEMBER_TYPES:
        head = (r.get("header") or {}).get("liveChatSponsorshipsHeaderRenderer") or {}
        name = runs_plain(r.get("authorName")) or runs_plain(head.get("authorName"))
        text, emotes = words(r.get("message"))
        if not text and head:
            text = runs_plain(head.get("primaryText"))             # "Gifted 5 memberships"
        return Message("youtube", name, text or "became a channel member", "member", "", _is_mod(r) or _is_mod(head),
                       r.get("authorExternalChannelId", ""), False, r.get("id", ""), emotes=emotes)
    if kind == "giftMessageViewModel":                            # Jewels gifts: "sent Star"
        gift = re.sub(r"^sent\s+", "", (r.get("text") or {}).get("content", "")).strip()
        name = ((r.get("authorName") or {}).get("content") or "").strip()
        return Message("youtube", name, "", "super", gift, False, "", False, r.get("id", "")) if name and gift else None
    return None


class _Parts:
    """Looks like a pytchat item to youtube_text()."""

    def __init__(self, parts, plain):
        self.messageEx, self.message = parts, plain


# ---------- network ----------
class InnerTubeChat:
    label = "A"

    def __init__(self, video_id, timeout=10):
        self.video_id, self.timeout = video_id, timeout
        self.context = self.token = None
        self.wait = POLL_SECS

    def _get(self, url, body=None):
        headers = dict(HEADERS)
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode()
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read().decode("utf-8", "replace")

    def open(self):
        self.context, self.token = parse_page(self._get(PAGE_URL % self.video_id))

    def poll(self):
        """The next batch of raw actions. Raises when YouTube stops giving a continuation (stream over or chat closed)."""
        data = json.loads(self._get(POLL_URL, {"context": self.context, "continuation": self.token}))
        chat = (data.get("continuationContents") or {}).get("liveChatContinuation")
        if not chat:
            raise ChatUnavailable("YouTube stopped sending chat (the stream may have ended)")
        token, self.wait = next_continuation(chat)
        if not token:
            raise ChatUnavailable("the chat has no continuation (the stream may have ended)")
        self.token = token
        return chat.get("actions") or []
