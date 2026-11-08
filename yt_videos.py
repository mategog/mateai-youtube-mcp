"""
mateai-youtube-mcp — Video upload, metadata update and top-level comment posting
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import datetime as dt
import re
import time
from pathlib import Path
from typing import Any

import yt_auth
import yt_common
from yt_auth import DEFAULT_CLIENT_SECRET


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


def _check_title_description(title: str | None, description: str | None) -> None:
    """YouTube rejects these with an unhelpful invalidTitle/invalidDescription error; catch them first."""
    for name, text in (("title", title), ("description", description)):
        if text and ("<" in text or ">" in text):
            raise ValueError(
                f"The {name} contains '<' or '>', which YouTube doesn't allow. "
                "Write it out instead, e.g. 'over 75%' instead of '>75%'."
            )
    if title and len(title) > 100:
        raise ValueError(f"The title is {len(title)} characters; YouTube allows at most 100.")
    if description and len(description.encode("utf-8")) > 5000:
        raise ValueError(
            f"The description is {len(description.encode('utf-8'))} bytes (UTF-8); YouTube allows at most 5000."
        )


# thumbnails.set docs: max 50MB, image/jpeg or image/png (the 2MB limit is the mobile Studio app's, not the API's).
_THUMBNAIL_MAX_BYTES = 50 * 1024 * 1024
_THUMBNAIL_SUFFIXES = (".jpg", ".jpeg", ".png")


def _check_thumbnail(path: Path | None) -> None:
    """Fail before any upload or update, instead of silently skipping or half-applying the thumbnail."""
    if path is None:
        return
    if not path.is_file():
        raise ValueError(f"Thumbnail file not found: {path}")
    if path.suffix.lower() not in _THUMBNAIL_SUFFIXES:
        raise ValueError(f"The thumbnail must be a JPG or PNG image; got '{path.suffix or path.name}'.")
    size = path.stat().st_size
    if size > _THUMBNAIL_MAX_BYTES:
        raise ValueError(f"The thumbnail is {size / 1024 / 1024:.1f} MB; YouTube allows at most 50 MB.")


def _build_update_changes(
    title: str | None,
    description: str | None,
    tags: list[str] | None,
    privacy_status: str | None,
    publish_at: str | None,
    contains_synthetic_media: bool | None,
) -> dict[str, dict[str, Any]]:
    """Only the `snippet`/`status` fields an update changes (a part is absent if untouched). Pure: shared by dry run and real update."""
    _check_title_description(title, description)
    if (privacy_status is not None or publish_at is not None) and contains_synthetic_media is None:
        # videos.list can't read the flag back, and a status update without it may reset it.
        raise ValueError(
            "Changing privacy_status or publish_at re-sends the video's status, which can reset its "
            "altered/synthetic media disclosure. Pass contains_synthetic_media explicitly (true or false)."
        )
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


def _wait_until_processed(yt: Any, video_id: str, polls: int = 60, poll_seconds: float = 5) -> bool:
    """thumbnails.set on a Short may not apply before processing succeeds (thumbnails.set docs). Waits up to ~5 min."""
    for attempt in range(polls):
        items = yt.videos().list(part="processingDetails", id=video_id).execute().get("items") or []
        status = items[0].get("processingDetails", {}).get("processingStatus") if items else None
        if status == "succeeded":
            return True
        if status in ("failed", "terminated"):
            return False
        if attempt < polls - 1:
            time.sleep(poll_seconds)
    return False


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

    _check_title_description(final_title, final_desc)
    _check_thumbnail(thumbnail_path)

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

    from googleapiclient.http import MediaFileUpload

    yt = yt_auth._youtube_client(client_secret_path)

    media = MediaFileUpload(str(video_path), chunksize=1024 * 1024 * 8, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = req.next_chunk()

    video_id = response["id"]
    # The video is already uploaded, so a failed thumbnail or comment must not raise; but say why.
    errors: dict[str, str] = {}
    thumb_uploaded = False
    if thumbnail_path:
        try:
            if _wait_until_processed(yt, video_id):
                yt.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_path)),
                ).execute()
                thumb_uploaded = True
            else:
                errors["thumbnailError"] = (
                    "YouTube hadn't finished processing the video, so the thumbnail was not set "
                    "(it may not stick on a Short before then). Set the cover later with yt_update_video."
                )
        except Exception as exc:
            errors["thumbnailError"] = str(exc)
            if yt_common.is_quota_error(exc):
                auto_post_comment = False  # out of quota: stop, don't try the comment

    comment_id = None
    if auto_post_comment and final_comment:
        try:
            c_res = post_video_comment(video_id, final_comment, client_secret_path=client_secret_path)
            comment_id = c_res.get("commentId")
        except Exception as exc:
            errors["commentError"] = str(exc)

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
        **errors,
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
    _check_thumbnail(thumbnail_path)

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

    from googleapiclient.http import MediaFileUpload

    yt = yt_auth._youtube_client(client_secret_path)

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

    # The metadata is already updated, so a failed thumbnail must not raise; but say why.
    errors: dict[str, str] = {}
    thumb_updated = False
    if thumbnail_path:
        try:
            yt.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path)),
            ).execute()
            thumb_updated = True
        except Exception as exc:
            errors["thumbnailError"] = str(exc)

    # videos.update echoes back only the parts that were sent; fall back to what videos.list returned.
    result_snippet = updated.get("snippet", snippet)
    result_status = updated.get("status", status)
    return {
        "videoId": video_id,
        "title": result_snippet["title"],
        "privacyStatus": result_status.get("privacyStatus"),
        "publishAt": result_status.get("publishAt"),
        "thumbnailUpdated": thumb_updated,
        "studioEditUrl": f"https://studio.youtube.com/video/{video_id}/edit",
        **errors,
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

    yt = yt_auth._youtube_client(client_secret_path)
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
