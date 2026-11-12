"""Global hotkeys (work while a game is focused) through Windows RegisterHotKey. Other systems simply get none."""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
ACTIONS = (("hk_skip", "Skip the message being read"), ("hk_mute", "Mute / unmute the voice"),
           ("hk_tts", "Read all chat / only !tts messages"),
           ("hk_counter", "Add 1 to your first counter"), ("hk_music", "Play / pause music"))
NAMED = {Qt.Key_Space: 0x20, Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22, Qt.Key_End: 0x23, Qt.Key_Home: 0x24,
         Qt.Key_Left: 0x25, Qt.Key_Up: 0x26, Qt.Key_Right: 0x27, Qt.Key_Down: 0x28, Qt.Key_Insert: 0x2D,
         Qt.Key_Delete: 0x2E, Qt.Key_Pause: 0x13}


def parse(text):
    """'Ctrl+Alt+S' -> (modifiers, virtual key) for RegisterHotKey, or None if it cannot be a safe global hotkey."""
    seq = QKeySequence(text or "")
    if seq.isEmpty():
        return None
    combo = seq[0]
    key, mods = Qt.Key(combo.key()), combo.keyboardModifiers()
    flags = MOD_NOREPEAT
    for qt_mod, flag in ((Qt.ControlModifier, MOD_CONTROL), (Qt.AltModifier, MOD_ALT), (Qt.ShiftModifier, MOD_SHIFT), (Qt.MetaModifier, MOD_WIN)):
        if mods & qt_mod:
            flags |= flag
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        vk = int(key)                                # same codes as ASCII
    elif Qt.Key_F1 <= key <= Qt.Key_F24:
        vk = 0x70 + int(key) - int(Qt.Key_F1)
    else:
        vk = NAMED.get(key)
    if vk is None:
        return None
    if flags == MOD_NOREPEAT and not 0x70 <= vk <= 0x87:   # a plain letter alone would break typing everywhere
        return None
    return flags, vk


class Hotkeys:
    def __init__(self):
        self.ids = {}          # hotkey id -> settings key of the action
        self.hwnd = 0

    def apply(self, hwnd, settings):
        """Register the hotkeys saved in settings. Returns a list of problems to show (empty when all worked)."""
        self.clear()
        if sys.platform != "win32":
            return ["Global hotkeys are only available on Windows."]
        import ctypes
        user32 = ctypes.windll.user32
        self.hwnd, problems = int(hwnd), []
        for n, (key, label) in enumerate(ACTIONS, start=1):
            text = (settings.get(key) or "").strip()
            if not text:
                continue
            parsed = parse(text)
            if parsed is None:
                problems.append("%s: use a modifier like Ctrl+Alt with a letter, number or F-key" % text)
                continue
            if user32.RegisterHotKey(self.hwnd, n, parsed[0], parsed[1]):
                self.ids[n] = key
            else:
                problems.append("%s is already used by another app" % text)
        return problems

    def clear(self):
        if sys.platform == "win32" and self.ids:
            import ctypes
            for n in self.ids:
                ctypes.windll.user32.UnregisterHotKey(self.hwnd, n)
        self.ids = {}

    def match(self, event_type, message):
        """The action for a native window message, if it is one of our hotkeys."""
        if sys.platform != "win32" or event_type != b"windows_generic_MSG" or not self.ids:
            return None
        import ctypes.wintypes
        msg = ctypes.wintypes.MSG.from_address(int(message))
        return self.ids.get(int(msg.wParam)) if msg.message == WM_HOTKEY else None
