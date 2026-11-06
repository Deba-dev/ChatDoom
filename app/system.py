"""Things that touch Windows or the settings file as a whole: starting with Windows, restarting, and settings backups."""
import json
import os
import re
import subprocess
import sys

from .settings import DEFAULTS, SECRET_KEYS

try:
    import winreg
except ImportError:                                 # not on Windows
    winreg = None

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "CHATDOOM"
# Never copied into a backup or taken from one: sign-ins, private links, and anything that decides which servers the app trusts.
PRIVATE = re.compile(r"token|secret|session|webhook|client|cloud|guild|url|repo|update|channel|^yt_|^inv_|^role_|cursor|seen|announced", re.I)
RESTART_KEYS = ("ui_scale", "ov_port")


def can_autostart():
    return winreg is not None and bool(getattr(sys, "frozen", False))


def autostart_on():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(on):
    """Returns True if Windows now does what was asked. Only the installed app can do this, never a copy run from the code."""
    if not can_autostart():
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if on:
                winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, '"%s" --autostart' % sys.executable)
            else:
                try:
                    winreg.DeleteValue(key, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def restart_command():
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, os.path.abspath(sys.argv[0])]


def restart():
    subprocess.Popen(restart_command(), close_fds=True)


def backupable(key):
    return key in DEFAULTS and key not in SECRET_KEYS and not PRIVATE.search(key)


def write_backup(settings, path):
    data = {k: settings.get(k) for k in DEFAULTS if backupable(k)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"chatdoomBackup": 1, "settings": data}, f, ensure_ascii=False, indent=1)
    return len(data)


def read_backup(settings, path):
    """Returns how many settings were restored, or -1 for a file that is not a backup. Each value must be the right type."""
    try:
        if os.path.getsize(path) > 5000000:
            return -1
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("chatdoomBackup") != 1 or not isinstance(data.get("settings"), dict):
            return -1
    except (OSError, ValueError, AttributeError):
        return -1
    wanted = {}
    for key, value in data["settings"].items():
        default = DEFAULTS.get(key)
        if backupable(key) and (type(value) is type(default) or (isinstance(default, (int, float)) and type(value) in (int, float))):
            wanted[key] = value
    settings.update(wanted)
    return len(wanted)


def reset_settings(settings):
    """Back to how a new install looks. Sign-ins and connected services are kept."""
    settings.update({k: v for k, v in DEFAULTS.items() if backupable(k)})
