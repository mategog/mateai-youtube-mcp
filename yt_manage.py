"""
mateai-youtube-mcp — Channel management: list videos, read and reply to comments, delete a video
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yt_auth
from yt_auth import DEFAULT_CLIENT_SECRET


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
    yt = yt or yt_auth._youtube_client(client_secret_path, upload_scope=False)
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


def fetch_video_text(
    video_id: str,
    yt=None,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """The owner's view of one video's text and schedule: title, description, tags, privacy, publishAt.
    Works for private and scheduled videos. 1 quota unit."""
    yt = yt or yt_auth._youtube_client(client_secret_path, upload_scope=False)
    items = yt.videos().list(part="snippet,status", id=video_id).execute().get("items", [])
    if not items:
        raise ValueError(f"Video not found on the signed-in channel: {video_id}")
    sn, st = items[0]["snippet"], items[0]["status"]
    return {
        "title": sn.get("title", ""),
        "description": sn.get("description", ""),
        "tags": sn.get("tags", []),
        "privacyStatus": st.get("privacyStatus"),
        "publishAt": st.get("publishAt"),
    }


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
    yt = yt or yt_auth._youtube_client(client_secret_path)
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
    yt = yt or yt_auth._youtube_client(client_secret_path)
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
    yt = yt or yt_auth._youtube_client(client_secret_path)
    existing = yt.videos().list(part="snippet", id=video_id).execute()
    if not existing.get("items"):
        raise ValueError(f"Video not found: {video_id}")
    title = existing["items"][0]["snippet"]["title"]
    if confirm_title != title:
        raise ValueError(f"confirm_title does not match the video's title ({title!r}); nothing deleted.")
    yt.videos().delete(id=video_id).execute()
    return {"videoId": video_id, "deletedTitle": title}
