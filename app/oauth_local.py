"""Catches the browser's 'come back to the app' step of a login (Discord) on this PC only (127.0.0.1)."""
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

PAGE = ("<html><head><meta charset='utf-8'><title>CHATDOOM</title></head><body style=\"font:18px 'Segoe UI',sans-serif;"
        "background:#0e1118;color:#eef;display:grid;place-items:center;height:100vh;margin:0\"><div style='text-align:center'>"
        "<div style='font-size:46px'>%s</div><h2 style='margin:8px'>%s</h2><p style='opacity:.7'>%s</p></div></body></html>")


class Loopback:
    """start() returns the address to hand to the website; the answer arrives on bridge.done as (tag, dict)."""

    def __init__(self, bridge, tag, timeout=300):
        self.bridge, self.tag, self.timeout = bridge, tag, timeout
        self.server = None
        self.cancelled = threading.Event()

    def start(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                if u.path != "/done":
                    self.send_response(404)
                    self.end_headers()
                    return
                good = q.get("ok") == "1"
                body = PAGE % (("\u2705", "You are connected", "You can close this tab and go back to CHATDOOM.") if good
                               else ("\u26a0\ufe0f", "Not connected", "Nothing was changed. You can close this tab and try again in CHATDOOM."))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode())
                owner.result = q

        self.result = None
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.server.timeout = 1
        port = self.server.server_port

        def work():
            end = time.time() + self.timeout
            while time.time() < end and self.result is None and not self.cancelled.is_set():
                self.server.handle_request()
            self.server.server_close()
            if self.cancelled.is_set():
                return
            self.bridge.done.emit(self.tag, self.result if self.result is not None else {"ok": "0", "error": "timed out"})

        threading.Thread(target=work, daemon=True).start()
        return "http://127.0.0.1:%d/done" % port

    def cancel(self):
        self.cancelled.set()
