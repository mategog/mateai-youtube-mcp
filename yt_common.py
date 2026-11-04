"""
mateai-youtube-mcp — Shared paths, constants and HTTP helpers for the YouTube modules
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# State (venv, tokens, OAuth secret, snapshot, report) lives in MATEAI_YT_HOME when set
# (the Claude Code plugin points it at ${CLAUDE_PLUGIN_DATA}), else next to this file.
STATE_DIR = Path(os.environ.get("MATEAI_YT_HOME") or HERE).expanduser()
for _sp in sorted((STATE_DIR / ".venv" / "lib").glob("python*/site-packages")):
    if str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

CACHE_FILE = STATE_DIR / "channel_snapshot.json"
REPORT_FILE = STATE_DIR / "report.html"
TEMPLATE_FILE = HERE / "report_template.html"

DEFAULT_HANDLE = "@mateai-c6m"
AUTHOR_ATTRIBUTION = "MateAI (https://www.youtube.com/@mateai-c6m)"

HTTP_HEADERS = {
    "User-Agent": "mateai-youtube-mcp (+https://github.com/mategog/mateai-youtube-mcp)",
    "Accept-Language": "en-US,en;q=0.9",
}


def _ssl_context() -> ssl.SSLContext:
    # python.org macOS builds ship with no CA certificates until "Install Certificates.command"
    # is run; fall back to the system bundle so HTTPS works without that manual step.
    paths = ssl.get_default_verify_paths()
    if not paths.cafile and not paths.capath and Path("/etc/ssl/cert.pem").exists():
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CONTEXT = _ssl_context()


def _http_get(url: str) -> str:
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_iso_duration(iso_str: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_str or "")
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mins * 60 + s
