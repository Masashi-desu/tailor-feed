#!/usr/bin/env python3
"""Static server for public/ (default 127.0.0.1:8095). Usage: python serve.py [--host H] [--port P]"""
import argparse, functools, os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".svg": "image/svg+xml",
                      ".webp": "image/webp", ".html": "text/html; charset=utf-8"}
    def end_headers(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def log_message(self, *a): pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("TAILOR_FEED_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("TAILOR_FEED_PORT", "8095")))
    a = ap.parse_args()
    h = functools.partial(Handler, directory=os.path.join(BASE, "public"))
    ThreadingHTTPServer((a.host, a.port), h).serve_forever()

if __name__ == "__main__":
    main()
