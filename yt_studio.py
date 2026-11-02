#!/usr/bin/env python3
"""
mateai-youtube-mcp — Local YouTube Studio & Analytics Connector
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).

Supports two modes:
1. Public Snapshot Mode (zero config, stdlib only):
   Pulls public channel stats, Long-form videos, Shorts, view counts, and likes for any @handle.
2. Authenticated Studio Mode (OAuth2 via client_secret.json):
   Pulls private YouTube Analytics API v2 metrics (Avg % viewed, Engaged views, Viewed vs. swiped away,
   Watch time, Subscribers gained) and uploads private video drafts with thumbnails.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TOKEN_FILE = HERE / ".tokens" / "token.json"


def _resolve_default_client_secret() -> Path:
    direct = HERE / "client_secret.json"
    if direct.exists():
        return direct
    secret_dir = HERE / "google_auth_secret"
    if secret_dir.is_dir():
        matches = sorted(secret_dir.glob("client_secret*.json"))
        if matches:
            return matches[0]
    root_matches = sorted(HERE.glob("client_secret*.json"))
    if root_matches:
        return root_matches[0]
    return direct


DEFAULT_CLIENT_SECRET = _resolve_default_client_secret()
CACHE_FILE = HERE / "channel_snapshot.json"
REPORT_FILE = HERE / "report.html"
TEMPLATE_FILE = HERE / "report_template.html"

DEFAULT_HANDLE = "@mateai-c6m"
AUTHOR_ATTRIBUTION = "MateAI (https://www.youtube.com/@mateai-c6m)"

SCOPES_READONLY = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
SCOPES_WITH_UPLOAD = SCOPES_READONLY + [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _http_get(url: str) -> str:
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _extract_yt_initial_data(page_html: str) -> dict[str, Any]:
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", page_html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def fetch_video_public_details(video_id: str, is_short_hint: bool = False) -> dict[str, Any]:
    """Fetch public details for a single video or Short using watch page + oEmbed."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    html = _http_get(watch_url)

    title_m = re.search(r'"videoDetails":\{.*?"title":"((?:[^"\\]|\\.)*)"', html)
    title = json.loads(f'"{title_m.group(1)}"') if title_m else video_id

    views_m = re.search(r'"viewCount":"(\d+)"', html)
    views = int(views_m.group(1)) if views_m else 0

    len_m = re.search(r'"lengthSeconds":"(\d+)"', html)
    length_sec = int(len_m.group(1)) if len_m else 0

    pub_m = re.search(r'"publishDate":"([^"]+)"', html)
    publish_date = pub_m.group(1)[:10] if pub_m else ""

    short_desc_m = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html)
    description = json.loads(f'"{short_desc_m.group(1)}"') if short_desc_m else ""

    likes = None
    likes_m = re.search(r'"label":"([\d,]+) likes"', html)
    if likes_m:
        likes = int(likes_m.group(1).replace(",", ""))
    else:
        likes_m2 = re.search(r"like this video along with ([\d,]+) other", html)
        if likes_m2:
            likes = int(likes_m2.group(1).replace(",", "")) + 1

    is_short = is_short_hint or (0 < length_sec <= 180 and ("#Shorts" in description or is_short_hint))

    return {
        "videoId": video_id,
        "title": title,
        "format": "short" if is_short else "long",
        "publishDate": publish_date,
        "durationSec": length_sec,
        "views": views,
        "likes": likes,
        "comments": None,
        "engagedViews": None,
        "viewedVsSwipedPct": None,
        "avgViewDurationSec": None,
        "avgViewPct": None,
        "watchTimeMin": None,
        "subsGained": None,
        "url": f"https://www.youtube.com/shorts/{video_id}" if is_short else watch_url,
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "descriptionPreview": description[:220],
        "sourceMode": "public",
    }


