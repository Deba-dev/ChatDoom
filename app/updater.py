"""Update check and one-click update, using GitHub Releases (free, no server of our own)."""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, Signal

from .settings import data_dir
from .version import VERSION

GH_API = "https://api.github.com"


def parse_version(v):
    """V1.0.4.1 -> (1, 0, 4, 1). Only the leading numbers count, so a suffix like -v2 is not read as a version."""
    match = re.match(r"\s*[vV]?(\d+(?:\.\d+){0,3})", v or "")
    nums = [int(x) for x in match.group(1).split(".")] if match else []
    return tuple(nums + [0] * (4 - len(nums)))


def clean_env():
    """Environment for the installer. A frozen app passes on PyInstaller's own settings, and the new app started by the
    installer would otherwise load files as if it were part of the old one."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI", "QT_", "QML", "PYSIDE"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if not p.startswith(bundle))
    return env


def update_log():
    return os.path.join(data_dir(), "update.log")


class Updater(QObject):
    found = Signal(object)        # {"version", "page", "asset", "digest", "notes"}
    message = Signal(str)
    status = Signal(str)          # manual check: nothing to install, or the check failed
    progress = Signal(str)
    quit_now = Signal()
    _evt = Signal(str, object)    # from worker threads

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.frozen = bool(getattr(sys, "frozen", False))      # only the installed app can replace itself
        self.busy = False
        self._evt.connect(self._on_evt)

    # ----- check -----
    def check(self, manual=False):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._check, args=(manual,), daemon=True).start()

    def _fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "CHATDOOM-updater", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())

    def _check(self, manual):
        repo = self.s.get("update_repo").strip()
        try:
            d = self._fetch("%s/repos/%s/releases/latest" % (GH_API, repo))
            tag = d.get("tag_name", "")
            if parse_version(tag) <= parse_version(VERSION):
                self.s.set("update_last", int(time.time()))
                if manual:
                    self._evt.emit("status", "There is not any update at all. Wait for the devs to update the app.")
                return
            asset = next((a for a in d.get("assets", []) if a.get("name", "").lower().endswith("setup.exe")), None)
            if not asset:          # a release goes public 5-10 minutes before its installer is built: look again later
                if manual:
                    self._evt.emit("status", "A new version is being prepared. Check again in about 10 minutes.")
                return
            self.s.set("update_last", int(time.time()))
            canonical_repo = self._release_repo(d.get("html_url", ""))
            if canonical_repo:
                self.s.set("update_repo", canonical_repo)
            self._evt.emit("found", {"version": tag.lstrip("vV"), "page": d.get("html_url", ""),
                                     "asset": asset.get("browser_download_url", ""),
                                     "digest": asset.get("digest", ""), "notes": (d.get("body") or "")[:300],
                                     "repo": canonical_repo or repo})
        except Exception as e:
            if manual:
                self._evt.emit("status", "Could not check for updates (%s)" % str(e)[:60])
        finally:
            self._evt.emit("idle", None)

    # ----- install -----
    def install(self, info):
        asset = info.get("asset", "")
        repo = (info.get("repo") or self.s.get("update_repo") or "").strip().strip("/")
        if not self._is_release_asset(asset, repo):
            self.message.emit("The update file is not from your GitHub repository, so it was not downloaded.")
            return
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._download, args=(info,), daemon=True).start()

    @staticmethod
    def _release_repo(page_url):
        parsed = urllib.parse.urlparse(page_url or "")
        match = re.fullmatch(r"/([^/]+)/([^/]+)/releases/tag/[^/]+", parsed.path)
        if parsed.scheme != "https" or parsed.hostname != "github.com" or not match:
            return ""
        return "%s/%s" % (match.group(1), match.group(2))

    @staticmethod
    def _is_release_asset(asset, repo):
        if not repo or repo.count("/") != 1:
            return False
        parsed = urllib.parse.urlparse(asset or "")
        owner, name = repo.split("/", 1)
        prefix = "/%s/%s/releases/download/" % (owner, name)
        path = urllib.parse.unquote(parsed.path)
        return (parsed.scheme == "https" and parsed.hostname == "github.com"
                and parsed.username is None and parsed.password is None
                and path.casefold().startswith(prefix.casefold())
                and all(part not in (".", "..") for part in path.split("/")))

    def _download(self, info):
        path = os.path.join(tempfile.gettempdir(), "CHATDOOM-Setup-%s.exe" % info["version"])
        try:
            req = urllib.request.Request(info["asset"], headers={"User-Agent": "CHATDOOM-updater"})
            sha, done = hashlib.sha256(), 0
            with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if total:
                        self._evt.emit("progress", "Downloading update... %d%%" % (done * 100 // total))
            if total and done != total:
                os.remove(path)
                self._evt.emit("note", "The update download stopped early. Please try again.")
                return
            want = (info.get("digest") or "").lower()
            if want.startswith("sha256:") and want[7:] != sha.hexdigest():
                os.remove(path)
                self._evt.emit("note", "The downloaded update did not match GitHub's checksum, so it was discarded.")
                return
            self.s.set("update_pending", info["version"])
            self._evt.emit("ready", path)
        except Exception as e:
            self._evt.emit("note", "Update download failed (%s)" % str(e)[:60])
        finally:
            self._evt.emit("idle", None)

    def launch(self, path):
        flags = 0x00000008 if sys.platform == "win32" else 0        # DETACHED_PROCESS
        subprocess.Popen([path, "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/LOG=" + update_log()],
                         close_fds=True, creationflags=flags, env=clean_env())

    def after_start(self):
        """Run once at startup: says if the last update did not finish, and removes old installers (160 MB each)."""
        pending = self.s.get("update_pending")
        if pending:
            self.s.set("update_pending", "")
            if parse_version(VERSION) < parse_version(pending):
                self.message.emit("The update to %s did not finish, so you are still on %s. Press Check for updates to try again. "
                                  "Details: %s" % (pending, VERSION, update_log()))
        for path in glob.glob(os.path.join(glob.escape(tempfile.gettempdir()), "CHATDOOM-Setup-*.exe")):
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            from . import cleanup
            cleanup.run()           # crashed voice files, imported music downloads, oversized logs
        except Exception:
            pass                    # cleaning up must never get in the way of starting

    def _on_evt(self, kind, data):
        if kind == "found":
            self.found.emit(data)
        elif kind == "note" and data:
            self.message.emit(data)
        elif kind == "status" and data:
            self.status.emit(data)
        elif kind == "progress":
            self.progress.emit(data)
        elif kind == "idle":
            self.busy = False
        elif kind == "ready":
            self.progress.emit("Installing update...")
            self.launch(data)
            self.quit_now.emit()
