"""Vercel serverless entry point (Python runtime, standard library only)."""

import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tapmaan.web import route  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _respond(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        status, ctype, payload, cache = route(method, self.path, body)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache or "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._respond("GET")

    def do_POST(self):
        self._respond("POST")
