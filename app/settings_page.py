"""Settings page: how the app looks, starts, behaves and updates, plus backups and About."""
import datetime
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QFileDialog, QLabel, QPushButton, QSlider, QSpinBox

from . import system
from .settings import data_dir
from .theme import DEFAULT_THEME, THEMES
from .ui_kit import SubPage, bind_switch, field_row, hrow, info_box, option_switch_row, section_card
from .version import CREATOR, PRODUCT_NAME, label
from .visuals import BACKGROUNDS
from .window_modes import MODES

SCALES = (("90%", 90), ("100% (normal)", 100), ("110%", 110), ("125%", 125), ("150%", 150))
LINKS = (("Website", "https://zunimilabs.online/chatdoom/"), ("Guides", "https://zunimilabs.online/guides/"), ("Help", "https://zunimilabs.online/support/"),
         ("Service status", "https://zunimilabs.online/status/"), ("Privacy", "https://zunimilabs.online/chatdoom/privacy/"), ("Terms", "https://zunimilabs.online/chatdoom/terms/"))
RELEASES = "https://github.com/Deba-dev/ChatDoom/releases"


def _button(text, name="quiet"):
    b = QPushButton(text)
    b.setObjectName(name)
    b.setCursor(Qt.PointingHandCursor)
    return b


