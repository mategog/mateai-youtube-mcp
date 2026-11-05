"""
mateai-youtube-mcp — Shared paths, constants and HTTP helpers for the YouTube modules
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Any, TypedDict

HERE = Path(__file__).resolve().parent
# State (venv, tokens, OAuth secret, snapshot, report) lives in MATEAI_YT_HOME when set
# (the Claude Code plugin points it at ${CLAUDE_PLUGIN_DATA}), else next to this file.
STATE_DIR = Path(os.environ.get("MATEAI_YT_HOME") or HERE).expanduser()


def add_venv_to_path() -> None:
    for sp in sorted((STATE_DIR / ".venv" / "lib").glob("python*/site-packages")):
        if str(sp) not in sys.path:
            sys.path.insert(0, str(sp))


add_venv_to_path()

CACHE_FILE = STATE_DIR / "channel_snapshot.json"
REPORT_FILE = STATE_DIR / "report.html"
TEMPLATE_FILE = HERE / "report_template.html"

DEFAULT_HANDLE = "@mateai-c6m"
AUTHOR_ATTRIBUTION = "MateAI (https://www.youtube.com/@mateai-c6m)"

HTTP_HEADERS = {
    "User-Agent": "mateai-youtube-mcp (+https://github.com/mategog/mateai-youtube-mcp)",
    "Accept-Language": "en-US,en;q=0.9",
}


QUOTA_EXCEEDED_MSG = (
    "YouTube API quota or rate limit reached, so this stopped and nothing more was sent. All MateAI users share "
    "one Google Cloud project's daily quota, which resets at midnight Pacific time (PT). Do not retry or loop; "
    "try again after the reset."
)


def is_quota_error(exc: BaseException) -> bool:
    """True for a YouTube quotaExceeded / rateLimitExceeded HttpError (HTTP 403 or 429). Duck-typed, no Google libs."""
    if getattr(getattr(exc, "resp", None), "status", None) not in (403, 429):
        return False
    content = getattr(exc, "content", b"")
    if isinstance(content, bytes):
        content = content.decode("utf-8", "replace")
    text = f"{content} {getattr(exc, 'error_details', '')} {exc}"
    return "quotaExceeded" in text or "rateLimitExceeded" in text


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


# The snapshot shape shared by the public, Studio and TikTok fetchers, the HTML report and the tables.
# Annotations only (nothing is checked at runtime). Studio-only analytics fields are None in public mode.
class _YouTubeVideoRequired(TypedDict):
    videoId: str
    title: str
    format: str  # "short" | "long"
    publishDate: str
    durationSec: int
    views: int
    likes: int | None
    comments: int | None
    engagedViews: int | None
    viewedVsSwipedPct: float | None
    avgViewDurationSec: float | None
    avgViewPct: float | None
    watchTimeMin: float | None
    subsGained: int | None
    url: str
    thumbnail: str
    descriptionPreview: str
    sourceMode: str  # "public" | "studio_oauth"


class YouTubeVideo(_YouTubeVideoRequired, total=False):
    privacyStatus: str  # Studio mode only


class TikTokVideo(TypedDict):
    videoId: str
    title: str
    videoDescription: str
    publishDate: str
    durationSec: int
    views: int
    likes: int
    comments: int
    shares: int
    url: str
    thumbnail: str
    sourceMode: str  # "tiktok_oauth"


class Totals(TypedDict, total=False):
    videoCount: int  # videos in THIS snapshot (a TikTok channel's own videoCount is the account total)
    shortsCount: int  # YouTube only
    longCount: int  # YouTube only
    totalViews: int
    topVideo: dict[str, Any] | None


class Snapshot(TypedDict):
    generatedAt: str
    mode: str  # "public" | "studio_oauth" | "tiktok_oauth"
    channel: dict[str, Any]  # YouTube: handle, title, description, subscribersText, avatarUrl, url; TikTok: see fetch_tiktok_snapshot
    totals: Totals
    videos: list[Any]  # YouTubeVideo or TikTokVideo
    attribution: str


def snapshot_envelope(mode: str, channel: dict, videos: list[dict], *, youtube_counts: bool) -> Snapshot:
    """The snapshot shape shared by the public, Studio and TikTok fetchers."""
    totals = {"videoCount": len(videos)}
    if youtube_counts:
        totals["shortsCount"] = sum(1 for v in videos if v["format"] == "short")
        totals["longCount"] = sum(1 for v in videos if v["format"] == "long")
    totals["totalViews"] = sum(v.get("views", 0) or 0 for v in videos)
    totals["topVideo"] = max(videos, key=lambda x: x.get("views", 0)) if videos else None
    return {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": mode,
        "channel": channel,
        "totals": totals,
        "videos": videos,
        "attribution": AUTHOR_ATTRIBUTION,
    }


def write_snapshot_cache(snap: dict, path: Path) -> None:
    path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
