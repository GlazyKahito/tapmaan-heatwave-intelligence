"""Local development server: static files from public/, everything else rendered by Python.

    python server.py            -> http://localhost:8000
"""

import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tapmaan.web import route

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, "public")


class DevHandler(BaseHTTPRequestHandler):
    def _send(self, status, ctype, payload, cache=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache or "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        for i in range(0, len(payload), 16384):  # chunked writes are more reliable on Windows sockets
            self.wfile.write(payload[i:i + 16384])
        self.wfile.flush()

    def do_GET(self):
        rel = self.path.split("?")[0].lstrip("/")
        full = os.path.normpath(os.path.join(PUBLIC, rel))
        if rel and full.startswith(PUBLIC) and os.path.isfile(full):
            with open(full, "rb") as f:
                data = f.read()
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith(("javascript", "svg+xml")):
                ctype += "; charset=utf-8"
            return self._send(200, ctype, data, "public, max-age=60")
        return self._send(*route("GET", self.path))

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self._send(*route("POST", self.path, self.rfile.read(length) if length else b""))

    def log_message(self, fmt, *args):
        sys.stderr.write("[tapmaan] " + fmt % args + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Tapmaan running on http://localhost:{port}")
    ThreadingHTTPServer(("", port), DevHandler).serve_forever()
