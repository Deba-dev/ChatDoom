"""Payments page: the streamer's ZunimiLabs UPI tip page (paid through Cashfree Easy Split) and how tips are read aloud.

The tip page and its QR code live on the cloud (cloud/src/tips.js). Viewers pay by UPI, Cashfree settles the streamer's
share to their own bank account or UPI ID, and each paid tip arrives through the same /api/events feed as before.
"""
import urllib.parse
import urllib.request

from PySide6.QtCore import QByteArray, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QSpinBox

from . import logs
from .discord import run_bg
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import SubPage, bind_switch, field_row, hrow, option_switch_row, section_card


def describe_page(page):
    """One line on where the tip page stands."""
    if not page:
        return "Not set up yet. Fill in the form below."
    status = page.get("status")
    if status == "ACTIVE":
        text = "Live: viewers can tip you." if page.get("enabled") else "Paused: your page is not taking tips."
    elif status == "BLOCKED":
        why = page.get("remarks")
        text = "Cashfree could not verify your account" + (": " + why if why else "") + ". Check the details below and save again."
    else:
        text = "Cashfree is checking your account (usually within a day). Your page opens once it is verified."
    return text + "  Paid to: " + (page.get("payout") or "-")


def describe_terms(t):
    if not t:
        return ""
    fee = (" and Cashfree's fee is %s%%" % t["gatewayFeePct"]) if t.get("gatewayFeePct") else ""
    test = "  TEST MODE: no real money moves yet." if t.get("sandbox") else ""
    return "Each tip: you get %s%%, ZunimiLabs keeps %s%%%s. Viewers pay by UPI; tips start at ₹%s.%s" % (
        t.get("streamerSharePct"), t.get("commissionPct"), fee, t.get("minTip"), test)


