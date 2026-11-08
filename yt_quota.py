"""Local YouTube Data API quota counter for MateAI Studio. Counts only, kept in $MATEAI_YT_HOME/youtube_quota.json;
nothing is sent anywhere. Records only when MATEAI_LAUNCHER=desktop and MATEAI_YT_HOME are set (the desktop app), because
the plugin itself also sets MATEAI_YT_HOME, and plain plugin users shouldn't get a new file.

Record: build("youtube", "v3", ..., requestBuilder=yt_quota.CountingRequest).
Usage: yt_quota.py -> one JSON object on the last stdout line:
{"limit", "upload_limit", "today": {date, units, uploads}, "days": [7 days, newest first]}.
The file holds raw calls per Pacific day, {"YYYY-MM-DD": {"youtube.videos.list": 3}}; units are computed on read.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.http import HttpRequest

LIMIT = 10000
UPLOAD_LIMIT = 100
# Units per call, from https://developers.google.com/youtube/v3/determine_quota_cost (checked 2026-11-08).
# videos.insert and search.list have their own 100-calls/day buckets there, so they don't count toward LIMIT.
COSTS = {
    "captions.list": 50, "captions.insert": 400, "captions.update": 450, "captions.delete": 50,
    "channelBanners.insert": 50, "channels.update": 50,
    "channelSections.insert": 50, "channelSections.update": 50, "channelSections.delete": 50,
    "comments.insert": 50, "comments.update": 50, "comments.setModerationStatus": 50, "comments.delete": 50,
    "commentThreads.insert": 50, "commentThreads.update": 50,
    "liveChatBans.insert": 200, "liveChatBans.delete": 200,
    "liveChatMessages.insert": 20, "liveChatMessages.delete": 20, "liveChatMessages.transition": 20,
    "liveChatMessages.list": 5, "liveChatMessages.streamList": 5,
    "liveChatModerators.insert": 200, "liveChatModerators.delete": 200, "liveChatModerators.list": 50,
    "playlistItems.insert": 50, "playlistItems.update": 50, "playlistItems.delete": 50,
    "playlists.insert": 50, "playlists.update": 50, "playlists.delete": 50,
    "subscriptions.insert": 50, "subscriptions.delete": 50, "thumbnails.set": 50,
    "videos.update": 50, "videos.rate": 50, "videos.reportAbuse": 50, "videos.delete": 50,
    "watermarks.set": 50, "watermarks.unset": 50,
    "videos.insert": 0, "search.list": 0,  # separate buckets, see above
}  # every other documented method (list, getRating, liveBroadcasts.*, liveStreams.*) costs 1


def _pacific():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/Los_Angeles")
    except Exception:  # Windows has no tz database without the tzdata package
        # shortcut: fixed UTC-8 ignores daylight time (day boundary off by 1 h in summer), bundle tzdata if Windows ships
        return timezone(timedelta(hours=-8))


PACIFIC = _pacific()


def store_path():
    return Path(os.environ.get("MATEAI_YT_HOME", ".")) / "youtube_quota.json"


def _enabled():
    return os.environ.get("MATEAI_LAUNCHER", "").strip().lower() == "desktop" and bool(os.environ.get("MATEAI_YT_HOME"))


def load():
    try:
        data = json.loads(store_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # missing or corrupt -> start from zero
        return {}


def today(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(PACIFIC).date()


def record(method_id, now=None):
    """Add one call of `method_id` (e.g. "youtube.videos.list") to today's count. Never raises."""
    try:
        if not _enabled() or not str(method_id).startswith("youtube."):
            return  # Analytics API etc. have their own quota
        # shortcut: read-modify-write without a lock; the app helper and the MCP racing can lose a count. Add a file lock if numbers drift.
        data, key = load(), today(now).isoformat()
        day = data[key] = data[key] if isinstance(data.get(key), dict) else {}
        day[method_id] = int(day.get(method_id, 0)) + 1
        path = store_path()
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass  # counting must never break an API call


def day_totals(calls):
    units = uploads = 0
    for method_id, n in (calls or {}).items():
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        name = method_id.removeprefix("youtube.")
        # shortcut: methods missing from COSTS count 1 unit, as most reads do; add them when Google adds methods
        units += COSTS.get(name, 1) * n
        uploads += n if name == "videos.insert" else 0
    return {"units": units, "uploads": uploads}


def summary(now=None):
    data, first = load(), today(now)
    days = []
    for i in range(7):
        date = (first - timedelta(days=i)).isoformat()
        calls = data.get(date)
        days.append({"date": date, **day_totals(calls if isinstance(calls, dict) else {})})
    return {"limit": LIMIT, "upload_limit": UPLOAD_LIMIT, "today": days[0], "days": days}


class CountingRequest(HttpRequest):
    """HttpRequest that records one call per real API request (failed ones too: Google charges those)."""

    def execute(self, http=None, num_retries=0):
        if not self.resumable:  # resumable execute() goes through next_chunk()
            record(self.methodId)
        return super().execute(http=http, num_retries=num_retries)

    def next_chunk(self, http=None, num_retries=0):
        if self.resumable_uri is None:  # first chunk starts the upload session: one call per upload
            record(self.methodId)
        return super().next_chunk(http=http, num_retries=num_retries)


if __name__ == "__main__":
    print(json.dumps(summary()), flush=True)
    sys.exit(0)
