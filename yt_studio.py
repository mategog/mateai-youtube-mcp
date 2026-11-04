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
import contextlib
import datetime as dt
import html as html_lib
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# State (venv, tokens, OAuth secret, snapshot, report) lives in MATEAI_YT_HOME when set
# (the Claude Code plugin points it at ${CLAUDE_PLUGIN_DATA}), else next to this file.
STATE_DIR = Path(os.environ.get("MATEAI_YT_HOME") or HERE).expanduser()
for _sp in sorted((STATE_DIR / ".venv" / "lib").glob("python*/site-packages")):
    if str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

TOKEN_FILE = STATE_DIR / ".tokens" / "token.json"


def _resolve_default_client_secret() -> Path:
    direct = STATE_DIR / "client_secret.json"
    if direct.exists():
        return direct
    secret_dir = STATE_DIR / "google_auth_secret"
    if secret_dir.is_dir():
        matches = sorted(secret_dir.glob("client_secret*.json"))
        if matches:
            return matches[0]
    root_matches = sorted(STATE_DIR.glob("client_secret*.json"))
    if root_matches:
        return root_matches[0]
    return direct


DEFAULT_CLIENT_SECRET = _resolve_default_client_secret()
CACHE_FILE = STATE_DIR / "channel_snapshot.json"
REPORT_FILE = STATE_DIR / "report.html"
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

# Public page scraping is opt-in: the default path is the official YouTube APIs via OAuth.
# Enable it per call (force_public / --public) or always with MATEAI_YT_PUBLIC_SCRAPE=1.
PUBLIC_SCRAPE_ENV = os.environ.get("MATEAI_YT_PUBLIC_SCRAPE") == "1"
SCRAPE_DISABLED_MSG = (
    "No YouTube OAuth credentials found, and public page scraping is off by default. "
    "Run `python3 yt_studio.py setup` (with MATEAI_YT_HOME set to the plugin data folder) to connect "
    "your channel through the official YouTube APIs, or opt in to public scraping with "
    "force_public=true / --public, or MATEAI_YT_PUBLIC_SCRAPE=1."
)

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

def _saved_scopes(token_file: Path) -> list[str]:
    scopes = json.loads(token_file.read_text(encoding="utf-8")).get("scopes") or []
    return scopes.split(" ") if isinstance(scopes, str) else list(scopes)


def _expired_marker() -> Path:
    """`.tokens/expired`: left by a failed refresh so /yt-setup knows the saved login is dead."""
    return TOKEN_FILE.with_name("expired")


def get_oauth_credentials(
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
    upload_scope: bool = False,
    force_reauth: bool = False,
):
    """Load cached OAuth2 token or launch local browser flow if client_secret.json exists."""
    try:
        from google.auth.exceptions import RefreshError
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

    covers_request = True
    if not force_reauth and TOKEN_FILE.exists():
        # Load with the union of what the file says was granted and what this call needs, so
        # saving never narrows the file's scopes (a read call used to overwrite them).
        granted = _saved_scopes(TOKEN_FILE)
        covers_request = set(scopes) <= set(granted)
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), granted + [s for s in scopes if s not in granted]
        )

    # A cached access token is only reusable if the file says it covers this call's scopes.
    if not creds or not creds.valid or not covers_request:
        if not force_reauth and creds and (creds.expired or not covers_request) and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                with contextlib.suppress(OSError):
                    _expired_marker().write_text("", encoding="utf-8")
                raise RuntimeError(
                    "Your YouTube login expired or was revoked, so Google refused to renew it. "
                    "Sign in again: type /yt-setup in Claude Code, or run "
                    "`python3 yt_studio.py setup`. (Google ends logins after 7 days for apps in "
                    f"'Testing' mode.)\nDetails: {exc}"
                ) from exc
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
        with contextlib.suppress(OSError):
            _expired_marker().unlink(missing_ok=True)

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


