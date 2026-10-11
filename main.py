import os
import sys

from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from app.ui import MainWindow
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


def main():
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
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
