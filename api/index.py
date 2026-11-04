"""Vercel entrypoint: serves the CounterSign app (UI and API) as one Python serverless function."""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "countersign"
sys.path.insert(0, str(APP_DIR))

from app import Handler  # noqa: E402


class handler(Handler):  # Vercel looks for a BaseHTTPRequestHandler subclass named `handler`
    pass
