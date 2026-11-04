import datetime
import os
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase, QIcon, QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from app.settings import data_dir
from app.version import PRODUCT_NAME, VERSION


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
    """The installed app has no console, so problems go to a file that can be read later."""
    try:
        with open(os.path.join(data_dir(), "crash.log"), "a", encoding="utf-8") as f:
            f.write("\n--- %s  v%s  %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), VERSION, kind))
            f.write("".join(traceback.format_exception(exc, value, tb)))
    except OSError:
        pass


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
    os._exit(1 if bad else 0)


def main():
    sys.excepthook = lambda exc, value, tb: log_crash("error", exc, value, tb)
    lower_priority()
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
    win.show()
    if "--selftest" in sys.argv:
        QTimer.singleShot(2500, lambda: selftest(win))
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_crash("startup", *sys.exc_info())
        if "--selftest" in sys.argv:
            os._exit(1)
        try:
            QMessageBox.critical(None, PRODUCT_NAME, "CHATDOOM could not start. Please reinstall it from zunimilabs.online/chatdoom.\n\n"
                                                     "Details: " + os.path.join(data_dir(), "crash.log"))
        except Exception:
            pass
        sys.exit(1)
