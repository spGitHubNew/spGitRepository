"""Vercel entrypoint: serves the CounterSign app (UI and API) as one Python serverless function."""

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

APP_DIR = Path(__file__).resolve().parents[1] / "countersign"
sys.path.insert(0, str(APP_DIR))

from app import Handler  # noqa: E402


class handler(Handler):  # Vercel looks for a BaseHTTPRequestHandler subclass named `handler`
    def route(self, method):
        # vercel.json rewrites every URL to /api/index?__path=<original path>; restore the original URL.
        url = urlparse(self.path)
        params = parse_qsl(url.query, keep_blank_values=True)
        original = [v for k, v in params if k == "__path"]
        if original:
            rest = urlencode([(k, v) for k, v in params if k != "__path"])
            self.path = "/" + original[0].lstrip("/") + ("?" + rest if rest else "")
        return super().route(method)
