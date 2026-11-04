"""
mateai-youtube-mcp — Public (no-OAuth) channel and video page scraping
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import html as html_lib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import yt_common
from yt_common import DEFAULT_HANDLE


def _extract_yt_initial_data(page_html: str) -> dict[str, Any]:
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", page_html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except ValueError:
        return {}


def fetch_video_public_details(video_id: str, is_short_hint: bool = False) -> dict[str, Any]:
    """Fetch public details for a single video or Short using watch page + oEmbed."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    html = yt_common._http_get(watch_url)

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

    is_short = is_short_hint or (0 < length_sec <= 180 and "#Shorts" in description)

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


def fetch_public_channel_snapshot(handle: str = DEFAULT_HANDLE) -> yt_common.Snapshot:
    """Fetch public channel metadata, videos, and Shorts without requiring OAuth."""
    clean_handle = handle if handle.startswith("@") else f"@{handle}"
    base_url = f"https://www.youtube.com/{clean_handle}"

    videos_html = yt_common._http_get(f"{base_url}/videos")
    shorts_html = yt_common._http_get(f"{base_url}/shorts")

    # Channel metadata from videos_html
    chan_title_m = re.search(r'<meta property="og:title" content="([^"]+)"', videos_html)
    channel_title = html_lib.unescape(chan_title_m.group(1)) if chan_title_m else clean_handle

    chan_desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', videos_html)
    channel_desc = html_lib.unescape(chan_desc_m.group(1)) if chan_desc_m else ""

    avatar_m = re.search(r'<meta property="og:image" content="([^"]+)"', videos_html)
    avatar_url = avatar_m.group(1) if avatar_m else ""

    subs_m = re.search(r'"subscriberCountText":\{"simpleText":"([^"]+)"\}', videos_html)
    subs_text = subs_m.group(1) if subs_m else None  # unknown: never invent a count

    # Extract video IDs in order of appearance
    long_ids = list(dict.fromkeys(re.findall(r'"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})"', videos_html)))
    if not long_ids:
        long_ids = list(dict.fromkeys(re.findall(r'"/watch\?v=([a-zA-Z0-9_-]{11})"', videos_html)))
    short_ids = list(dict.fromkeys(re.findall(r'"/shorts/([a-zA-Z0-9_-]{11})"', shorts_html)))

    # Shorts first; a video listed on both pages counts once, as a Short.
    wanted = {**{vid: True for vid in short_ids}, **{vid: False for vid in long_ids if vid not in short_ids}}
    # One page fetch per video: run them side by side. map() keeps the order, and the first failure raises as before.
    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(lambda kv: fetch_video_public_details(kv[0], is_short_hint=kv[1]), wanted.items()))

    items.sort(key=lambda x: (x.get("publishDate") or "", x.get("views") or 0), reverse=True)

    return yt_common.snapshot_envelope(
        "public",
        {
            "handle": clean_handle,
            "title": channel_title,
            "description": channel_desc,
            "subscribersText": subs_text,
            "avatarUrl": avatar_url,
            "url": base_url,
        },
        items,
        youtube_counts=True,
    )
