"""Logs: everything that goes wrong (and the main things that happen) is written to files the streamer can send us.

Files, all in <data folder>/logs:
  chatdoom.log      day-to-day log: start/stop, connections, cloud errors, voice problems, warnings. Rotates at 1 MB, 4 old copies.
  crash.log         only crashes: Python errors nobody caught, in any thread, with the full traceback.
  native-crash.log  hard crashes inside Qt or Windows code (Python's faulthandler). Normally empty.
Secrets (tokens, keys, passwords) are blanked before anything is written.
"""
import datetime
import faulthandler
import logging
import logging.handlers
import os
import platform
import re
import sys
import threading
import traceback
import zipfile

from .settings import data_dir
from .version import VERSION

LOG = logging.getLogger("chatdoom")
LOG_BYTES = 1024 * 1024
LOG_COPIES = 4
CRASH_LIMIT = 512 * 1024
_SECRET = re.compile(
    r"(?i)((?:access_?token|refresh_?token|token|secret|client_secret|api[_-]?key|password|passwd|authorization|signature|sig|key)"
    r"[\"']?\s*[=:]\s*[\"']?(?:bearer\s+)?)[^\s\"'&,;}]+")
_BEARER = re.compile(r"(?i)\b(bearer|bot)\s+[A-Za-z0-9._~+/=-]{12,}")
_WEBHOOK = re.compile(r"(?i)(discord(?:app)?\.com/api/webhooks/\d+/)[\w-]+")
_state = {"ready": False, "native": None, "unclean": False}


