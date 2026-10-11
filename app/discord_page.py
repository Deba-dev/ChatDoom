"""Discord page: add the bot with one click, get roles and invite links made for you.
Everything manual (keys, pasting invites, chat-activity roles) stays tucked away under 'Advanced options'."""
from collections import deque
import urllib.parse

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from .discord import post_live_announcement, post_webhook, run_bg
from .oauth_local import Loopback
from .platforms import youtube_id
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import (FormScrollArea, Switch, bind_switch, copy_row, field_row, hrow, info_box, make_badge,
                     option_switch_row, platform_mark, section_card, set_badge, status_row)

SOURCES = ("youtube", "twitch", "kick")
NICE = {"youtube": "YouTube", "twitch": "Twitch", "kick": "Kick"}


def _style(btn, name):
    btn.setObjectName(name)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


class DiscordPage(FormScrollArea):
    def __init__(self, settings, cloud, bridge, links):
        super().__init__()
        self.s, self.cloud, self.bridge, self.links = settings, cloud, bridge, links
        saved_videos = self.s.get("discord_announced_videos")
        self._announced_videos = list(saved_videos)[-20:] if isinstance(saved_videos, list) else []
        self._pending_auto_videos = set()
        self._paid_event_ids = set()
        self._paid_event_order = deque()
        self.role_names = {}
        self.loop = None
        inner = QWidget()
        inner.setObjectName("page")
        self.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 8, 12, 12)
        lay.setSpacing(14)
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]

        # ---------- 1. connect ----------
        c, cl = section_card("Connect Discord",
                             "Press the button, choose your server on Discord's page and press Authorize. "
                             "CHATDOOM connects by itself: no keys, no links to copy.")
        self.badge = make_badge("\u25cf  Not connected", "pill")
        self.status = QLabel("")
        self.status.setObjectName("sub")
        self.status.setWordWrap(True)
        self.connect_btn = QPushButton("Add CHATDOOM bot to my server")
        self.connect_btn.setObjectName("primary")
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self.connect)
        cl.addWidget(status_row(self.badge, self.status))
        cl.addWidget(hrow(self.connect_btn))
        cl.addWidget(info_box("Manage Roles (to give roles), Create Invite (to make your invite links), View Channels, and "
                              "Manage Server, which Discord requires just to see how often each invite was used. The bot never reads messages.",
                              "What the bot asks Discord for"))
        lay.addWidget(c)

        # ---------- 2. roles + invites made for you ----------
        self.roles_card, cl = section_card("Roles for your viewers",
                                           "Tick the platforms you stream on. CHATDOOM creates a role and a never-expiring invite link for each. "
                                           "Everyone who joins through a link gets that role within about 2 minutes.")
        self.src_switch, self.src_link, self.src_role = {}, {}, {}
        for src in SOURCES:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 4, 0, 4)
            h.setSpacing(12)
            sw = Switch()
            sw.set_accent(accent)
            sw.setChecked(True)
            names = QVBoxLayout()
            names.setSpacing(0)
            nm = QLabel("%s viewers" % NICE[src])
            nm.setObjectName("settingName")
            role = QLabel("Role will be created")
            role.setObjectName("settingNote")
            names.addWidget(nm)
            names.addWidget(role)
            wrap, link = copy_row("", "Invite link appears here")
            h.addWidget(sw)
            h.addWidget(platform_mark(src))
            h.addLayout(names, 1)
            h.addWidget(wrap, 2)
            self.src_switch[src], self.src_link[src], self.src_role[src] = sw, link, role
            cl.addWidget(row)
        self.setup_btn = QPushButton("Create roles and invite links")
        self.setup_btn.setObjectName("primary")
        self.setup_btn.setCursor(Qt.PointingHandCursor)
        self.setup_btn.clicked.connect(self.setup_roles)
        self.check_btn = QPushButton("Check now")
        self.check_btn.setCursor(Qt.PointingHandCursor)
        self.check_btn.clicked.connect(self.check_invites)
        self.istatus = QLabel("")
        self.istatus.setObjectName("sub")
        self.istatus.setWordWrap(True)
        cl.addWidget(hrow(self.setup_btn, self.check_btn))
        cl.addWidget(self.istatus)
        self.tip = info_box("Put each invite link where that audience will see it, for example the YouTube link in your video description "
                            "and pinned comment. You can run this again any time: existing roles and links are reused.", "Where to share the links")
        self.tip.hide()
        cl.addWidget(self.tip)
        lay.addWidget(self.roles_card)

        # ---------- 3. announcements ----------
        c, cl = section_card("Go-live announcements",
                             "Posts once per YouTube live video, including after chat reconnects. The card includes your message and a clickable stream link.")
        self.hook = QLineEdit(self.s.get("webhook_url"))
        self.hook.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.hook.editingFinished.connect(lambda: self.s.set("webhook_url", self.hook.text().strip()))
        self.yt = QLineEdit(self.s.get("youtube"))
        self.yt.setPlaceholderText("https://youtube.com/watch?v=... or a video ID")
        self.yt.editingFinished.connect(lambda: self.s.set("youtube", self.yt.text().strip()))
        self.title = QLineEdit(self.s.get("announce_title"))
        self.title.setPlaceholderText("🔴 LIVE NOW")
        self.title.editingFinished.connect(lambda: self.s.set("announce_title", self.title.text()))
        self.text = QPlainTextEdit(self.s.get("announce_text"))
        self.text.setPlaceholderText("I'm live! Come hang out")
        self.text.setMaximumHeight(95)
        self.text.textChanged.connect(lambda: self.s.set("announce_text", self.text.toPlainText()))
        cl.addWidget(field_row("Webhook URL", "Where live announcements are posted.", self.hook))
        cl.addWidget(field_row("YouTube live link", "Uses the active video URL entered on the Connect page.", self.yt))
        cl.addWidget(field_row("Card title", "Customize the announcement heading.", self.title))
        cl.addWidget(field_row("Custom message", "Supports multiple lines and {url} / {video_id} placeholders.", self.text))
        cl.addWidget(option_switch_row("Announce automatically when YouTube connects",
                                       "Posts the card when the YouTube chat connects.",
                                       bind_switch(self.s, "announce_auto", accent)))
        cl.addWidget(option_switch_row("Post Super Chats / Bits to Discord",
                                       "Sends each paid message immediately; duplicate platform events are ignored.",
                                       bind_switch(self.s, "post_super", accent)))
        now = QPushButton("Announce now")
        now.clicked.connect(self.announce_now)
        self.hstatus = QLabel("")
        self.hstatus.setObjectName("sub")
        cl.addWidget(hrow(now, self.hstatus))
        lay.addWidget(c)

        # ---------- advanced (hidden until asked for) ----------
        self.adv_btn = QPushButton("Show advanced options")
        self.adv_btn.setObjectName("quiet")
        self.adv_btn.setCheckable(True)
        self.adv_btn.setCursor(Qt.PointingHandCursor)
        self.adv_btn.toggled.connect(self._toggle_advanced)
        lay.addWidget(hrow(self.adv_btn))
        self.adv = QWidget()
        al = QVBoxLayout(self.adv)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(14)
        self._build_advanced(al)
        self.adv.hide()
        lay.addWidget(self.adv)
        lay.addStretch(1)

        bridge.done.connect(self.on_done)
        self.refresh_state()
        if self.s.get("cloud_token"):
            self.test()

    # ------------------------------------------------------------------ advanced cards
    def _build_advanced(self, al):
        c, cl = section_card("Connection details",
                             "Only needed if the one-click connection does not work. Paste the server key shown on the Discord approval page.")
        self.url = QLineEdit(self.s.get("cloud_url"))
        self.url.setPlaceholderText("https://chatvoice-cloud.something.workers.dev")
        self.url.editingFinished.connect(lambda: self.s.set("cloud_url", self.url.text().strip()))
        self.key = QLineEdit(self.s.get("cloud_token"))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Server key")
        self.key.editingFinished.connect(lambda: self.s.set("cloud_token", self.key.text().strip()))
        test = QPushButton("Test connection")
        test.setObjectName("primary")
        test.clicked.connect(self.test)
        cl.addWidget(field_row("CHATDOOM cloud address", "Built in. Change it only if you run your own cloud.", self.url))
        cl.addWidget(field_row("Server key", "Filled in automatically by the one-click connection.", self.key))
        cl.addWidget(hrow(test))
        al.addWidget(c)

        c, cl = section_card("Use my own invite links",
                             "Already made invites in Discord? Paste them and pick a role instead of using the automatic setup.")
        self.inv_edits, self.inv_boxes = {}, {}
        for src in SOURCES:
            e = QLineEdit(self.s.get("inv_" + src))
            e.setPlaceholderText("https://discord.gg/...")
            e.editingFinished.connect(lambda k=src, w=e: self.s.set("inv_" + k, w.text().strip()))
            cb = QComboBox()
            cb.addItem("(no role)", "")
            lab = QLabel(NICE[src])
            lab.setObjectName("settingName")
            lab.setMinimumWidth(72)
            self.inv_edits[src], self.inv_boxes[src] = e, cb
            cl.addWidget(hrow(lab, e, cb))
        save_inv = QPushButton("Save invite roles")
        save_inv.setObjectName("primary")
        save_inv.clicked.connect(self.save_invites)
        cl.addWidget(hrow(save_inv))
        al.addWidget(c)

        c, cl = section_card("Chat-activity roles",
                             "Viewers who link their account get Verified. Active chatters become Regulars. Paid messages grant Supporter. "
                             "The CHATDOOM role must sit above these roles in Discord.")
        self.boxes = {}
        for key, label in (("role_verified", "Verified (after linking)"), ("role_regular", "Regular (after N messages)"),
                           ("role_supporter", "Supporter (after a paid message)")):
            cb = QComboBox()
            cb.addItem("(none)", "")
            self.boxes[key] = cb
            lab = QLabel(label)
            lab.setObjectName("settingName")
            lab.setMinimumWidth(210)
            if key == "role_regular":
                self.n = QSpinBox()
                self.n.setRange(1, 100000)
                self.n.setValue(int(self.s.get("regular_msgs")))
                cl.addWidget(hrow(lab, cb, self.n, QLabel("messages")))
            else:
                cl.addWidget(hrow(lab, cb))
        load = QPushButton("Load my roles")
        load.clicked.connect(self.load_roles)
        save = QPushButton("Save rules")
        save.setObjectName("primary")
        save.clicked.connect(self.save_rules)
        self.rstatus = QLabel("")
        self.rstatus.setObjectName("sub")
        cl.addWidget(hrow(load, save, self.rstatus))
        al.addWidget(c)

        c, cl = section_card("Link page for chat-activity roles",
                             "Share this link in Discord and your stream description. Viewers log in with Discord, get a code, "
                             "and type !link CODE in your stream chat.")
        wrap, self.link = copy_row("", "Connect Discord first")
        cl.addWidget(wrap)
        al.addWidget(c)
        self.update_link()

    def _toggle_advanced(self, on):
        self.adv.setVisible(on)
        self.adv_btn.setText("Hide advanced options" if on else "Show advanced options")

    # ------------------------------------------------------------------ state
    @property
    def connected(self):
        return bool(self.s.get("cloud_token"))

    def refresh_state(self):
        if self.connected:
            name = self.s.get("guild_name") or "your Discord server"
            set_badge(self.badge, "\u25cf  Connected", "pillOn")
            self.status.setText(name)
            self.connect_btn.setText("Connect a different server")
            _style(self.connect_btn, "quiet")
        else:
            set_badge(self.badge, "\u25cf  Not connected", "pill")
            self.status.setText("Add the bot to start.")
            self.connect_btn.setText("Add CHATDOOM bot to my server")
            _style(self.connect_btn, "primary")
        self.roles_card.setEnabled(self.connected)
        done = sum(1 for src in SOURCES if self.src_link[src].text())
        self.setup_btn.setText("Update roles and links" if done else "Create roles and invite links")
        self.tip.setVisible(bool(done))

    # ------------------------------------------------------------------ one-click connect
    def connect(self):
        base = self.s.get("cloud_url").strip().rstrip("/")
        if not base:
            self.status.setText("The CHATDOOM cloud address is missing. Open Advanced options.")
            return
        self.loop = Loopback(self.bridge, "dc:connect")
        back = self.loop.start()
        set_badge(self.badge, "\u25cf  Waiting for Discord...", "pillWait")
        self.status.setText("Finish in your browser: choose your server and press Authorize.")
        QDesktopServices.openUrl(QUrl(base + "/setup?return=" + urllib.parse.quote(back, safe="")))

    def _connected_from_browser(self, res):
        if res.get("ok") != "1" or not res.get("token"):
            set_badge(self.badge, "\u25cf  Not connected", "pillBad")
            why = res.get("error") or ""
            self.status.setText("Discord was not connected" + (" (%s)." % why if why else ".") + " Press the button to try again.")
            return
        self.s.set("cloud_token", res["token"])
        self.s.set("guild_name", res.get("guild", ""))
        self.s.set("guild_id", res.get("gid", ""))
        self.key.setText(res["token"])
        self.refresh_state()
        self.update_link()
        self.links.refresh()
        self.test()

    def setup_roles(self):
        sources = [s for s in SOURCES if self.src_switch[s].isChecked()]
        if not sources:
            self.istatus.setText("Tick at least one platform.")
            return
        self.istatus.setText("Creating roles and invite links...")
        self.setup_btn.setEnabled(False)
        run_bg(self.bridge, "dc:setup", lambda: self.cloud.call("POST", "/api/discord/setup", {"sources": sources}))

    def show_rules(self, rules):
        for rule in rules or []:
            src = str(rule.get("label", "")).lower()
            if src in self.src_link:
                self.src_link[src].setText("https://discord.gg/" + rule["code"])
                self.src_role[src].setText("Role: " + self.role_names.get(rule["role"], NICE[src] + " Viewer"))
                self.s.set("inv_" + src, "https://discord.gg/" + rule["code"])
                self.s.set("inv_role_" + src, rule["role"])
                if src in self.inv_edits:
                    self.inv_edits[src].setText("https://discord.gg/" + rule["code"])
        self.refresh_state()

    # ------------------------------------------------------------------ actions (also used by Advanced)
    def _save_conn(self):
        url, key = self.url.text().strip(), self.key.text().strip()
        if url:
            self.s.set("cloud_url", url)
        if key:
            self.s.set("cloud_token", key)

    def test(self):
        self._save_conn()
        self.status.setText("Checking..." if not self.connected else self.status.text())
        run_bg(self.bridge, "ui:test", lambda: self.cloud.call("GET", "/api/config"))

    def load_roles(self):
        self._save_conn()
        self.rstatus.setText("Loading...")
        run_bg(self.bridge, "ui:roles", lambda: self.cloud.call("GET", "/api/roles"))

    def save_rules(self):
        self._save_conn()
        cfg = {"verifiedRole": self.boxes["role_verified"].currentData() or "",
               "regularRole": self.boxes["role_regular"].currentData() or "",
               "supporterRole": self.boxes["role_supporter"].currentData() or "",
               "regularMsgs": self.n.value()}
        for k, b in self.boxes.items():
            self.s.set(k, b.currentData() or "")
        self.s.set("regular_msgs", self.n.value())
        self.rstatus.setText("Saving...")
        run_bg(self.bridge, "ui:save", lambda: self.cloud.call("PUT", "/api/config", cfg))

    def save_invites(self):
        self._save_conn()
        rules = []
        for src, e in self.inv_edits.items():
            code, role = e.text().strip(), self.inv_boxes[src].currentData() or ""
            self.s.set("inv_role_" + src, role)
            if code:
                if not role:
                    self.istatus.setText("Pick a role for the %s invite first (press 'Load my roles' if the list is empty)" % NICE[src])
                    return
                rules.append({"code": code, "role": role, "label": NICE[src]})
        self.istatus.setText("Saving...")
        run_bg(self.bridge, "ui:inv", lambda: self.cloud.call("PUT", "/api/config", {"inviteRules": rules}))

    def check_invites(self):
        self._save_conn()
        self.istatus.setText("Checking...")
        run_bg(self.bridge, "ui:invcheck", lambda: self.cloud.call("POST", "/api/invites/check", {}))

    def announce_now(self, youtube_link=None, automatic_video_id=None):
        self.s.set("webhook_url", self.hook.text().strip())
        link = (youtube_link if youtube_link is not None else self.yt.text()).strip()
        self.yt.setText(link)
        self.s.set("youtube", link)
        self.s.set("announce_title", self.title.text())
        self.s.set("announce_text", self.text.toPlainText())
        self.hstatus.setText("Sending...")
        url, txt, yt, title = (self.s.get("webhook_url"), self.s.get("announce_text"),
                               self.s.get("youtube"), self.s.get("announce_title"))
        tag = "ui:auto|" + automatic_video_id if automatic_video_id else "ui:hook"
        run_bg(self.bridge, tag, lambda: post_live_announcement(url, txt, yt, title))

    def auto_announce(self, platform=None, youtube_link=None):
        if platform and platform != "youtube":
            return
        if not self.s.get("announce_auto"):
            return
        yt = (youtube_link or self.s.get("youtube") or "").strip()
        video_id = youtube_id(yt) if yt else None
        if not video_id:
            self.hstatus.setText("Automatic announcement needs the YouTube live video link or 11-character video ID from Connect.")
            return
        if not self.s.get("webhook_url"):
            self.hstatus.setText("Add a Discord webhook URL to enable automatic announcements.")
            return
        if video_id in self._announced_videos or video_id in self._pending_auto_videos:
            return
        self._pending_auto_videos.add(video_id)
        self.announce_now(yt, automatic_video_id=video_id)

    def post_paid(self, m):
        if self.s.get("post_super") and self.s.get("webhook_url"):
            if m.event_id:
                event_key = "%s:%s" % (m.platform, m.event_id)
                if event_key in self._paid_event_ids:
                    return
                self._paid_event_ids.add(event_key)
                self._paid_event_order.append(event_key)
                if len(self._paid_event_order) > 2000:
                    self._paid_event_ids.discard(self._paid_event_order.popleft())
            where = "" if m.platform == "tip" else " on " + m.platform
            txt = "\U0001F48E **%s** sent **%s**%s%s" % (m.author, m.amount, where, (": " + m.text[:300]) if m.text else "")
            run_bg(self.bridge, "ui:hookpaid", lambda: post_webhook(self.s.get("webhook_url"), txt))

    def update_link(self):
        gid, base = self.s.get("guild_id"), self.s.get("cloud_url").strip().rstrip("/")
        self.link.setText("%s/link/%s" % (base, gid) if gid and base else "")

    def _fill_roles(self, roles):
        self.role_names = {r["id"]: r["name"] for r in roles}
        for src, cb in self.inv_boxes.items():
            saved = self.s.get("inv_role_" + src)
            cb.clear()
            cb.addItem("(no role)", "")
            for r in roles:
                cb.addItem(r["name"], r["id"])
            cb.setCurrentIndex(max(0, cb.findData(saved)))
        for key, cb in self.boxes.items():
            saved = self.s.get(key)
            cb.clear()
            cb.addItem("(none)", "")
            for r in roles:
                cb.addItem(r["name"], r["id"])
            cb.setCurrentIndex(max(0, cb.findData(saved)))
        for src in SOURCES:                                   # show real role names on the simple view
            rid = self.s.get("inv_role_" + src)
            if rid in self.role_names and self.src_link[src].text():
                self.src_role[src].setText("Role: " + self.role_names[rid])

    # ------------------------------------------------------------------ answers
    def on_done(self, tag, res):
        err = res.get("error")
        if tag == "dc:connect":
            return self._connected_from_browser(res)
        if tag == "dc:setup":
            self.setup_btn.setEnabled(True)
            if err:
                self.istatus.setText(err)
                return
            self.role_names.update({x["roleId"]: x["roleName"] for x in res.get("sources", [])})
            self.show_rules([{"label": x["label"], "code": x["invite"].rsplit("/", 1)[-1], "role": x["roleId"]} for x in res.get("sources", [])])
            made = sum(1 for x in res.get("sources", []) if x.get("roleCreated"))
            self.istatus.setText("Done. %d invite link(s) ready%s." % (len(res.get("sources", [])), ", %d new role(s) created" % made if made else ""))
            self.load_roles()
            return
        if not tag.startswith("ui:"):
            return
        if tag == "ui:test":
            if err:
                if self.connected and "bad server key" in err:
                    self.s.set("cloud_token", "")
                    self.key.setText("")
                    self.refresh_state()
                    self.status.setText("The saved connection is no longer valid. Add the bot again.")
                else:
                    self.status.setText(err)
                return
            self.s.set("guild_id", res["guildId"])
            self.s.set("guild_name", res["guildName"])
            cfg = res.get("config", {})
            for k, name in (("role_verified", "verifiedRole"), ("role_regular", "regularRole"), ("role_supporter", "supporterRole")):
                if name in cfg:
                    self.s.set(k, cfg[name])
            self.show_rules(cfg.get("inviteRules", []))
            if cfg.get("regularMsgs"):
                self.n.setValue(int(cfg["regularMsgs"]))
            self.refresh_state()
            self.update_link()
            self.links.refresh()
            self.load_roles()
        elif tag == "ui:roles":
            if err:
                self.rstatus.setText(err)
            else:
                self._fill_roles(res["roles"])
                self.rstatus.setText("%d roles loaded" % len(res["roles"]))
        elif tag == "ui:save":
            self.rstatus.setText(err or "Rules saved")
        elif tag == "ui:inv":
            self.istatus.setText(err or "Saved. CHATDOOM's cloud checks for new members every 2 minutes.")
        elif tag == "ui:invcheck":
            if err or res.get("error"):
                self.istatus.setText(err or res["error"])
                return
            lines = []
            for r in res.get("rules", []):
                lines.append("%s: %s" % (r["label"], "invite found, used %d times so far" % r["uses"] if r.get("found")
                                         else "invite NOT found - create it in Discord or fix the link"))
            lines += res.get("notes", [])
            if res.get("assigned"):
                lines.append("Gave roles to %d new member(s)." % len(res["assigned"]))
            self.istatus.setText("\n".join(lines) or "Nothing new")
        elif tag.startswith("ui:auto|"):
            video_id = tag.partition("|")[2]
            self._pending_auto_videos.discard(video_id)
            err = err or res.get("error")
            if not err:
                if video_id not in self._announced_videos:
                    self._announced_videos.append(video_id)
                    self._announced_videos = self._announced_videos[-20:]
                    self.s.set("discord_announced_videos", self._announced_videos)
            self.hstatus.setText("Announcement failed: " + err if err else "Announcement sent to Discord.")
        elif tag == "ui:hook":
            err = err or res.get("error")
            self.hstatus.setText("Announcement failed: " + err if err else "Announcement sent to Discord.")
