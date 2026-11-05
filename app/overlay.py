"""A tiny local web server (127.0.0.1 only) that OBS shows as a Browser Source: alerts and chat on screen."""
import json
import os
import re
import threading
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .overlay_html import INDEX, page

STUDIO_ORIGIN = "https://zunimilabs.online"
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


class Overlay:
    def __init__(self, settings, fonts_dir, cfg_fn, sounds_dir="", memes_dir=""):
        self.s, self.fonts_dir, self.cfg_fn, self.sounds_dir, self.memes_dir = settings, fonts_dir, cfg_fn, sounds_dir, memes_dir
        self.port = 0
        self.server = None
        self.error = ""
        self.lock = threading.Lock()
        self.next_id = 1
        self.events = {"alert": deque(maxlen=60), "chat": deque(maxlen=60), "meme": deque(maxlen=30)}
        self.states = {"music": {"title": "", "artist": "", "playing": False},
                       "widgets": {"counters": [], "poll": None, "giveaway": None}}

    # ----- data -----
    def push(self, kind, data):
        if kind in self.states:                              # a 'state' (like the song playing now), not a queue of events
            with self.lock:
                self.states[kind] = dict(data)
                self.next_id += 1
            return self.next_id - 1
        with self.lock:
            ev = dict(data, id=self.next_id)
            self.next_id += 1
            self.events[kind].append(ev)
            return ev["id"]

    def poll(self, kind, after):
        if kind in self.states:
            with self.lock:
                return {"events": [], "latest": self.next_id - 1, "state": dict(self.states[kind]), "cfg": self.cfg_fn()}
        with self.lock:
            latest = self.next_id - 1
            evs = [] if after < 0 else [e for e in self.events[kind] if e["id"] > after]
        return {"events": evs, "latest": latest, "cfg": self.cfg_fn()}

    def url(self, kind):
        return "http://127.0.0.1:%d/%s" % (self.port, kind) if self.port else ""

    # ----- server -----
    def start(self):
        overlay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype):
                data = body if isinstance(body, bytes) else body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self._studio_headers()
                self.end_headers()
                self.wfile.write(data)

            def _studio_headers(self):
                """Overlay Studio's page may read /poll. Every other website stays blocked by the browser."""
                if self.path.startswith("/poll") and self.headers.get("Origin") == STUDIO_ORIGIN:
                    self.send_header("Access-Control-Allow-Origin", STUDIO_ORIGIN)
                    self.send_header("Access-Control-Allow-Private-Network", "true")
                    self.send_header("Vary", "Origin")

            def do_OPTIONS(self):
                self.send_response(204)
                self._studio_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                if u.path in ("/", ""):
                    return self._send(200, INDEX, "text/html; charset=utf-8")
                if u.path in ("/alert", "/chat", "/music", "/meme", "/widgets"):
                    return self._send(200, page(u.path[1:]), "text/html; charset=utf-8")
                if u.path == "/poll":
                    q = urllib.parse.parse_qs(u.query)
                    kind = q.get("type", ["alert"])[0]
                    try:
                        after = int(q.get("after", ["-1"])[0])
                    except ValueError:
                        after = -1
                    if kind not in overlay.events and kind not in overlay.states:
                        return self._send(400, "{}", "application/json")
                    return self._send(200, json.dumps(overlay.poll(kind, after)), "application/json")
                m = re.fullmatch(r"/fonts/(Poppins-[A-Za-z]+\.ttf)", u.path)
                if m:
                    f = os.path.join(overlay.fonts_dir, m.group(1))
                    if os.path.isfile(f):
                        with open(f, "rb") as fh:
                            return self._send(200, fh.read(), "font/ttf")
                sound_path = urllib.parse.unquote(u.path)
                m = re.fullmatch(r"/sounds/([^/\\]{1,220})", sound_path)
                if m and overlay.sounds_dir:
                    name = m.group(1)
                    if os.path.splitext(name)[1].lower() not in (".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus"):
                        return self._send(404, "not found", "text/plain")
                    f = os.path.realpath(os.path.join(overlay.sounds_dir, name))
                    root = os.path.realpath(overlay.sounds_dir)
                    if os.path.basename(f) == name and os.path.commonpath((root, f)) == root and os.path.isfile(f):
                        ctype = {"mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg", "flac": "audio/flac",
                                 "m4a": "audio/mp4", "aac": "audio/aac", "opus": "audio/ogg"}[os.path.splitext(f)[1].lower()[1:]]
                        with open(f, "rb") as fh:
                            return self._send(200, fh.read(), ctype)
                m = re.fullmatch(r"/memes/([^/\\]{1,220})", sound_path)
                if m and overlay.memes_dir:
                    name = m.group(1)
                    ctype = IMAGE_TYPES.get(os.path.splitext(name)[1].lower())
                    f = os.path.realpath(os.path.join(overlay.memes_dir, name))
                    root = os.path.realpath(overlay.memes_dir)
                    if ctype and os.path.basename(f) == name and os.path.commonpath((root, f)) == root and os.path.isfile(f):
                        with open(f, "rb") as fh:
                            return self._send(200, fh.read(), ctype)
                self._send(404, "not found", "text/plain")

        start = int(self.s.get("ov_port"))
        for port in range(start, start + 25):
            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
                self.server.daemon_threads = True
                break
            except OSError:
                continue
        if not self.server:
            self.error = "Could not open a local port for the overlays"
            return False
        self.port = self.server.server_address[1]
        if self.port != start:
            self.s.set("ov_port", self.port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return True

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