def folder():
    path = os.path.join(data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def path(name="chatdoom.log"):
    return os.path.join(folder(), name)


def redact(text):
    text = _WEBHOOK.sub(r"\1***", str(text))
    text = _BEARER.sub(r"\1 ***", text)
    return _SECRET.sub(r"\1***", text)


class _Redact(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


class _Stream:
    """Stands in for stdout/stderr in the installed app (they are None there), so stray prints and library noise are kept."""
    def __init__(self, level):
        self.level = level
        self.buf = ""

    def write(self, text):
        self.buf += str(text)
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                LOG.log(self.level, "[output] %s", line.rstrip())
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


def crash(kind, exc=None, value=None, tb=None):
    """Writes a crash with its traceback to crash.log and chatdoom.log. Never raises."""
    try:
        if exc is None:
            exc, value, tb = sys.exc_info()
        details = "".join(traceback.format_exception(exc, value, tb)) if exc else "%s\n" % value
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(path("crash.log"), "a", encoding="utf-8") as f:
            f.write("\n--- %s  v%s  %s  (%s)\n%s" % (stamp, VERSION, kind, threading.current_thread().name, redact(details)))
        LOG.critical("CRASH (%s): %s", kind, details.rstrip())
    except Exception:
        pass


def _qt_handler(mode, context, message):
    try:
        from PySide6.QtCore import QtMsgType
        level = {QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
                 QtMsgType.QtFatalMsg: logging.CRITICAL, QtMsgType.QtInfoMsg: logging.INFO}.get(mode, logging.DEBUG)
        where = ""
        if context is not None and getattr(context, "file", None):
            where = " (%s:%s)" % (context.file, context.line)
        LOG.log(level, "[Qt] %s%s", message, where)
    except Exception:
        pass


def _pid_alive(pid):
    if pid <= 0 or pid == os.getpid():
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            handle = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            code = ctypes.c_ulong()
            k.GetExitCodeProcess(handle, ctypes.byref(code))
            k.CloseHandle(handle)
            return code.value == 259                              # STILL_ACTIVE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _check_last_run():
    """A marker lives while the app runs; finding one from a process that is gone means the last session ended without closing."""
    marker = path("running")
    try:
        with open(marker, encoding="utf-8") as f:
            old = int((f.read() or "0").split()[0])
        if not _pid_alive(old):
            _state["unclean"] = True
            LOG.warning("The last session (pid %d) did not close normally: it crashed, was ended from Task Manager, or Windows shut down.", old)
    except (OSError, ValueError, IndexError):
        pass
    try:
        with open(marker, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def last_run_unclean():
    return _state["unclean"]


def _move_old_crash_log():
    """Before 1.4.6 crash.log sat in the data folder itself."""
    old = os.path.join(data_dir(), "crash.log")
    try:
        if os.path.isfile(old):
            with open(old, encoding="utf-8", errors="replace") as src:
                text = src.read()[-CRASH_LIMIT:]
            with open(path("crash.log"), "a", encoding="utf-8") as dst:
                dst.write(text)
            os.remove(old)
    except OSError:
        pass


def setup(detailed=False):
    """Call first thing in main(). Safe to call twice."""
    if _state["ready"]:
        set_detailed(detailed)
        return
    _state["ready"] = True
    logging.raiseExceptions = False                 # a locked log file must never break the app
    try:
        handler = logging.handlers.RotatingFileHandler(path(), maxBytes=LOG_BYTES, backupCount=LOG_COPIES, encoding="utf-8", delay=True)
        handler.setFormatter(_Redact("%(asctime)s %(levelname)-7s %(threadName)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
        LOG.addHandler(handler)
    except OSError:
        pass
    LOG.propagate = False
    set_detailed(detailed)
    _move_old_crash_log()
    if sys.stdout is None:
        sys.stdout = _Stream(logging.INFO)
    if sys.stderr is None:
        sys.stderr = _Stream(logging.WARNING)
    logging.captureWarnings(True)
    warn = logging.getLogger("py.warnings")
    for h in LOG.handlers:
        warn.addHandler(h)
    try:
        _state["native"] = open(path("native-crash.log"), "a", encoding="utf-8")
        faulthandler.enable(file=_state["native"], all_threads=True)
    except Exception:
        pass
    sys.excepthook = lambda exc, value, tb: crash("error", exc, value, tb)
    threading.excepthook = lambda a: crash("thread " + (a.thread.name if a.thread else "?"), a.exc_type, a.exc_value, a.exc_traceback)
    sys.unraisablehook = lambda u: LOG.warning("Ignored error in %r: %s", u.object, "".join(
        traceback.format_exception(u.exc_type, u.exc_value, u.exc_traceback)).rstrip())
    LOG.info("===== CHATDOOM %s starting (pid %d, %s, Windows %s, Python %s, %s) =====", VERSION, os.getpid(),
             "installed" if getattr(sys, "frozen", False) else "from source", platform.version(), platform.python_version(),
             platform.machine())
    _check_last_run()


def hook_qt():
    """After PySide6 is imported: Qt's own warnings go to the log too."""
    try:
        from PySide6 import __version__ as pyside
        from PySide6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(_qt_handler)
        LOG.info("Qt %s", pyside)
    except Exception:
        LOG.exception("Could not hook Qt messages")


def set_detailed(on):
    """Detailed logs (Settings > Advanced) add every chat decision. Off: warnings, errors and the main events."""
    LOG.setLevel(logging.DEBUG if on else logging.INFO)


def closing(summary=""):
    LOG.info("===== CHATDOOM closing normally%s =====", (": " + summary) if summary else "")
    try:
        with open(path("running"), encoding="utf-8") as f:
            mine = f.read().strip() == str(os.getpid())     # after Restart the new copy owns the marker
        if mine:
            os.remove(path("running"))
    except OSError:
        pass
    for h in LOG.handlers:
        try:
            h.flush()
        except Exception:
            pass


def save_zip(target):
    """Puts every log into one zip for support. Returns the number of files."""
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(folder())):
            full = os.path.join(folder(), name)
            if name != "running" and os.path.isfile(full) and os.path.getsize(full):
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        z.writestr(name, redact(f.read()))
                    count += 1
                except OSError:
                    pass
        z.writestr("about.txt", "CHATDOOM %s\nWindows %s\nPython %s\nSaved %s\n" % (
            VERSION, platform.version(), platform.python_version(), datetime.datetime.now().isoformat(timespec="seconds")))
    return count


def get(name):
    """A child logger, e.g. logs.get("voice")."""
    return LOG.getChild(name)