def fetch_public_channel_snapshot(handle: str = DEFAULT_HANDLE) -> dict[str, Any]:
    """Fetch public channel metadata, videos, and Shorts without requiring OAuth."""
    clean_handle = handle if handle.startswith("@") else f"@{handle}"
    base_url = f"https://www.youtube.com/{clean_handle}"

    videos_html = _http_get(f"{base_url}/videos")
    shorts_html = _http_get(f"{base_url}/shorts")

    # Channel metadata from videos_html
    chan_title_m = re.search(r'<meta property="og:title" content="([^"]+)"', videos_html)
    channel_title = html_lib.unescape(chan_title_m.group(1)) if chan_title_m else clean_handle

    chan_desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', videos_html)
    channel_desc = html_lib.unescape(chan_desc_m.group(1)) if chan_desc_m else ""

    avatar_m = re.search(r'<meta property="og:image" content="([^"]+)"', videos_html)
    avatar_url = avatar_m.group(1) if avatar_m else ""

    subs_m = re.search(r'"subscriberCountText":\{"simpleText":"([^"]+)"\}', videos_html)
    subs_text = subs_m.group(1) if subs_m else "10 subscribers"

    # Extract video IDs in order of appearance
    long_ids: list[str] = []
    for vid in re.findall(r'"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})"', videos_html):
        if vid not in long_ids:
            long_ids.append(vid)
    if not long_ids:
        for vid in re.findall(r'"/watch\?v=([a-zA-Z0-9_-]{11})"', videos_html):
            if vid not in long_ids:
                long_ids.append(vid)

    short_ids: list[str] = []
    for vid in re.findall(r'"/shorts/([a-zA-Z0-9_-]{11})"', shorts_html):
        if vid not in short_ids:
            short_ids.append(vid)

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for vid in short_ids:
        if vid in seen:
            continue
        seen.add(vid)
        items.append(fetch_video_public_details(vid, is_short_hint=True))

    for vid in long_ids:
        if vid in seen:
            continue
        seen.add(vid)
        items.append(fetch_video_public_details(vid, is_short_hint=False))

    items.sort(key=lambda x: (x.get("publishDate") or "", x.get("views") or 0), reverse=True)

    total_views = sum(v.get("views", 0) or 0 for v in items)
    shorts_list = [v for v in items if v["format"] == "short"]
    long_list = [v for v in items if v["format"] == "long"]

    snapshot = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": "public",
        "channel": {
            "handle": clean_handle,
            "title": channel_title,
            "description": channel_desc,
            "subscribersText": subs_text,
            "avatarUrl": avatar_url,
            "url": base_url,
        },
        "totals": {
            "videoCount": len(items),
            "shortsCount": len(shorts_list),
            "longCount": len(long_list),
            "totalViews": total_views,
            "topVideo": max(items, key=lambda x: x.get("views", 0)) if items else None,
        },
        "videos": items,
        "attribution": AUTHOR_ATTRIBUTION,
    }
    return snapshot


# ---------------------------------------------------------------------------
# Authenticated OAuth2 YouTube Data v3 + YouTube Analytics v2 Mode
# ---------------------------------------------------------------------------

