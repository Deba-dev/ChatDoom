import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase, QIcon, QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from app import logs
from app.settings import Settings
from app.version import PRODUCT_NAME


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def lower_priority():
    """Run below normal priority so games and OBS always win the CPU."""
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
        except Exception:
            pass


def log_crash(kind, exc, value, tb):
    """The installed app has no console, so problems go to logs/crash.log (see app/logs.py)."""
    logs.crash(kind, exc, value, tb)


def selftest(win):
    """Started by the build (CHATDOOM.exe --selftest): a release is stopped here if the app cannot start or a picture is broken."""
    bad = [n for n in ("chatdoom-logo.png", "robot.png", "icon.png") if QImage(resource(os.path.join("assets", n))).isNull()]
    if not os.path.isfile(resource(os.path.join("assets", "icon.ico"))):
        bad.append("icon.ico")
    for i in range(win.stack.count()):
        win.goto(i)
    QApplication.processEvents()
    if bad:
        log_crash("selftest", RuntimeError, RuntimeError("missing or broken: " + ", ".join(bad)), None)
    logs.closing("selftest " + ("failed" if bad else "passed"))
    os._exit(1 if bad else 0)


def main():
    settings = Settings()
    logs.setup(bool(settings.get("detailed_logs")))
    lower_priority()
    scale = int(settings.get("ui_scale") or 100)
    if scale != 100:                              # must be set before the app starts
        os.environ["QT_SCALE_FACTOR"] = str(scale / 100)
    logs.hook_qt()
    app = QApplication(sys.argv)
    app.setApplicationName(PRODUCT_NAME)
    app.setStyle("Fusion")
    fonts = resource(os.path.join("assets", "fonts"))
    if os.path.isdir(fonts):                      # bundled Poppins (supports Hindi, English and the rupee sign)
        for f in os.listdir(fonts):
            if f.lower().endswith(".ttf"):
                QFontDatabase.addApplicationFont(os.path.join(fonts, f))
    icon = resource(os.path.join("assets", "icon.png"))
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    from app.ui import MainWindow          # after the crash log is ready, so a failed import is written down too
    win = MainWindow()
    win.start_window("--autostart" in sys.argv and "--selftest" not in sys.argv)
    if "--selftest" in sys.argv:
        QTimer.singleShot(2500, lambda: selftest(win))
    code = app.exec()
    logs.closing("exit code %d" % code)
    sys.exit(code)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        logs.setup()
        log_crash("startup", *sys.exc_info())
        if "--selftest" in sys.argv:
            os._exit(1)
        try:
            QMessageBox.critical(None, PRODUCT_NAME, "CHATDOOM could not start. Please reinstall it from zunimilabs.online/chatdoom.\n\n"
                                                     "Details: " + logs.path("crash.log"))
        except Exception:
            pass
        sys.exit(1)
