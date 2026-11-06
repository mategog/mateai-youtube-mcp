"""
mateai-youtube-mcp — Channel snapshot (Studio OAuth or opt-in public), Shorts table and HTML report
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

import yt_auth
import yt_common
import yt_public
from yt_auth import DEFAULT_CLIENT_SECRET
from yt_common import DEFAULT_HANDLE, _parse_iso_duration


# Public page scraping is opt-in: the default path is the official YouTube APIs via OAuth.
# Enable it per call (force_public / --public) or always with MATEAI_YT_PUBLIC_SCRAPE=1.
PUBLIC_SCRAPE_ENV = os.environ.get("MATEAI_YT_PUBLIC_SCRAPE") == "1"
SCRAPE_DISABLED_MSG = (
    "No YouTube OAuth credentials found, and public page scraping is off by default. "
    "Run `python3 yt_studio.py setup` (with MATEAI_YT_HOME set to the plugin data folder) to connect "
    "your channel through the official YouTube APIs, or opt in to public scraping with "
    "force_public=true / --public, or MATEAI_YT_PUBLIC_SCRAPE=1."
)


def _http_status(exc: Exception) -> int | None:
    """HTTP status of a googleapiclient HttpError (duck-typed so tests need no Google libraries)."""
    return getattr(getattr(exc, "resp", None), "status", None)


def fetch_studio_channel_snapshot(
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
    days: int = 90,
) -> yt_common.Snapshot:
    """Fetch full private Studio metrics via YouTube Data API v3 + YouTube Analytics API v2."""
    yt, yta = yt_auth._youtube_and_analytics_clients(client_secret_path)

    ch_resp = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
    if not ch_resp.get("items"):
        raise RuntimeError("No YouTube channel found for the authenticated Google account.")

    ch = ch_resp["items"][0]
    uploads_playlist = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    snippet = ch["snippet"]
    stats = ch["statistics"]

    # Fetch recent uploads
    pl_resp = yt.playlistItems().list(
        part="contentDetails,snippet", playlistId=uploads_playlist, maxResults=50
    ).execute()
    video_ids = [item["contentDetails"]["videoId"] for item in pl_resp.get("items", [])]

    v_resp = yt.videos().list(
        part="snippet,contentDetails,statistics,status",
        id=",".join(video_ids),
    ).execute() if video_ids else {"items": []}

    # Query YouTube Analytics API per video
    end_date = dt.date.today().isoformat()
    start_date = (dt.date.today() - dt.timedelta(days=days)).isoformat()

    def _query_by_video(metrics: str) -> dict[str, Any]:
        return yta.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=metrics,
            dimensions="video",
            maxResults=50,
            sort="-views",
        ).execute()

    base_metrics = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained"
    try:
        rep = _query_by_video(base_metrics.replace("views,", "views,engagedViews,", 1))
    except Exception as exc:
        # Only "this metric isn't supported for the window" (HTTP 400) is worth a retry without
        # engagedViews. Auth, quota and network errors must surface, not turn into empty analytics.
        if _http_status(exc) != 400:
            raise
        rep = _query_by_video(base_metrics)
    headers = [h["name"] for h in rep.get("columnHeaders", [])]
    analytics_by_vid: dict[str, dict[str, Any]] = {}
    for row in rep.get("rows", []):
        row_dict = dict(zip(headers, row))
        analytics_by_vid[row_dict["video"]] = row_dict

    items: list[dict[str, Any]] = []
    for v in v_resp.get("items", []):
        vid = v["id"]
        v_snip = v["snippet"]
        v_stat = v.get("statistics", {})
        dur_iso = v["contentDetails"].get("duration", "PT0S")
        dur_sec = _parse_iso_duration(dur_iso)
        is_short = 0 < dur_sec <= 180

        a = analytics_by_vid.get(vid, {})
        views = int(v_stat.get("viewCount", a.get("views", 0)) or 0)
        engaged = a.get("engagedViews")
        viewed_vs_swiped = round((engaged / views) * 100, 1) if (engaged and views > 0) else None

        items.append({
            "videoId": vid,
            "title": v_snip.get("title", vid),
            "format": "short" if is_short else "long",
            "privacyStatus": v.get("status", {}).get("privacyStatus", "public"),
            "publishDate": v_snip.get("publishedAt", "")[:10],
            "durationSec": dur_sec,
            "views": views,
            "likes": int(v_stat.get("likeCount", a.get("likes", 0)) or 0),
            "comments": int(v_stat.get("commentCount", a.get("comments", 0)) or 0),
            "engagedViews": int(engaged) if engaged is not None else None,
            "viewedVsSwipedPct": viewed_vs_swiped,
            "avgViewDurationSec": round(float(a["averageViewDuration"]), 1) if "averageViewDuration" in a else None,
            "avgViewPct": round(float(a["averageViewPercentage"]), 1) if "averageViewPercentage" in a else None,
            "watchTimeMin": round(float(a["estimatedMinutesWatched"]), 1) if "estimatedMinutesWatched" in a else None,
            "subsGained": int(a["subscribersGained"]) if "subscribersGained" in a else None,
            "url": f"https://www.youtube.com/shorts/{vid}" if is_short else f"https://www.youtube.com/watch?v={vid}",
            "thumbnail": v_snip.get("thumbnails", {}).get("high", {}).get("url", f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"),
            "descriptionPreview": (v_snip.get("description") or "")[:220],
            "sourceMode": "studio_oauth",
        })

    items.sort(key=lambda x: x.get("publishDate") or "", reverse=True)
    return yt_common.snapshot_envelope(
        "studio_oauth",
        {
            "handle": snippet.get("customUrl", DEFAULT_HANDLE),
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "subscribersText": f"{stats.get('subscriberCount', '0')} subscribers",
            "avatarUrl": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
            "url": f"https://www.youtube.com/{snippet.get('customUrl', DEFAULT_HANDLE)}",
        },
        items,
        youtube_counts=True,
    )


# ---------------------------------------------------------------------------
# Shorts Experiment Markdown Table Generator
# ---------------------------------------------------------------------------

def _load_shorts_styles() -> dict[str, str]:
    """Optional `shorts_styles.json` in the state folder: {"<videoId>": "C (Poster)"}. No file means style unknown."""
    path = yt_common.STATE_DIR / "shorts_styles.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    return {str(k): str(v) for k, v in data.items()}



def build_shorts_experiment_markdown(snapshot: dict[str, Any]) -> str:
    """Format the Shorts performance table matching pipeline/explainer-short/README.md."""
    lines = [
        "| Video | Style | Published | Views | Viewed vs swiped | Avg % viewed | Engaged views | Subs gained |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    styles = _load_shorts_styles()
    shorts = [v for v in snapshot.get("videos", []) if v.get("format") == "short"]
    for s in shorts:
        title = s.get("title", s["videoId"])
        pub = s.get("publishDate") or "published"
        views = f"{s.get('views', 0):,}"
        vvs = f"{s['viewedVsSwipedPct']:.1f}%" if s.get("viewedVsSwipedPct") is not None else "*(Studio OAuth)*"
        avp = f"{s['avgViewPct']:.1f}%" if s.get("avgViewPct") is not None else "*(Studio OAuth)*"
        eng = f"{s['engagedViews']:,}" if s.get("engagedViews") is not None else "*(Studio OAuth)*"
        subs = f"+{s['subsGained']}" if s.get("subsGained") is not None else "*(Studio OAuth)*"
        style = styles.get(s["videoId"], "—")
        lines.append(f"| [{title}]({s['url']}) | {style} | {pub} | {views} | {vvs} | {avp} | {eng} | {subs} |")
    return "\n".join(lines)


def render_html_report(snapshot: dict[str, Any], out_path: Path = yt_common.REPORT_FILE) -> Path:
    """Render interactive HTML dashboard from report_template.html."""
    template = yt_common.TEMPLATE_FILE.read_text(encoding="utf-8")
    # "<" escaped so a scraped "</script>" can't close the script block the JSON sits in.
    payload_json = json.dumps(snapshot, indent=2).replace("<", "\\u003c")
    rendered = template.replace("__SNAPSHOT_JSON__", payload_json)
    out_path.write_text(rendered, encoding="utf-8")
    return out_path


def get_best_snapshot(handle: str = DEFAULT_HANDLE, force_public: bool = False) -> dict[str, Any]:
    """Use Studio OAuth when configured; scrape public pages only when explicitly opted in."""
    allow_scrape = force_public or PUBLIC_SCRAPE_ENV
    if not force_public and (yt_auth.TOKEN_FILE.exists() or DEFAULT_CLIENT_SECRET.exists()):
        try:
            snap = fetch_studio_channel_snapshot()
            yt_common.write_snapshot_cache(snap, yt_common.CACHE_FILE)
            return snap
        except Exception as exc:
            if not allow_scrape or yt_common.is_quota_error(exc):
                raise
            sys.stderr.write(f"[yt_studio] Studio OAuth unavailable ({exc}); using public snapshot.\n")

    if not allow_scrape:
        raise RuntimeError(SCRAPE_DISABLED_MSG)
    snap = yt_public.fetch_public_channel_snapshot(handle=handle)
    yt_common.write_snapshot_cache(snap, yt_common.CACHE_FILE)
    return snap


def print_cli_summary(snap: dict[str, Any]) -> None:
    ch = snap["channel"]
    tot = snap["totals"]
    print(f"Channel: {ch['title']} ({ch['handle']})  |  {ch['subscribersText'] or '—'}  |  Mode: {snap['mode']}")
    print(f"Videos:  {tot['videoCount']} ({tot['shortsCount']} Shorts, {tot['longCount']} Long-form)  |  Total Views: {tot['totalViews']:,}")
    print("-" * 92)
    print(f"{'FMT':<6} {'PUBLISHED':<11} {'VIEWS':>7} {'LIKES':>6} {'AVG %':>7} {'SWIPE%':>7}  {'TITLE'}")
    print("-" * 92)
    for v in snap["videos"]:
        fmt = "SHORT" if v["format"] == "short" else "LONG"
        pub = v.get("publishDate") or "—"
        views = f"{v.get('views', 0):,}"
        likes = str(v["likes"]) if v.get("likes") is not None else "—"
        avg_p = f"{v['avgViewPct']:.1f}%" if v.get("avgViewPct") is not None else "—"
        swp = f"{v['viewedVsSwipedPct']:.1f}%" if v.get("viewedVsSwipedPct") is not None else "—"
        title = v["title"][:48]
        print(f"{fmt:<6} {pub:<11} {views:>7} {likes:>6} {avg_p:>7} {swp:>7}  {title}")