def get_oauth_credentials(
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
    upload_scope: bool = False,
    force_reauth: bool = False,
):
    """Load cached OAuth2 token or launch local browser flow if client_secret.json exists."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "Google API libraries not installed. Run:\n"
            "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
        ) from exc

    scopes = SCOPES_WITH_UPLOAD if upload_scope else SCOPES_READONLY
    creds = None

    if not force_reauth and TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), scopes)

    if not creds or not creds.valid:
        if not force_reauth and creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secret_path.exists():
                raise FileNotFoundError(
                    f"Missing OAuth credentials at {client_secret_path}.\n"
                    "Download an OAuth 2.0 Desktop client JSON from Google Cloud Console "
                    "and save it as client_secret.json (see README.md)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes)
            creds = flow.run_local_server(port=0, prompt="consent")

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        os.chmod(TOKEN_FILE, 0o600)

    return creds


def fetch_studio_channel_snapshot(
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
    days: int = 90,
) -> dict[str, Any]:
    """Fetch full private Studio metrics via YouTube Data API v3 + YouTube Analytics API v2."""
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=False)
    yt = build("youtube", "v3", credentials=creds)
    yta = build("youtubeAnalytics", "v2", credentials=creds)

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

    analytics_by_vid: dict[str, dict[str, Any]] = {}
    try:
        rep = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained",
            dimensions="video",
            maxResults=50,
            sort="-views",
        ).execute()
        headers = [h["name"] for h in rep.get("columnHeaders", [])]
        for row in rep.get("rows", []):
            row_dict = dict(zip(headers, row))
            analytics_by_vid[row_dict["video"]] = row_dict
    except Exception:
        # Fallback if engagedViews metric isn't supported for a specific date window
        rep = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained",
            dimensions="video",
            maxResults=50,
            sort="-views",
        ).execute()
        headers = [h["name"] for h in rep.get("columnHeaders", [])]
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
    shorts_list = [v for v in items if v["format"] == "short"]
    long_list = [v for v in items if v["format"] == "long"]

    return {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": "studio_oauth",
        "channel": {
            "handle": snippet.get("customUrl", DEFAULT_HANDLE),
            "title": snippet.get("title", "MateAI"),
            "description": snippet.get("description", ""),
            "subscribersText": f"{stats.get('subscriberCount', '0')} subscribers",
            "avatarUrl": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
            "url": f"https://www.youtube.com/{snippet.get('customUrl', DEFAULT_HANDLE)}",
        },
        "totals": {
            "videoCount": len(items),
            "shortsCount": len(shorts_list),
            "longCount": len(long_list),
            "totalViews": sum(v.get("views", 0) or 0 for v in items),
            "topVideo": max(items, key=lambda x: x.get("views", 0)) if items else None,
        },
        "videos": items,
        "attribution": AUTHOR_ATTRIBUTION,
    }


def _parse_iso_duration(iso_str: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_str or "")
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mins * 60 + s


# ---------------------------------------------------------------------------
# Upload Markdown Parser & Private Draft Uploader
# ---------------------------------------------------------------------------

def parse_upload_markdown(md_path: Path) -> dict[str, Any]:
    """Parse a MateAI upload markdown file (e.g. planning/gemini-4-carbon-upload.md)."""
    text = md_path.read_text(encoding="utf-8")

    def _extract_code_block_after(heading_pattern: str) -> str:
        pattern = rf"##\s+{heading_pattern}.*?\n```[^\n]*\n(.*?)\n```"
        m = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    title = _extract_code_block_after("Title")
    description = _extract_code_block_after("Description")
    tags_raw = _extract_code_block_after("Tags")
    pinned_comment = _extract_code_block_after("Pinned comment")

    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
    return {
        "title": title,
        "description": description,
        "tags": tags,
        "pinnedComment": pinned_comment,
        "sourceFile": str(md_path),
    }


def upload_private_draft(
    video_path: Path,
    spec_path: Path,
    thumbnail_path: Path | None = None,
    privacy_status: str = "private",
    publish_at: str | None = None,
    auto_post_comment: bool = False,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """Upload a rendered video + metadata as a Private Draft or Scheduled Upload to YouTube Studio."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    meta = parse_upload_markdown(spec_path)
    if not meta["title"]:
        raise ValueError(f"Could not find a '## Title' code block in {spec_path}")

    creds = get_oauth_credentials(client_secret_path, upload_scope=True)
    yt = build("youtube", "v3", credentials=creds)

    status_body: dict[str, Any] = {
        "privacyStatus": "private" if publish_at else privacy_status,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status_body["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": "28",  # Science & Technology
        },
        "status": status_body,
    }

    media = MediaFileUpload(str(video_path), chunksize=1024 * 1024 * 8, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = req.next_chunk()

    video_id = response["id"]
    thumb_uploaded = False
    if thumbnail_path and thumbnail_path.exists():
        try:
            yt.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path)),
            ).execute()
            thumb_uploaded = True
        except Exception:
            thumb_uploaded = False

    comment_id = None
    if auto_post_comment and meta.get("pinnedComment"):
        try:
            c_res = post_video_comment(video_id, meta["pinnedComment"], client_secret_path=client_secret_path)
            comment_id = c_res.get("commentId")
        except Exception:
            comment_id = None

    return {
        "videoId": video_id,
        "title": meta["title"],
        "privacyStatus": status_body["privacyStatus"],
        "scheduledPublishAt": publish_at,
        "studioEditUrl": f"https://studio.youtube.com/video/{video_id}/edit",
        "watchUrl": f"https://youtu.be/{video_id}",
        "thumbnailUploaded": thumb_uploaded,
        "commentPostedId": comment_id,
        "pinnedCommentText": meta["pinnedComment"],
    }


