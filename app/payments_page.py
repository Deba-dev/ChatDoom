"""Payments page: connect the streamer's Razorpay webhook and choose how payments are read."""
import urllib.parse

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

from .discord import run_bg
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import FormScrollArea, bind_switch, field_row, hrow, option_switch_row, section_card

GATEWAYS = {
    "razorpay": ("Razorpay", "Razorpay webhook secret (you choose it in the Razorpay dashboard)",
                 "Razorpay > Settings > Webhooks > Add: paste this address and the SAME secret, tick only the event payment.captured. "
                 "On your Payment Page add two fields labelled Name and Message."),
    "stripe": ("Stripe", "Stripe signing secret (starts with whsec_)",
               "Stripe Dashboard > Developers > Webhooks > Add endpoint: paste this address, choose the event checkout.session.completed, "
               "then paste the endpoint's signing secret here. On your Payment Link add custom fields labelled Name and Message."),
    "cashfree": ("Cashfree", "Cashfree secret key",
                 "Cashfree Dashboard > Developers > Webhooks: paste this address. The secret is your Payment Gateway secret key. "
                 "Add Name and Message fields to your payment form. (Field names are not confirmed yet - see PAYMENTS-SETUP.txt.)"),
    "generic": ("Any other tool (Zapier, Make, n8n, Google Apps Script...)", "A secret you choose",
                'Send a POST with JSON {"name":"...","message":"...","amount":100,"currency":"INR"} to this address, with the header '
                "X-ChatVoice-Secret set to your secret (or put it in the JSON as \"secret\")."),
}


class PaymentsPage(FormScrollArea):
    def __init__(self, settings, cloud, bridge, poller):
        super().__init__()
        self.s, self.cloud, self.bridge, self.poller = settings, cloud, bridge, poller
        inner = QWidget()
        inner.setObjectName("page")
        self.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 8, 12, 12)
        lay.setSpacing(14)
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]

        c, cl = section_card(
            "Connect your payment page",
            "Viewers pay on a page in your own payment account. Your service tells CHATDOOM, and CHATDOOM reads the name, amount, and message aloud. "
            "Complete the Discord page first—payments use the same server connection.",
        )
        self.cfg = {}
        self.gw = QComboBox()
        for key, (label, _, _) in GATEWAYS.items():
            self.gw.addItem(label, key)
        self.gw.setCurrentIndex(max(0, self.gw.findData(self.s.get("pay_gateway"))))
        self.gw.currentIndexChanged.connect(self._gateway_changed)
        cl.addWidget(field_row("Payment service", "Choose the tool that sends payment webhooks.", self.gw))
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        save = QPushButton("Save secret")
        save.setObjectName("primary")
        save.clicked.connect(self.save_secret)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self.state = QLabel("")
        self.state.setObjectName("sub")
        cl.addWidget(field_row("Webhook secret", "Paste the secret from your payment dashboard.", self.secret))
        cl.addWidget(hrow(save, refresh, self.state))
        self.hook = QLineEdit()
        self.hook.setReadOnly(True)
        self.hook.setPlaceholderText("Webhook address appears here after you save the secret")
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.hook.text()))
        self.how = QLabel()
        self.how.setObjectName("settingNote")
        self.how.setWordWrap(True)
        cl.addWidget(self.how)
        cl.addWidget(hrow(self.hook, copy))
        self._gateway_changed()
        lay.addWidget(c)

        c, cl = section_card(
            "Reading payments aloud",
            "On your payment page, add two fields labelled Name and Message. CHATDOOM finds them by their labels.",
        )
        self.tips_switch = bind_switch(self.s, "tips_on", accent)
        self.tips_switch.toggled.connect(lambda _: self.poller.apply())
        cl.addWidget(option_switch_row(
            "Listen for payments and read them aloud",
            "Turn on webhook listening on this PC.",
            self.tips_switch,
        ))
        self.minimum = QSpinBox()
        self.minimum.setRange(0, 100000)
        self.minimum.setPrefix("₹ ")
        self.minimum.setValue(int(self.s.get("tip_min")))
        self.minimum.valueChanged.connect(lambda v: self.s.set("tip_min", v))
        self.status = QLabel("Not listening")
        self.status.setObjectName("sub")
        test = QPushButton("Send a test payment")
        test.clicked.connect(self.test_tip)
        cl.addWidget(field_row(
            "Minimum amount for the message",
            "Read the viewer's message only when the payment is at least this amount (INR).",
            self.minimum,
        ))
        cl.addWidget(hrow(test, self.status))
        note = QLabel("Messages with blocked words are never read; the name and amount still are. "
                      "Payments are also posted to Discord if you enabled that on the Discord page.")
        note.setObjectName("settingNote")
        note.setWordWrap(True)
        cl.addWidget(note)
        lay.addWidget(c)

        c, cl = section_card(
            "Quick tip link",
            "Paste a payment or tipping page link to share with viewers. This opens your provider's page; it does not process or alert on payments.",
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
        cl.addWidget(field_row("Viewer tip page", "Use a public HTTPS link from a payment provider you trust.", self.tip_link))
        cl.addWidget(hrow(save_link, copy_link, open_link, self.link_status))
        lay.addWidget(c)

        lay.addStretch(1)
        bridge.done.connect(self.on_done)
        poller.status.connect(self.status.setText)

    def _gateway_changed(self):
        key = self.gw.currentData()
        self.s.set("pay_gateway", key)
        self.secret.setPlaceholderText(GATEWAYS[key][1])
        self.how.setText(GATEWAYS[key][2])
        self._show_cfg()

    def _show_cfg(self):
        key = self.gw.currentData()
        self.hook.setText((self.cfg.get("hookUrls") or {}).get(key, ""))
        if self.cfg:
            self.state.setText("Secret saved on server" if self.cfg.get("has%sSecret" % key.capitalize()) else "No secret saved yet")

    def refresh(self):
        self.state.setText("Checking...")
        run_bg(self.bridge, "pay:cfg", lambda: self.cloud.call("GET", "/api/config"))

    def save_secret(self):
        text = self.secret.text().strip()
        if not text:
            self.state.setText("Type the secret first")
            return
        self.state.setText("Saving...")
        field = self.gw.currentData() + "Secret"
        run_bg(self.bridge, "pay:save", lambda: self.cloud.call("PUT", "/api/config", {field: text}))

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
        if not tag.startswith("pay:"):
            return
        if res.get("error"):
            self.state.setText(res["error"])
            return
        self.cfg = res.get("config", {})
        self._show_cfg()
        if tag == "pay:save":
            self.secret.clear()
            self.state.setText("Saved. Now add the address below in your payment service.")
