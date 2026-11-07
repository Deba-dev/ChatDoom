"""Removes what the app leaves behind, so it never slowly fills the user's drive.

Only the app's own leftovers are touched: settings, music, memes, sounds and backgrounds are never removed.
"""
import glob
import os
import shutil
import tempfile
import time

from .settings import data_dir

STALE = 24 * 3600               # a leftover this old belongs to no running voice, preview or download
LOG_LIMIT = 256 * 1024          # a log keeps its newest part, which is the part worth reading
TEMP_PATTERNS = ("chatvoice_*.mp3", "chatdoom-*", "CHATDOOM-Setup-*.exe")


def remove(path):
    try:
        if os.path.isdir(path):
            size = sum(os.path.getsize(os.path.join(r, f)) for r, _, files in os.walk(path) for f in files)
            shutil.rmtree(path)
        else:
            size = os.path.getsize(path)
            os.remove(path)
    except OSError:
        return 0                # in use or already gone
    return size


def old(path, now):
    try:
        return now - os.path.getmtime(path) > STALE
    except OSError:
        return False


def trim_log(path, limit=LOG_LIMIT):
    """Keeps the last part of a log that only ever grows."""
    try:
        size = os.path.getsize(path)
        if size <= limit:
            return 0
        with open(path, "rb") as f:
            f.seek(size - limit)
            tail = f.read()
        tail = tail[tail.find(b"\n") + 1:]          # start on a whole line
        with open(path, "wb") as f:
            f.write(tail)
        return size - len(tail)
    except OSError:
        return 0


def run(now=None):
    """Returns the bytes freed. Safe to call at every start."""
    now = now or time.time()
    freed = 0
    temp = glob.escape(tempfile.gettempdir())
    for pattern in TEMP_PATTERNS:
        for path in glob.glob(os.path.join(temp, pattern)):
            if old(path, now):
                freed += remove(path)
    downloads = os.path.join(data_dir(), "MusicDownloads")      # tracks are copied into Music or Soundboard
    if os.path.isdir(downloads):
        for name in os.listdir(downloads):
            path = os.path.join(downloads, name)
            if old(path, now):
                freed += remove(path)
    for name in ("crash.log", "update.log"):
        freed += trim_log(os.path.join(data_dir(), name))
    return freed