class SettingsPage(SubPage):
    def __init__(self, settings, host, pages):
        super().__init__()
        self.s, self.host = settings, host
        accent = THEMES.get(self.s.get("theme"), THEMES[DEFAULT_THEME])["a1"]
        sw = lambda key: bind_switch(self.s, key, accent)

        # ---------- appearance ----------
        lay = self.add_tab("Appearance")
        c, cl = section_card("Look", "Themes colour the whole app and follow through to your overlays.")
        self.theme = QComboBox()
        self.theme.addItems(list(THEMES))
        self.theme.setCurrentText(self.s.get("theme") if self.s.get("theme") in THEMES else DEFAULT_THEME)
        self.theme.currentTextChanged.connect(host.apply_theme)
        cl.addWidget(field_row("Theme", "", self.theme))
        self.backdrop = QComboBox()
        for text, value in BACKGROUNDS:
            self.backdrop.addItem(text, value)
        self.backdrop.setCurrentIndex(max(0, self.backdrop.findData(self.s.get("background"))))
        self.backdrop.currentIndexChanged.connect(lambda _: (self.s.set("background", self.backdrop.currentData()), host.canvas.sync()))
        cl.addWidget(field_row("Background", "The aurora moves only while CHATDOOM is the active window.", self.backdrop))
        self.dim = QSlider(Qt.Horizontal)
        self.dim.setRange(20, 85)
        self.dim.setValue(int(self.s.get("bg_dim")))
        self.dim.valueChanged.connect(host.set_background_dim)
        cl.addWidget(field_row("Darken the background picture", "Higher keeps text easier to read.", self.dim))
        customize = _button("Customize colours and pictures")
        customize.clicked.connect(host._open_appearance)
        cl.addWidget(hrow(customize))
        lay.addWidget(c)
        c, cl = section_card("Layout and motion", "")
        lite = sw("lite_mode")
        lite.toggled.connect(host._lite)
        self.lite = lite
        cl.addWidget(option_switch_row("Lite mode", "Turns off fade and hover motion. Use it on slow PCs or while gaming.", lite))
        stats = sw("show_stats")
        stats.toggled.connect(lambda _: host._refresh_stats())
        cl.addWidget(option_switch_row("Show the stat cards", "The three live numbers at the top of each page.", stats))
        self.scale = QComboBox()
        for text, value in SCALES:
            self.scale.addItem(text, value)
        self.scale.setCurrentIndex(max(0, self.scale.findData(self.s.get("ui_scale"))))
        self.scale.currentIndexChanged.connect(lambda _: self._needs_restart("ui_scale", self.scale.currentData()))
        cl.addWidget(field_row("Interface size", "Makes everything larger or smaller. Needs a restart.", self.scale))
        lay.addWidget(c)

        # ---------- startup and window ----------
        lay = self.add_tab("Startup and window")
        c, cl = section_card("When CHATDOOM starts", "")
        self.autostart = sw("autostart")
        self.autostart.setChecked(system.autostart_on())
        self.autostart.setEnabled(system.can_autostart())
        self.autostart.toggled.connect(self._autostart_changed)
        cl.addWidget(option_switch_row("Start with Windows", "Only the installed app can do this." if not system.can_autostart() else "", self.autostart))
        cl.addWidget(option_switch_row("Start hidden in the tray", "When Windows starts it. Needs Keep running in the tray.", sw("start_hidden")))
        self.start_page = QComboBox()
        self.start_page.addItem("The last page I used", -1)
        for index, name in pages:
            self.start_page.addItem(name, index)
        self.start_page.setCurrentIndex(max(0, self.start_page.findData(int(self.s.get("start_page")))))
        self.start_page.currentIndexChanged.connect(lambda _: self.s.set("start_page", self.start_page.currentData()))
        cl.addWidget(field_row("Open on", "", self.start_page))
        cl.addWidget(option_switch_row("Connect my streams", "Connects every stream that has a saved link or channel.", sw("auto_connect")))
        cl.addWidget(option_switch_row("Start with the voice muted", "", sw("start_muted")))
        lay.addWidget(c)
        c, cl = section_card("Window", "")
        self.window_mode = QComboBox()
        for text, value in MODES:
            self.window_mode.addItem(text, value)
        self.window_mode.setCurrentIndex(max(0, self.window_mode.findData(host.modes.mode)))
        self.window_mode.currentIndexChanged.connect(lambda _: host.modes.set_mode(self.window_mode.currentData()))
        host.modes.mode_changed.connect(self._show_window_mode)
        cl.addWidget(field_row("Window mode", "Borderless fills the screen above the taskbar; Fullscreen covers it all. F11 switches fullscreen on and off.", self.window_mode))
        tray = sw("close_to_tray")
        tray.toggled.connect(lambda _: host.sync_tray())
        cl.addWidget(option_switch_row("Keep running in the tray", "Closing the window keeps CHATDOOM reading chat. Use the tray icon to quit.", tray))
        esc = sw("esc_to_tray")
        esc.toggled.connect(lambda _: host.sync_tray())
        cl.addWidget(option_switch_row("Esc hides it to the tray", "Esc first leaves a text box or fullscreen.", esc))
        cl.addWidget(option_switch_row("Ask before Esc hides it", "Hide to tray, Quit or Cancel; Cancel is the default.", sw("esc_ask")))
        top = sw("always_on_top")
        top.toggled.connect(host.set_always_on_top)
        cl.addWidget(option_switch_row("Always on top", "Keeps the window above your other apps.", top))
        cl.addWidget(option_switch_row("Ask before closing while live", "Stops you ending the voice and overlays by accident.", sw("confirm_quit")))
        lay.addWidget(c)

        # ---------- notifications ----------
        lay = self.add_tab("Notifications")
        c, cl = section_card("Pop-up notices", "The small notices at the top right of the app.")
        cl.addWidget(option_switch_row("Show pop-up notices", "New chatters, supporters, purchases and other events.", sw("toasts")))
        self.toast_seconds = QSpinBox()
        self.toast_seconds.setRange(2, 15)
        self.toast_seconds.setSuffix(" s")
        self.toast_seconds.setValue(int(self.s.get("toast_seconds")))
        self.toast_seconds.valueChanged.connect(lambda v: self.s.set("toast_seconds", v))
        cl.addWidget(field_row("Normal time on screen", "", self.toast_seconds))
        cl.addWidget(option_switch_row("Flash the taskbar for supporters", "When the app is in the background and someone pays or joins.", sw("flash_paid")))
        lay.addWidget(c)

        # ---------- updates ----------
        lay = self.add_tab("Updates")
        c, cl = section_card("Updates", "Your settings are kept when CHATDOOM updates.")
        self.version = QLabel(label())
        self.version.setObjectName("pageTitle")
        cl.addWidget(self.version)
        self.update_note = QLabel()
        self.update_note.setObjectName("settingNote")
        cl.addWidget(self.update_note)
        cl.addWidget(option_switch_row("Check for updates by myself", "Checks when the app opens, at most once every 20 hours.", sw("auto_update_check")))
        check, notes = _button("Check for updates", "primary"), _button("See what's new")
        check.clicked.connect(lambda: (host.updater.check(True), self.refresh()))
        notes.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES)))
        cl.addWidget(hrow(check, notes))
        lay.addWidget(c)

        # ---------- data ----------
        lay = self.add_tab("Data and backup")
        c, cl = section_card("Backup", "Saves your designs, commands, timers and settings to a file. Sign-ins, private links and viewer points are never included.")
        save, load = _button("Save a backup", "primary"), _button("Restore a backup")
        save.clicked.connect(self._save_backup)
        load.clicked.connect(self._load_backup)
        cl.addWidget(hrow(save, load))
        self.backup_note = QLabel("")
        self.backup_note.setObjectName("settingNote")
        cl.addWidget(self.backup_note)
        lay.addWidget(c)
        c, cl = section_card("Files and connection", "")
        folder, logs = _button("Open my data folder"), _button("Open the crash log")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(data_dir())))
        logs.clicked.connect(self._open_log)
        cl.addWidget(hrow(folder, logs))
        self.port = QSpinBox()
        self.port.setRange(1024, 65000)
        self.port.setValue(int(self.s.get("ov_port")))
        self.port.valueChanged.connect(lambda v: self._needs_restart("ov_port", v))
        cl.addWidget(field_row("Overlay port", "Change this only if another app uses it. Your OBS addresses change too. Needs a restart.", self.port))
        lay.addWidget(c)
        c, cl = section_card("Start over", "Puts settings and designs back to how a new install looks. Sign-ins, connected services and viewer points stay.")
        self.reset_btn = _button("Reset all settings", "danger")
        self.reset_btn.clicked.connect(self._reset)
        cl.addWidget(hrow(self.reset_btn))
        lay.addWidget(c)

        # ---------- about ----------
        lay = self.add_tab("About")
        c, cl = section_card(PRODUCT_NAME, "Developed and powered by %s." % CREATOR)
        cl.addWidget(QLabel(label()))
        for start in (0, 3):
            buttons = []
            for text, url in LINKS[start:start + 3]:
                b = _button(text)
                b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
                buttons.append(b)
            cl.addWidget(hrow(*buttons))
        lay.addWidget(c)

        self.restart_box = info_box("Some changes need a restart.", "Restart needed")
        self.restart_btn = _button("Restart now", "primary")
        self.restart_btn.clicked.connect(host.restart_app)
        self.restart_row = hrow(self.restart_box, self.restart_btn)
        self.restart_row.hide()
        self.add_header(self.restart_row)
        self.finish()
        self.refresh()

    def refresh(self):
        stamp = float(self.s.get("update_last") or 0)
        when = datetime.datetime.fromtimestamp(stamp).strftime("%d %b %Y, %H:%M") if stamp else "not yet"
        self.update_note.setText("Last checked: %s" % when)

    def _show_window_mode(self, _mode):
        """F11 and the corner buttons change the mode too; the box follows without saving again."""
        self.window_mode.blockSignals(True)
        self.window_mode.setCurrentIndex(max(0, self.window_mode.findData(self.host.modes.mode)))
        self.window_mode.blockSignals(False)

    def _needs_restart(self, key, value):
        self.s.set(key, value)
        self.restart_row.show()

    def _autostart_changed(self, on):
        if not system.set_autostart(on):
            self.autostart.blockSignals(True)
            self.autostart.setChecked(system.autostart_on())
            self.autostart.blockSignals(False)
            self.host.toasts.show("Windows did not allow that change.", "warn")

    def _open_log(self):
        path = os.path.join(data_dir(), "crash.log")
        if os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            self.host.toasts.show("No crashes have been logged.", "good")

    def save_backup(self, path):
        self.backup_note.setText("Saved %d settings." % system.write_backup(self.s, path))

    def load_backup(self, path):
        count = system.read_backup(self.s, path)
        if count < 0:
            self.backup_note.setText("That is not a CHATDOOM backup file.")
            return False
        self.backup_note.setText("Restored %d settings." % count)
        self.restart_row.show()
        return True

    def _save_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save a backup", os.path.expanduser("~/chatdoom-backup.json"), "CHATDOOM backup (*.json)")
        if path:
            self.save_backup(path)

    def _load_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restore a backup", os.path.expanduser("~"), "CHATDOOM backup (*.json)")
        if path:
            self.load_backup(path)

    def _reset(self):
        if self.reset_btn.text() != "Click again to reset":         # a second click confirms, no popup needed
            self.reset_btn.setText("Click again to reset")
            return
        system.reset_settings(self.s)
        self.reset_btn.setText("Reset all settings")
        self.restart_row.show()
