"""
Serve the demo locally, with answers.

The published artifact generates through the viewer's own Claude access
(`claude.use("sample")`). On localhost that does not exist, so the page falls
back to POSTing here and this proxy calls the API with the key from .env --
which is why the key stays server-side and never reaches the browser.

    .venv/bin/python serve.py            # http://localhost:8756
    .venv/bin/python serve.py --port 9000

Retrieval always runs in the browser either way; only the answer step differs.
"""

import argparse
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from embed import load_dotenv

ROOT = Path(__file__).parent / "demo"
MODEL = "claude-sonnet-5"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def guess_type(self, path):
        # Without an explicit charset the page is decoded as latin-1 and every
        # non-ASCII character (the middot in "13 chunks · 4,548 tokens") mojibakes.
        t = super().guess_type(path)
        if t in ("text/html", "text/css", "application/javascript", "text/javascript"):
            return t + "; charset=utf-8"
        return t

    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        if self.path.rstrip("/") != "/api/ask":
            self.send_error(404)
            return
        try:
            body = json.loads(self.rfile.read(
                int(self.headers.get("Content-Length", 0))) or b"{}")
            import anthropic
            resp = anthropic.Anthropic().messages.create(
                model=MODEL, max_tokens=2048,
                messages=[{"role": "user", "content": body.get("prompt", "")}])
            text = "".join(b.text for b in resp.content if b.type == "text")
            payload = {"text": text}
        except Exception as e:                       # noqa: BLE001
            payload = {"error": f"{type(e).__name__}: {e}"}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        # log_error passes an HTTPStatus here, not a string -- an unguarded
        # `in` test raises and takes the whole request thread down with it.
        first = str(args[0]) if args else ""
        if "api/ask" in first:
            print(f"  ask -> {first}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8756)
    args = ap.parse_args()
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("warning: ANTHROPIC_API_KEY not set — retrieval will work, answers will not")
    print(f"demo on http://localhost:{args.port}  (serving {ROOT})")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