def _describe_publish_at(publish_at: str | None) -> tuple[str | None, list[str]]:
    """Return (local-time text, warnings) for an ISO 8601 `publish_at`, for dry runs."""
    if not publish_at:
        return None, []
    try:
        when = dt.datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
    except ValueError:
        return None, [f"publish_at {publish_at!r} is not ISO 8601 (e.g. 2026-11-05T20:00:00+01:00)."]
    if when.tzinfo is None:
        return None, ["publish_at has no timezone offset (add e.g. +01:00 or Z); YouTube may reject it."]
    warnings = []
    if when <= dt.datetime.now(dt.timezone.utc):
        warnings.append("publish_at is in the past; YouTube will reject it or publish right away.")
    return when.astimezone().strftime("%a %Y-%m-%d %H:%M %Z"), warnings


def _build_upload_body(
    title: str,
    description: str,
    tags: list[str],
    category_id: str,
    language: str,
    made_for_kids: bool,
    contains_synthetic_media: bool,
    privacy_status: str,
    publish_at: str | None,
) -> dict[str, Any]:
    """The `videos.insert` body. Pure: shared by the dry run and the real upload. A schedule forces private."""
    status: dict[str, Any] = {
        "privacyStatus": "private" if publish_at else privacy_status,
        "selfDeclaredMadeForKids": made_for_kids,
        "containsSyntheticMedia": contains_synthetic_media,
    }
    if publish_at:
        status["publishAt"] = publish_at
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,  # 28 = Science & Technology
            "defaultLanguage": language,
            "defaultAudioLanguage": language,
        },
        "status": status,
    }


def _build_update_changes(
    title: str | None,
    description: str | None,
    tags: list[str] | None,
    privacy_status: str | None,
    publish_at: str | None,
    contains_synthetic_media: bool | None,
) -> dict[str, dict[str, Any]]:
    """Only the `snippet`/`status` fields an update changes (a part is absent if untouched). Pure: shared by dry run and real update."""
    snippet = {
        key: value
        for key, value in (("title", title), ("description", description), ("tags", tags))
        if value is not None
    }
    status: dict[str, Any] = {}
    if privacy_status is not None:
        status["privacyStatus"] = privacy_status
    if publish_at is not None:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    if contains_synthetic_media is not None:
        status["containsSyntheticMedia"] = contains_synthetic_media
    return {name: fields for name, fields in (("snippet", snippet), ("status", status)) if fields}