class PaymentsPage(SubPage):
    def __init__(self, settings, cloud, bridge, poller):
        super().__init__()
        self.s, self.cloud, self.bridge, self.poller = settings, cloud, bridge, poller
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]
        self.tip = {}
        self._build_upi_tab(self.add_tab("UPI tip page"))

        lay = self.add_tab("Read aloud")
        c, cl = section_card(
            "Reading tips aloud",
            "When a viewer tips on your page, CHATDOOM reads their name, amount and message and shows the OBS alert.",
        )
        self.tips_switch = bind_switch(self.s, "tips_on", accent)
        self.tips_switch.toggled.connect(lambda _: self.poller.apply())
        cl.addWidget(option_switch_row(
            "Listen for tips and read them aloud",
            "Turn this on while you stream.",
            self.tips_switch,
        ))
        self.minimum = QSpinBox()
        self.minimum.setRange(0, 100000)
        self.minimum.setPrefix("₹ ")
        self.minimum.setValue(int(self.s.get("tip_min")))
        self.minimum.valueChanged.connect(lambda v: self.s.set("tip_min", v))
        self.status = QLabel("Not listening")
        self.status.setObjectName("sub")
        test = QPushButton("Send a test tip")
        test.clicked.connect(self.test_tip)
        cl.addWidget(field_row(
            "Minimum amount for the message",
            "Read the viewer's message only when the tip is at least this amount (INR).",
            self.minimum,
        ))
        cl.addWidget(hrow(test, self.status))
        note = QLabel("Messages with blocked words are never read; the name and amount still are. "
                      "Tips are also posted to Discord if you enabled that on the Discord page.")
        note.setObjectName("settingNote")
        note.setWordWrap(True)
        cl.addWidget(note)
        lay.addWidget(c)

        lay = self.add_tab("Other tip link")
        c, cl = section_card(
            "Another tipping link",
            "Have a tipping page somewhere else too? Save its link here to copy or open it quickly. "
            "Tips there are not read aloud; only your UPI tip page is.",
        )
        self.tip_link = QLineEdit(self.s.get("tip_link"))
        self.tip_link.setPlaceholderText("https://your-payment-provider.example/your-link")
        save_link = QPushButton("Save link")
        save_link.setObjectName("primary")
        save_link.clicked.connect(self.save_tip_link)
        copy_link = QPushButton("Copy")
        copy_link.clicked.connect(self.copy_tip_link)
        open_link = QPushButton("Open")
        open_link.clicked.connect(self.open_tip_link)
        self.link_status = QLabel("")
        self.link_status.setObjectName("sub")
        cl.addWidget(field_row("Tip link", "Use a public HTTPS link from a payment provider you trust.", self.tip_link))
        cl.addWidget(hrow(save_link, copy_link, open_link, self.link_status))
        lay.addWidget(c)

        self.finish()
        bridge.done.connect(self.on_done)
        poller.status.connect(self.status.setText)
        self.refresh_upi()

    # ---------------- UPI tip page ----------------
    def _build_upi_tab(self, lay):
        intro, il = section_card(
            "Your UPI tip page and QR code",
            "Viewers scan your QR on stream, type their name and message, and pay with any UPI app. CHATDOOM reads it aloud "
            "and shows the alert. Cashfree pays you directly to your bank account or UPI ID, two working days later. You need "
            "no payment gateway account of your own. Complete the Discord page first: tips use the same server connection.",
        )
        self.upi_terms = QLabel("")
        self.upi_terms.setObjectName("settingNote")
        self.upi_terms.setWordWrap(True)
        il.addWidget(self.upi_terms)
        self.upi_state = QLabel("Checking...")
        self.upi_state.setObjectName("sub")
        self.upi_state.setWordWrap(True)
        il.addWidget(self.upi_state)
        self.upi_url = QLineEdit()
        self.upi_url.setReadOnly(True)
        self.upi_url.setPlaceholderText("Your tip page link appears here once it is set up")
        copy_url = QPushButton("Copy link")
        copy_url.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.upi_url.text()))
        open_url = QPushButton("Open")
        open_url.clicked.connect(self.open_upi_page)
        self.upi_link_row = hrow(self.upi_url, copy_url, open_url)
        self.upi_link_row.hide()                  # appears once Cashfree has verified the streamer's account
        il.addWidget(self.upi_link_row)
        self.qr = QSvgWidget()
        self.qr.setFixedSize(180, 180)
        self.qr.hide()
        copy_qr = QPushButton("Copy QR link for OBS")
        copy_qr.setToolTip("In OBS add a Browser source with this address, 400 x 400, to show the QR on stream")
        copy_qr.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.tip.get("qrUrl", "")))
        self.upi_pause = QPushButton("Pause tips")
        self.upi_pause.clicked.connect(self.toggle_upi_pause)
        self.upi_qr_row = hrow(self.qr, copy_qr, self.upi_pause)
        self.upi_qr_row.hide()
        il.addWidget(self.upi_qr_row)
        self.upi_wait = QTimer(self)              # while Cashfree checks the account, ask again every minute
        self.upi_wait.setInterval(60000)
        self.upi_wait.timeout.connect(self.refresh_upi)
        lay.addWidget(intro)

        form, fl = section_card(
            "Set up or change your page",
            "Cashfree checks your account before the first tip (usually within a day). Your PAN and account number go to "
            "Cashfree only; ZunimiLabs does not keep them. To change only the page name, title or smallest tip, leave the "
            "payout fields empty.",
        )
        self.upi_fields = {}

        def field(key, title, note, placeholder="", password=False):
            w = QLineEdit()
            w.setPlaceholderText(placeholder)
            if password:
                w.setEchoMode(QLineEdit.Password)
            self.upi_fields[key] = w
            row = field_row(title, note, w)
            self.upi_rows = getattr(self, "upi_rows", {})
            self.upi_rows[key] = row
            fl.addWidget(row)

        field("slug", "Page name", "Your link becomes cloud.zunimilabs.online/t/<page name>. Letters, numbers and dashes.", "drxshi")
        field("name", "Name viewers see", "Shown at the top of your tip page.", "DRXSHI")
        self.upi_min = QSpinBox()
        self.upi_min.setRange(10, 100000)
        self.upi_min.setPrefix("₹ ")
        self.upi_min.setValue(20)
        fl.addWidget(field_row("Smallest tip", "Tips under this amount are refused on the page.", self.upi_min))
        self.upi_payout = QComboBox()
        self.upi_payout.addItem("UPI ID", "upi")
        self.upi_payout.addItem("Bank account", "bank")
        self.upi_payout.currentIndexChanged.connect(self._payout_changed)
        fl.addWidget(field_row("Get paid to", "Where Cashfree sends your money.", self.upi_payout))
        field("vpa", "UPI ID", "The UPI ID that receives your tips.", "name@okicici")
        field("account", "Account number", "Your bank account number.", "", password=True)
        field("ifsc", "IFSC", "Your branch's IFSC code.", "HDFC0001234")
        field("holder", "Account holder name", "Exactly as your bank has it.")
        field("pan", "PAN", "Cashfree needs it to pay you (KYC).", "ABCDE1234F", password=True)
        field("email", "Email", "Cashfree sends payout notices here.")
        field("phone", "Mobile number", "10-digit Indian mobile number.", "98765 43210")
        self._payout_changed()
        save = QPushButton("Save my tip page")
        save.setObjectName("primary")
        save.clicked.connect(self.save_upi)
        self.upi_save_state = QLabel("")
        self.upi_save_state.setObjectName("sub")
        self.upi_save_state.setWordWrap(True)
        fl.addWidget(hrow(save, self.upi_save_state))
        lay.addWidget(form)

    def _payout_changed(self):
        upi = self.upi_payout.currentData() == "upi"
        for key, show in (("vpa", upi), ("account", not upi), ("ifsc", not upi)):
            self.upi_rows[key].setVisible(show)

    def refresh_upi(self):
        run_bg(self.bridge, "upi:get", lambda: self.cloud.call("GET", "/api/tips"))

    def upi_body(self):
        """What Save sends. Payout details only when typed (or on the first setup), so a rename keeps the account."""
        f = {k: w.text().strip() for k, w in self.upi_fields.items()}
        body = {"slug": f["slug"], "name": f["name"], "minAmount": self.upi_min.value()}
        if not self.tip or any(f[k] for k in ("vpa", "account", "pan")):
            body.update(holder=f["holder"], pan=f["pan"], email=f["email"], phone=f["phone"])
            if self.upi_payout.currentData() == "upi":
                body["vpa"] = f["vpa"]
            else:
                body.update(account=f["account"], ifsc=f["ifsc"])
        return body

    def save_upi(self):
        body = self.upi_body()
        self.upi_save_state.setText("Saving...")
        run_bg(self.bridge, "upi:save", lambda: self.cloud.call("POST", "/api/tips/setup", body))

    def toggle_upi_pause(self):
        if self.tip:
            enabled = not self.tip.get("enabled")
            run_bg(self.bridge, "upi:pause", lambda: self.cloud.call("PUT", "/api/tips", {"enabled": enabled}))

    def open_upi_page(self):
        if self.upi_url.text():
            QDesktopServices.openUrl(QUrl(self.upi_url.text()))

    def _show_upi(self, res):
        if res.get("terms"):
            self.upi_terms.setText(describe_terms(res["terms"]))
        page = res.get("page")
        was_waiting = self.tip.get("status") not in (None, "ACTIVE")
        self.tip = page or {}
        self.upi_state.setText(describe_page(page))
        verified = bool(page) and page.get("status") == "ACTIVE"
        self.upi_link_row.setVisible(verified)    # link and QR only once the account is verified
        self.upi_qr_row.setVisible(verified)
        if page and page.get("status") not in ("ACTIVE", "BLOCKED"):
            self.upi_wait.start()
        else:
            self.upi_wait.stop()
        if not page:
            return
        if verified and was_waiting:
            self.upi_state.setText("Verified! Your tip link and QR code are ready below.  " + describe_page(page))
            logs.get("tips").info("Tip page %s verified by Cashfree", page.get("slug"))
        self.upi_url.setText(page["url"] if verified else "")
        if not self.upi_fields["slug"].text():
            self.upi_fields["slug"].setText(page["slug"])
            self.upi_fields["name"].setText(page["name"])
            self.upi_min.setValue(int(page["minAmount"]))
        self.upi_pause.setText("Pause tips" if page.get("enabled") else "Resume tips")
        url = page.get("qrUrl")
        if url and verified:
            def fetch():
                with urllib.request.urlopen(url, timeout=15) as r:
                    return {"svg": r.read().decode("utf-8")}
            run_bg(self.bridge, "upi:qr", fetch)

    # ---------------- reading aloud, other link ----------------
    def test_tip(self):
        self.poller.tip.emit({"name": "Rahul", "message": "Great stream bhai, keep it up!", "value": 100.0,
                              "currency": "INR", "display": "₹100"})

    def save_tip_link(self):
        raw = self.tip_link.text().strip()
        try:
            parsed = urllib.parse.urlsplit(raw)
        except ValueError:
            self.link_status.setText("Enter a valid HTTPS tip link")
            return False
        if parsed.scheme != "https" or not parsed.netloc:
            self.link_status.setText("Enter a valid HTTPS tip link")
            return False
        self.s.set("tip_link", raw)
        self.link_status.setText("Tip link saved")
        return True

    def copy_tip_link(self):
        if self.save_tip_link():
            QGuiApplication.clipboard().setText(self.s.get("tip_link"))

    def open_tip_link(self):
        if self.save_tip_link():
            QDesktopServices.openUrl(QUrl(self.s.get("tip_link")))

    def on_done(self, tag, res):
        if not tag.startswith("upi:"):
            return
        if tag == "upi:qr":
            if res.get("svg"):
                self.qr.load(QByteArray(res["svg"].encode("utf-8")))
                self.qr.show()
            return
        if res.get("error"):
            (self.upi_save_state if tag == "upi:save" else self.upi_state).setText(res["error"])
            return
        if tag == "upi:save":
            self.upi_save_state.setText("Saved.")
            for key in ("vpa", "account", "ifsc", "pan"):      # saved with Cashfree; a later rename must not resend them
                self.upi_fields[key].clear()
        self._show_upi(res)