def update_video_metadata(
    video_id: str,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    privacy_status: str | None = None,
    publish_at: str | None = None,
    thumbnail_path: Path | None = None,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """Update title, description, tags, privacy, schedule time, or thumbnail of an existing video."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_oauth_credentials(client_secret_path, upload_scope=True)
    yt = build("youtube", "v3", credentials=creds)

    existing = yt.videos().list(part="snippet,status", id=video_id).execute()
    if not existing.get("items"):
        raise ValueError(f"Video not found: {video_id}")

    item = existing["items"][0]
    snippet = item["snippet"]
    status = item["status"]

    if title is not None:
        snippet["title"] = title
    if description is not None:
        snippet["description"] = description
    if tags is not None:
        snippet["tags"] = tags
    if privacy_status is not None:
        status["privacyStatus"] = privacy_status
    if publish_at is not None:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    updated = yt.videos().update(
        part="snippet,status",
        body={"id": video_id, "snippet": snippet, "status": status},
    ).execute()

    thumb_updated = False
    if thumbnail_path and thumbnail_path.exists():
        yt.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path)),
        ).execute()
        thumb_updated = True

    return {
        "videoId": video_id,
        "title": updated["snippet"]["title"],
        "privacyStatus": updated["status"].get("privacyStatus"),
        "publishAt": updated["status"].get("publishAt"),
        "thumbnailUpdated": thumb_updated,
        "studioEditUrl": f"https://studio.youtube.com/video/{video_id}/edit",
    }


def post_video_comment(
    video_id: str,
    text: str,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """Post a top-level comment on a video (ready to be pinned in Studio)."""
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=True)
    yt = build("youtube", "v3", credentials=creds)
    resp = yt.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": text}},
            }
        },
    ).execute()
    return {
        "commentId": resp["id"],
        "videoId": video_id,
        "text": text,
    }


# ---------------------------------------------------------------------------
# Shorts Experiment Markdown Table Generator
# ---------------------------------------------------------------------------

def build_shorts_experiment_markdown(snapshot: dict[str, Any]) -> str:
    """Format the Shorts performance table matching pipeline/explainer-short/README.md."""
    lines = [
        "| Video | Style | Published | Views | Viewed vs swiped | Avg % viewed | Engaged views | Subs gained |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    shorts = [v for v in snapshot.get("videos", []) if v.get("format") == "short"]
    for s in shorts:
        title = s.get("title", s["videoId"])
        pub = s.get("publishDate") or "published"
        views = f"{s.get('views', 0):,}"
        vvs = f"{s['viewedVsSwipedPct']:.1f}%" if s.get("viewedVsSwipedPct") is not None else "*(Studio OAuth)*"
        avp = f"{s['avgViewPct']:.1f}%" if s.get("avgViewPct") is not None else "*(Studio OAuth)*"
        eng = f"{s['engagedViews']:,}" if s.get("engagedViews") is not None else "*(Studio OAuth)*"
        subs = f"+{s['subsGained']}" if s.get("subsGained") is not None else "*(Studio OAuth)*"
        style = "C (Poster)" if "Carbon" in title or "Knocked" in title or "Acted" in title else "Grid"
        lines.append(f"| [{title}]({s['url']}) | {style} | {pub} | {views} | {vvs} | {avp} | {eng} | {subs} |")
    return "\n".join(lines)


def render_html_report(snapshot: dict[str, Any], out_path: Path = REPORT_FILE) -> Path:
    """Render interactive HTML dashboard from report_template.html."""
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    payload_json = json.dumps(snapshot, indent=2)
    rendered = template.replace("__SNAPSHOT_JSON__", payload_json)
    out_path.write_text(rendered, encoding="utf-8")
    return out_path


def get_best_snapshot(handle: str = DEFAULT_HANDLE, force_public: bool = False) -> dict[str, Any]:
    """Use Studio OAuth if token/client_secret is ready, otherwise fallback to Public Snapshot."""
    if not force_public and (TOKEN_FILE.exists() or DEFAULT_CLIENT_SECRET.exists()):
        try:
            snap = fetch_studio_channel_snapshot()
            CACHE_FILE.write_text(json.dumps(snap, indent=2), encoding="utf-8")
            return snap
        except Exception as exc:
            if not force_public:
                sys.stderr.write(f"[yt_studio] Studio OAuth unavailable ({exc}); using public snapshot.\n")

    snap = fetch_public_channel_snapshot(handle=handle)
    CACHE_FILE.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


def print_cli_summary(snap: dict[str, Any]) -> None:
    ch = snap["channel"]
    tot = snap["totals"]
    print(f"Channel: {ch['title']} ({ch['handle']})  |  {ch['subscribersText']}  |  Mode: {snap['mode']}")
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MateAI YouTube Studio & Analytics Connector (CLI + Dashboard)"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("snapshot", help="Fetch channel stats, print summary, and write report.html")
    p_snap.add_argument("--handle", default=DEFAULT_HANDLE, help="YouTube handle (default: @mateai-c6m)")
    p_snap.add_argument("--public", action="store_true", help="Force zero-config public scraping mode")
    p_snap.add_argument("--json", action="store_true", help="Print raw JSON to stdout")

    sub.add_parser("auth", help="Run one-time Google Cloud OAuth2 browser login")

    p_table = sub.add_parser("experiment-table", help="Print Markdown table for Shorts style experiments")
    p_table.add_argument("--handle", default=DEFAULT_HANDLE)

    p_up = sub.add_parser("upload-draft", help="Upload a video + markdown spec as a Private draft in Studio")
    p_up.add_argument("--video", required=True, type=Path, help="Path to MP4/MOV file")
    p_up.add_argument("--spec", required=True, type=Path, help="Path to upload markdown file")
    p_up.add_argument("--thumbnail", type=Path, help="Optional path to cover PNG/JPG")
    p_up.add_argument("--privacy", default="private", choices=["private", "unlisted"])

    args = parser.parse_args()
    cmd = args.cmd or "snapshot"

    if cmd == "auth":
        get_oauth_credentials(upload_scope=True, force_reauth=True)
        print(f"Authenticated! Token saved to {TOKEN_FILE}")
        return

    if cmd == "upload-draft":
        res = upload_private_draft(
            video_path=args.video,
            spec_path=args.spec,
            thumbnail_path=args.thumbnail,
            privacy_status=args.privacy,
        )
        print(json.dumps(res, indent=2))
        return

    if cmd == "experiment-table":
        snap = get_best_snapshot(handle=args.handle)
        print(build_shorts_experiment_markdown(snap))
        return

    # Default: snapshot
    handle = getattr(args, "handle", DEFAULT_HANDLE)
    force_public = getattr(args, "public", False)
    snap = get_best_snapshot(handle=handle, force_public=force_public)
    if TEMPLATE_FILE.exists():
        render_html_report(snap, REPORT_FILE)
    if getattr(args, "json", False):
        print(json.dumps(snap, indent=2))
    else:
        print_cli_summary(snap)
        if REPORT_FILE.exists():
            print(f"\nDashboard written to: {REPORT_FILE}")


if __name__ == "__main__":
    main()