def upload_private_draft(
    video_path: Path,
    spec_path: Path | None = None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    hashtags: list[str] | None = None,
    pinned_comment: str | None = None,
    category_id: str = "28",
    language: str = "en",
    made_for_kids: bool = False,
    contains_synthetic_media: bool = False,
    thumbnail_path: Path | None = None,
    privacy_status: str = "private",
    publish_at: str | None = None,
    auto_post_comment: bool = False,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upload a video + full YouTube Studio setup (title, description, hashtags, tags, language, synthetic flag, thumbnail, schedule).

    With `dry_run=True`, validate the inputs and return what would be sent, without signing in or uploading.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    meta = (
        parse_upload_markdown(spec_path)
        if (spec_path and spec_path.exists())
        else {"title": "", "description": "", "tags": [], "pinnedComment": ""}
    )

    final_title = (title or meta["title"]).strip()
    if not final_title:
        raise ValueError("Video title is required (pass `title` or a `spec_path` with a `## Title` block).")

    final_desc = (description if description is not None else meta["description"]).strip()
    if hashtags:
        clean_tags = [h if h.startswith("#") else f"#{h}" for h in hashtags]
        hashtag_line = " ".join(clean_tags)
        if hashtag_line not in final_desc:
            final_desc = f"{final_desc}\n\n{hashtag_line}".strip()

    final_tags = tags if tags is not None else meta["tags"]
    final_comment = pinned_comment if pinned_comment is not None else meta["pinnedComment"]

    body = _build_upload_body(
        final_title, final_desc, final_tags, category_id, language,
        made_for_kids, contains_synthetic_media, privacy_status, publish_at,
    )

    if dry_run:
        publish_local, warnings = _describe_publish_at(publish_at)
        return {
            "dryRun": True,
            "message": "Nothing was uploaded.",
            "videoPath": str(video_path),
            "videoSizeMB": round(video_path.stat().st_size / 1_000_000, 1),
            "title": body["snippet"]["title"],
            "description": body["snippet"]["description"],
            "tags": body["snippet"]["tags"],
            "privacyStatus": body["status"]["privacyStatus"],
            "scheduledPublishAt": publish_at,
            "scheduledPublishAtLocal": publish_local,
            "language": body["snippet"]["defaultLanguage"],
            "categoryId": body["snippet"]["categoryId"],
            "madeForKids": body["status"]["selfDeclaredMadeForKids"],
            "containsSyntheticMedia": body["status"]["containsSyntheticMedia"],
            "thumbnailPath": str(thumbnail_path) if thumbnail_path else None,
            "thumbnailFound": bool(thumbnail_path and thumbnail_path.exists()),
            "pinnedCommentText": final_comment,
            "willPostComment": bool(auto_post_comment and final_comment),
            "warnings": warnings,
        }

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_oauth_credentials(client_secret_path, upload_scope=True)
    yt = build("youtube", "v3", credentials=creds)

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
    if auto_post_comment and final_comment:
        try:
            c_res = post_video_comment(video_id, final_comment, client_secret_path=client_secret_path)
            comment_id = c_res.get("commentId")
        except Exception:
            comment_id = None

    return {
        "videoId": video_id,
        "title": final_title,
        "privacyStatus": body["status"]["privacyStatus"],
        "scheduledPublishAt": publish_at,
        "language": language,
        "categoryId": category_id,
        "madeForKids": made_for_kids,
        "containsSyntheticMedia": contains_synthetic_media,
        "tagsCount": len(final_tags),
        "studioEditUrl": f"https://studio.youtube.com/video/{video_id}/edit",
        "watchUrl": f"https://youtu.be/{video_id}",
        "thumbnailUploaded": thumb_uploaded,
        "commentPostedId": comment_id,
        "pinnedCommentText": final_comment,
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
    dry_run: bool = False,
    contains_synthetic_media: bool | None = None,
) -> dict[str, Any]:
    """Update title, description, tags, privacy, schedule time, synthetic-media flag, or thumbnail of an existing video.

    Only the parts that actually change are sent to `videos.update`; in particular `status` is not re-sent
    for title/description/tag/thumbnail edits, because `videos.list` does not return `containsSyntheticMedia`.

    With `dry_run=True`, return the changes that would be applied, without signing in or changing anything.
    """
    changes = _build_update_changes(
        title, description, tags, privacy_status, publish_at, contains_synthetic_media)

    if dry_run:
        publish_local, warnings = _describe_publish_at(publish_at)
        would_change = {**changes.get("snippet", {}), **changes.get("status", {})}
        if thumbnail_path:
            would_change["thumbnailPath"] = str(thumbnail_path)
        return {
            "dryRun": True,
            "message": "Nothing was changed.",
            "videoId": video_id,
            "wouldChange": would_change,
            "scheduledPublishAtLocal": publish_local,
            "thumbnailFound": bool(thumbnail_path and thumbnail_path.exists()),
            "warnings": warnings,
        }

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

    body: dict[str, Any] = {"id": video_id}
    if "snippet" in changes:
        snippet.update(changes["snippet"])
        body["snippet"] = snippet
    if "status" in changes:
        status.update(changes["status"])
        body["status"] = status
    parts = [name for name in ("snippet", "status") if name in body]

    # Nothing to change (e.g. thumbnail only): skip videos.update so no part is re-sent.
    updated = (
        yt.videos().update(part=",".join(parts), body=body).execute()
        if parts else {"snippet": snippet, "status": status}
    )

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
    dry_run: bool = False,
) -> dict[str, Any]:
    """Post a top-level comment on a video (ready to be pinned in Studio). `dry_run=True` posts nothing."""
    if dry_run:
        return {"dryRun": True, "message": "Nothing was posted.", "videoId": video_id, "text": text}

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


def _youtube_client(client_secret_path: Path = DEFAULT_CLIENT_SECRET):
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=True)
    return build("youtube", "v3", credentials=creds)


