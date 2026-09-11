#!/usr/bin/env python3
"""Local HTML -> PDF render service (WeasyPrint).

Usage:
    .venv/bin/python tools/html2pdf_server.py [port]      # default 8765

Endpoints (loopback only, no auth — dev tool):
    GET  /health   -> {"ok": true}
    POST /render   -> body JSON: {"path": "<file rel. to repo root>",
                                  "out":  "<optional pdf name>"}
                      renders HTML to PDF (out defaults to <path>.pdf),
                      returns {"pdf": path, "pages": n}

Writes are atomic (tmp + rename), matching repo convention. Paths are
restricted to the working directory tree — no absolute traversal.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import weasyprint

ROOT = Path.cwd().resolve()


def resolve_in_root(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if not p.is_relative_to(ROOT):
        raise ValueError(f"path escapes working dir: {rel!r}")
    return p


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload, ctype: str = "application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (http.server API)
        if urlparse(self.path).path == "/health":
            self._send(200, {"ok": True, "root": str(ROOT)})
        else:
            self._send(404, {"error": "unknown route; try GET /health"})

    def do_POST(self):  # noqa: N802 (http.server API)
        if urlparse(self.path).path != "/render":
            self._send(404, {"error": "unknown route; try POST /render"})
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n))
            src = resolve_in_root(req["path"])
            if not src.is_file():
                raise ValueError(f"no such file: {req['path']}")
            if req.get("out"):
                dst = resolve_in_root(req["out"])
            else:
                dst = src.with_suffix(".pdf")
        except Exception as e:
            self._send(400, {"error": f"{type(e).__name__}: {e}"})
            return
        try:
            doc = weasyprint.HTML(filename=str(src)).render()
            pages = len(doc.pages)
            tmp = dst.with_name(dst.name + ".tmp")
            doc.write_pdf(str(tmp))
            tmp.replace(dst)
        except Exception as e:
            self._send(500, {"error": f"{type(e).__name__}: {e}"})
            return
        self._send(200, {"pdf": str(dst.relative_to(ROOT)), "pages": pages})

    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"html2pdf listening on http://127.0.0.1:{port} (root: {ROOT})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