def list_channel_videos(
    query: str | None = None,
    limit: int = 25,
    yt=None,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """List the authenticated channel's uploads (private/unlisted included), newest first.

    `query` is a case-insensitive substring match on title or description, applied locally
    (search.list costs 100 quota units; paging the uploads playlist costs ~2 per 50 videos).
    """
    yt = yt or _youtube_client(client_secret_path)
    channel = yt.channels().list(part="contentDetails", mine=True).execute()
    uploads = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    needle = (query or "").lower()
    videos: list[dict[str, Any]] = []
    page_token = None
    while len(videos) < limit:
        page = yt.playlistItems().list(
            part="contentDetails", playlistId=uploads, maxResults=50, pageToken=page_token
        ).execute()
        ids = [i["contentDetails"]["videoId"] for i in page.get("items", [])]
        if ids:
            details = yt.videos().list(part="snippet,status,statistics", id=",".join(ids)).execute()
            for v in details.get("items", []):
                sn = v["snippet"]
                if needle and needle not in f"{sn['title']}\n{sn.get('description', '')}".lower():
                    continue
                videos.append({
                    "videoId": v["id"],
                    "title": sn["title"],
                    "publishedAt": sn.get("publishedAt"),
                    "privacyStatus": v["status"].get("privacyStatus"),
                    "publishAt": v["status"].get("publishAt"),
                    "views": int(v.get("statistics", {}).get("viewCount", 0)),
                    "url": f"https://www.youtube.com/watch?v={v['id']}",
                })
        page_token = page.get("nextPageToken")
        if not page_token:
            break
    return {"videos": videos[:limit]}


def list_video_comments(
    video_id: str,
    limit: int = 20,
    order: str = "time",
    yt=None,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """Read top-level comment threads on a video (single page, max 100). Each thread carries
    replyCount plus the first few replies; the API does not inline more than ~5."""
    if order not in ("time", "relevance"):
        raise ValueError("order must be 'time' or 'relevance'")
    yt = yt or _youtube_client(client_secret_path)
    resp = yt.commentThreads().list(
        part="snippet,replies",
        videoId=video_id,
        maxResults=max(1, min(limit, 100)),
        order=order,
        textFormat="plainText",
    ).execute()
    comments = []
    for t in resp.get("items", []):
        top = t["snippet"]["topLevelComment"]
        sn = top["snippet"]
        comments.append({
            "commentId": top["id"],
            "author": sn.get("authorDisplayName"),
            "text": sn.get("textDisplay"),
            "likes": sn.get("likeCount", 0),
            "publishedAt": sn.get("publishedAt"),
            "replyCount": t["snippet"].get("totalReplyCount", 0),
            "replies": [
                {
                    "commentId": r["id"],
                    "author": r["snippet"].get("authorDisplayName"),
                    "text": r["snippet"].get("textDisplay"),
                    "publishedAt": r["snippet"].get("publishedAt"),
                }
                for r in t.get("replies", {}).get("comments", [])
            ],
        })
    return {"videoId": video_id, "comments": comments}


def reply_to_comment(
    parent_id: str,
    text: str,
    yt=None,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """Reply publicly to a top-level comment (parent_id is a commentId from list_video_comments)."""
    yt = yt or _youtube_client(client_secret_path)
    resp = yt.comments().insert(
        part="snippet",
        body={"snippet": {"parentId": parent_id, "textOriginal": text}},
    ).execute()
    return {"commentId": resp["id"], "parentId": parent_id, "text": text}


def delete_video(
    video_id: str,
    confirm_title: str,
    yt=None,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """Permanently delete a video. Refuses unless confirm_title equals the video's current title."""
    yt = yt or _youtube_client(client_secret_path)
    existing = yt.videos().list(part="snippet", id=video_id).execute()
    if not existing.get("items"):
        raise ValueError(f"Video not found: {video_id}")
    title = existing["items"][0]["snippet"]["title"]
    if confirm_title != title:
        raise ValueError(f"confirm_title does not match the video's title ({title!r}); nothing deleted.")
    yt.videos().delete(id=video_id).execute()
    return {"videoId": video_id, "deletedTitle": title}


def fetch_video_retention_diagnosis(
    video_id: str,
    words_or_script_path: Path | None = None,
    days: int = 365,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """
    Pull the 100-point audience retention curve (audienceWatchRatio + relativeRetentionPerformance),
    traffic sources, and cross-reference steepest drop-off timestamps against spoken words if available.
    """
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=False)
    yt = build("youtube", "v3", credentials=creds)
    yta = build("youtubeAnalytics", "v2", credentials=creds)

    v_resp = yt.videos().list(part="snippet,contentDetails,statistics", id=video_id).execute()
    if not v_resp.get("items"):
        raise ValueError(f"Video not found: {video_id}")
    v_item = v_resp["items"][0]
    title = v_item["snippet"]["title"]
    dur_sec = _parse_iso_duration(v_item["contentDetails"].get("duration", "PT0S"))

    end_date = dt.date.today().isoformat()
    start_date = (dt.date.today() - dt.timedelta(days=days)).isoformat()

    # 1. Traffic sources for this video
    traffic_sources: list[dict[str, Any]] = []
    try:
        ts_rep = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched",
            dimensions="insightTrafficSourceType",
            filters=f"video=={video_id}",
            sort="-views",
        ).execute()
        for r in ts_rep.get("rows", []):
            traffic_sources.append({
                "sourceType": r[0],
                "views": int(r[1]),
                "watchTimeMin": round(float(r[2]), 1),
            })
    except Exception:
        pass

    # 2. 100-point Audience Retention curve
    curve_rows: list[list[float]] = []
    try:
        rc_rep = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
        ).execute()
        curve_rows = rc_rep.get("rows", [])
    except Exception:
        curve_rows = []

    # Optional: load word timings from words.js / json if provided
    timed_words: list[dict[str, Any]] = []
    if words_or_script_path and words_or_script_path.exists():
        raw_txt = words_or_script_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\[.*\]", raw_txt, flags=re.DOTALL)
        if m:
            try:
                timed_words = json.loads(m.group(0))
            except Exception:
                timed_words = []

    def _spoken_around(sec: float, window: float = 5.0) -> str:
        if not timed_words:
            return ""
        tokens = [
            str(w.get("w", ""))
            for w in timed_words
            if isinstance(w, dict) and (sec - 2.0) <= float(w.get("s", -999)) <= (sec + window)
        ]
        return " ".join(tokens).strip()

    checkpoints: dict[str, Any] = {}
    steepest_drops: list[dict[str, Any]] = []

    if curve_rows and dur_sec > 0:
        for pct_target, label in [(0.03, "hook_3pct"), (0.10, "10pct"), (0.25, "25pct"), (0.50, "50pct"), (0.75, "75pct"), (1.00, "100pct")]:
            closest = min(curve_rows, key=lambda r: abs(float(r[0]) - pct_target))
            sec = int(round(float(closest[0]) * dur_sec))
            checkpoints[label] = {
                "timestampSec": sec,
                "timestampFmt": f"{sec // 60}:{sec % 60:02d}",
                "watchingPct": round(float(closest[1]) * 100, 1),
                "youtubePeerPercentile": round(float(closest[2]) * 100, 1),
            }

        diffs = []
        for i in range(1, len(curve_rows)):
            prev_r = float(curve_rows[i - 1][1])
            curr_r = float(curve_rows[i][1])
            delta = curr_r - prev_r
            ratio_pt = float(curve_rows[i][0])
            sec = int(round(ratio_pt * dur_sec))
            diffs.append({
                "timestampSec": sec,
                "timestampFmt": f"{sec // 60}:{sec % 60:02d}",
                "videoProgressPct": int(round(ratio_pt * 100)),
                "beforeWatchingPct": round(prev_r * 100, 1),
                "afterWatchingPct": round(curr_r * 100, 1),
                "dropPctPoints": round(delta * 100, 1),
                "youtubePeerPercentile": round(float(curve_rows[i][2]) * 100, 1),
                "spokenWordsAtCliff": _spoken_around(sec),
            })
        diffs.sort(key=lambda x: x["dropPctPoints"])
        steepest_drops = diffs[:5]

    return {
        "videoId": video_id,
        "title": title,
        "durationSec": dur_sec,
        "durationFmt": f"{dur_sec // 60}:{dur_sec % 60:02d}",
        "trafficSources": traffic_sources,
        "retentionCheckpoints": checkpoints,
        "steepestDropOffCliffs": steepest_drops,
        "hasRetentionCurve": bool(curve_rows),
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
    """Use Studio OAuth when configured; scrape public pages only when explicitly opted in."""
    allow_scrape = force_public or PUBLIC_SCRAPE_ENV
    if not force_public and (TOKEN_FILE.exists() or DEFAULT_CLIENT_SECRET.exists()):
        try:
            snap = fetch_studio_channel_snapshot()
            CACHE_FILE.write_text(json.dumps(snap, indent=2), encoding="utf-8")
            return snap
        except Exception as exc:
            if not allow_scrape:
                raise
            sys.stderr.write(f"[yt_studio] Studio OAuth unavailable ({exc}); using public snapshot.\n")

    if not allow_scrape:
        raise RuntimeError(SCRAPE_DISABLED_MSG)
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


def run_interactive_setup_wizard() -> None:
    """Zero-friction guided setup: auto-installs .venv, enables APIs, watches ~/Downloads for JSON, and logs in."""
    import shutil
    import subprocess
    import time
    import webbrowser

    print("=" * 72)
    print("  MateAI YouTube Studio MCP — Guided 1-Command Setup Wizard")
    print("=" * 72)

    # Step 1: Ensure .venv and Google API client packages exist
    venv_py = STATE_DIR / ".venv" / "bin" / "python"
    if not venv_py.exists():
        print("\n[1/4] Creating local Python virtualenv (.venv) and installing Google API SDK...")
        subprocess.run([sys.executable, "-m", "venv", str(STATE_DIR / ".venv")], check=True)
        subprocess.run([str(STATE_DIR / ".venv" / "bin" / "pip"), "install", "-q", "-r", str(HERE / "requirements.txt")], check=True)
        for sp in sorted((STATE_DIR / ".venv" / "lib").glob("python*/site-packages")):
            if str(sp) not in sys.path:
                sys.path.insert(0, str(sp))
    else:
        print("\n[1/4] Python virtualenv (.venv) is ready.")

    # Step 2: Enable YouTube Data API v3 & YouTube Analytics API
    print("\n[2/4] Enabling YouTube Data API v3 & YouTube Analytics API...")
    gcloud_bin = shutil.which("gcloud")
    apis_enabled_via_cli = False
    if gcloud_bin:
        try:
            proj = subprocess.check_output([gcloud_bin, "config", "get-value", "project"], text=True, stderr=subprocess.DEVNULL).strip()
            if proj and proj != "(unset)":
                print(f"      Found active gcloud project '{proj}'. Enabling YouTube APIs automatically...")
                res = subprocess.run(
                    [gcloud_bin, "services", "enable", "youtube.googleapis.com", "youtubeanalytics.googleapis.com"],
                     capture_output=True, text=True
                )
                if res.returncode == 0:
                    print("      ✓ Enabled youtube.googleapis.com and youtubeanalytics.googleapis.com via gcloud!")
                    apis_enabled_via_cli = True
        except Exception:
            pass

    if not apis_enabled_via_cli:
        print("      Opening direct 1-click API enablement pages in your browser...")
        webbrowser.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com")
        webbrowser.open("https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com")

    # Step 3: Check or watch for client_secret.json
    secret_dir = STATE_DIR / "google_auth_secret"
    secret_dir.mkdir(parents=True, exist_ok=True)
    secret_path = _resolve_default_client_secret()

    if not secret_path.exists():
        print("\n[3/4] Waiting for your Desktop OAuth JSON file...")
        print("      1. Add your YouTube email under 'Test users': https://console.cloud.google.com/auth/audience")
        print("      2. Create a 'Desktop app' OAuth client & click 'Download JSON': https://console.cloud.google.com/auth/clients/create")
        webbrowser.open("https://console.cloud.google.com/auth/audience")
        webbrowser.open("https://console.cloud.google.com/auth/clients/create")

        downloads = Path.home() / "Downloads"
        desktop = Path.home() / "Desktop"
        print(f"\n      👀 Watching ~/Downloads and {secret_dir} for client_secret*.json (Ctrl+C to cancel)...")
        found_file: Path | None = None
        while not found_file:
            for folder in (secret_dir, STATE_DIR, downloads, desktop):
                if not folder.exists():
                    continue
                matches = sorted(folder.glob("client_secret*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                if matches:
                    found_file = matches[0]
                    break
            if not found_file:
                time.sleep(1.0)

        target = secret_dir / "client_secret.json"
        if found_file.resolve() != target.resolve():
            shutil.copy2(found_file, target)
        os.chmod(target, 0o600)
        secret_path = target
        print(f"      ✓ Auto-imported {found_file.name} -> {target} (mode 0600)")
    else:
        print(f"\n[3/4] Found existing OAuth client secret: {secret_path.name}")

    # Step 4: Launch OAuth browser login & pull live Studio snapshot
    print("\n[4/4] Launching Google account & YouTube channel selector in your browser...")
    get_oauth_credentials(client_secret_path=secret_path, upload_scope=True, force_reauth=True)
    snap = fetch_studio_channel_snapshot(client_secret_path=secret_path)
    CACHE_FILE.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    if TEMPLATE_FILE.exists():
        render_html_report(snap, REPORT_FILE)
        webbrowser.open(REPORT_FILE.as_uri())
    print("\n✓ Setup complete! Live Studio snapshot:")
    print_cli_summary(snap)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MateAI YouTube Studio & Analytics Connector (CLI + Dashboard)"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("snapshot", help="Fetch channel stats, print summary, and write report.html")
    p_snap.add_argument("--handle", default=DEFAULT_HANDLE, help="YouTube handle (default: @mateai-c6m)")
    p_snap.add_argument("--public", action="store_true", help="Force zero-config public scraping mode")
    p_snap.add_argument("--json", action="store_true", help="Print raw JSON to stdout")

    sub.add_parser("setup", help="Interactive 1-command wizard: auto-watches ~/Downloads for OAuth JSON & logs in")
    sub.add_parser("auth", help="Run one-time Google Cloud OAuth2 browser login")

    p_table = sub.add_parser("experiment-table", help="Print Markdown table for Shorts style experiments")
    p_table.add_argument("--handle", default=DEFAULT_HANDLE)

    p_up = sub.add_parser("upload-draft", help="Upload & configure a video/Short in Studio (draft or scheduled)")
    p_up.add_argument("--video", required=True, type=Path, help="Path to MP4/MOV file")
    p_up.add_argument("--spec", type=Path, help="Optional path to upload markdown file")
    p_up.add_argument("--title", help="Video title (overrides spec)")
    p_up.add_argument("--description", help="Video description (overrides spec)")
    p_up.add_argument("--tags", help="Comma-separated SEO tags (overrides spec)")
    p_up.add_argument("--hashtags", help="Comma-separated hashtags, e.g. '#AINews,#Shorts'")
    p_up.add_argument("--comment", help="Pinned comment text to post")
    p_up.add_argument("--thumbnail", type=Path, help="Optional path to cover PNG/JPG")
    p_up.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    p_up.add_argument("--publish-at", help="ISO 8601 schedule time, e.g. '2026-11-04T18:00:00+01:00'")
    p_up.add_argument("--synthetic", action="store_true", help="Set altered/synthetic media disclosure flag")
    p_up.add_argument("--auto-comment", action="store_true", help="Automatically post the top-level comment")

    args = parser.parse_args()
    cmd = args.cmd or "snapshot"

    if cmd == "setup":
        run_interactive_setup_wizard()
        return

    if cmd == "auth":
        get_oauth_credentials(upload_scope=True, force_reauth=True)
        print(f"Authenticated! Token saved to {TOKEN_FILE}")
        return

    if cmd == "upload-draft":
        res = upload_private_draft(
            video_path=args.video,
            spec_path=args.spec,
            title=args.title,
            description=args.description,
            tags=[t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None,
            hashtags=[h.strip() for h in args.hashtags.split(",") if h.strip()] if args.hashtags else None,
            pinned_comment=args.comment,
            thumbnail_path=args.thumbnail,
            privacy_status=args.privacy,
            publish_at=args.publish_at,
            contains_synthetic_media=args.synthetic,
            auto_post_comment=args.auto_comment,
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
