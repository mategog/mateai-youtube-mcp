#!/usr/bin/env python3
"""
mateai-youtube-mcp — Model Context Protocol (MCP) Server for Antigravity & Claude Code
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

from tiktok_studio import (
    TIKTOK_CACHE_FILE,
    build_cross_platform_table,
    fetch_tiktok_snapshot,
    upload_tiktok_inbox_draft,
)
from yt_studio import (
    AUTHOR_ATTRIBUTION,
    DEFAULT_HANDLE,
    REPORT_FILE,
    build_shorts_experiment_markdown,
    delete_video,
    fetch_video_public_details,
    fetch_video_retention_diagnosis,
    get_best_snapshot,
    list_channel_videos,
    list_video_comments,
    PUBLIC_SCRAPE_ENV,
    post_video_comment,
    render_html_report,
    reply_to_comment,
    update_video_metadata,
    upload_private_draft,
)

SERVER_INFO = {
    "name": "mateai-youtube-mcp",
    "version": "1.0.1",
    "author": AUTHOR_ATTRIBUTION,
}

SERVER_INSTRUCTIONS = (
    "Self-hosted YouTube Studio & Analytics MCP server. "
    "Use yt_channel_snapshot and yt_shorts_experiment_table to inspect channel performance and render report.html. "
    "Use yt_video_details to diagnose 100-point audience retention curves, drop-off cliffs, and traffic sources for a 11-char video_id. "
    "Use yt_upload_draft, yt_update_video, and yt_post_comment to upload/schedule videos, update metadata/thumbnails, and post comments in YouTube Studio. "
    "Use yt_list_videos to find video IDs, yt_list_comments and yt_reply_comment to read and answer comments, "
    "and yt_delete_video (irreversible, needs the exact title) to remove a video; prefer yt_update_video with privacy_status to hide one."
)

TOOLS = [
    {
        "name": "yt_channel_snapshot",
        "description": (
            "Fetch live YouTube channel statistics, recent long-form videos, and Shorts metrics, and write an updated "
            "local report.html dashboard and channel_snapshot.json cache on disk. "
            "When YouTube OAuth2 credentials are present (and force_public is false), queries YouTube Data API v3 (~3 quota units) "
            "and YouTube Analytics API v2 for private owner metrics (averageViewPercentage, swipedAwayRate, engagedViews, "
            "estimatedMinutesWatched, subscribersGained); public page scraping is opt-in only (force_public=true or MATEAI_YT_PUBLIC_SCRAPE=1); without OAuth or opt-in it returns setup instructions. "
            "Overwrites report.html idempotently on each run."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "pattern": "^@?[A-Za-z0-9._-]+$",
                    "default": "@mateai-c6m",
                    "description": "YouTube channel handle (with or without leading '@', e.g. '@mateai-c6m'). Defaults to '@mateai-c6m'.",
                },
                "force_public": {
                    "type": "boolean",
                    "default": False,
                    "description": "Opt in to public page scraping for this call (bypasses OAuth2; public views/likes only). Only set when the user asks for it.",
                },
            },
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["studio_oauth", "public_scrape"]},
                "channel": {"type": "object"},
                "videos": {"type": "array", "items": {"type": "object"}},
                "shorts": {"type": "array", "items": {"type": "object"}},
                "dashboardPath": {"type": "string"},
            },
            "required": ["mode", "channel", "videos", "shorts", "dashboardPath"],
        },
        "annotations": {
            "title": "Fetch YouTube Channel Snapshot & Update Local Dashboard",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_shorts_experiment_table",
        "description": (
            "Generate a GitHub-Flavored Markdown comparison table of the channel's YouTube Shorts ordered newest-first "
            "with columns for Publish Date, Title, Views, Viewed vs Swiped Away %, Average % Viewed, Engaged Views, and Subscribers Gained. "
            "Pulls live data from YouTube Data API v3 + YouTube Analytics API v2 when OAuth2 is configured (or public channel pages when unauthenticated, "
            "where private retention columns are shown as '—'). Returns a 'No Shorts found' notice if the channel has no Shorts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "pattern": "^@?[A-Za-z0-9._-]+$",
                    "default": "@mateai-c6m",
                    "description": "YouTube channel handle (with or without leading '@', default '@mateai-c6m').",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Generate Shorts Experiment Markdown Table",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_video_details",
        "description": (
            "Fetch public video metadata plus owner-authorized YouTube Analytics retention diagnostics for a single 11-character video_id: "
            "100-point elapsedVideoTimeRatio audience retention curve, exact MM:SS drop-off cliffs, relativeRetentionPerformance peer percentiles, "
            "and traffic source breakdown. Retention curve and traffic diagnostics require channel-owner OAuth2 (a studioDiagnosisError explains a missing scope). "
            "Public page metadata (title, views, likes) is scraped only when force_public=true or MATEAI_YT_PUBLIC_SCRAPE=1. "
            "When words_or_script_path is provided, maps each retention drop-off cliff onto the exact spoken words at that timestamp."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9_-]{11}$",
                    "description": "11-character YouTube video or Short ID (e.g. 'I9c6W135VZk').",
                },
                "words_or_script_path": {
                    "type": "string",
                    "description": "Optional local filesystem path to a readable Whisper words.js or JSON word-timestamp file used to align retention drop-off cliffs with spoken words.",
                },
                "force_public": {
                    "type": "boolean",
                    "default": False,
                    "description": "Opt in to scraping the public watch page for title/views/likes. Only set when the user asks for it.",
                },
            },
            "required": ["video_id"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "videoId": {"type": "string"},
                "title": {"type": "string"},
                "viewCount": {"type": "integer"},
                "likeCount": {"type": "integer"},
                "studioDiagnosis": {"type": "object"},
            },
            "required": ["videoId"],
        },
        "annotations": {
            "title": "Fetch Video Retention Curve & Drop-Off Diagnosis",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_upload_draft",
        "description": (
            "Upload a local MP4/MOV video file to YouTube Studio via YouTube Data API v3 (videos.insert, costs ~1,600 daily quota units) "
            "and optionally attach a custom thumbnail (thumbnails.set) and top-level pinned comment (commentThreads.insert). "
            "Requires channel OAuth2 with youtube.upload scope. Non-idempotent: each call creates a new YouTube video resource and returns "
            "{videoId, studioUrl, watchUrl, privacyStatus, publishAt}. "
            "Defaults to privacy_status='private' (unpublished draft); when publish_at (ISO 8601 future timestamp) is provided, privacy_status is forced to 'private' "
            "until YouTube automatically publishes the video at publish_at. Inline parameters (title, description, tags, hashtags, pinned_comment) override values parsed from spec_path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "Absolute local filesystem path to a readable MP4 or MOV video file to upload."},
                "title": {"type": "string", "maxLength": 100, "description": "Video title (1–100 characters). Required unless spec_path provides a '## Title' section."},
                "description": {"type": "string", "maxLength": 5000, "description": "Video description (up to 5,000 characters). Hashtags from 'hashtags' are appended if not already present."},
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Hashtags to append to the end of description (e.g. ['#AINews', '#Shorts']).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "YouTube SEO keyword tags (combined length up to 500 characters).",
                },
                "pinned_comment": {"type": "string", "description": "Top-level comment text to post on the video when auto_post_comment is true."},
                "spec_path": {"type": "string", "description": "Optional local path to a Markdown upload spec file ('## Title', '## Description', '## Tags', '## Pinned comment') used as fallback when inline fields are omitted."},
                "thumbnail_path": {"type": "string", "description": "Optional absolute local path to a PNG/JPG custom thumbnail image (<=2MB, requires verified YouTube account)."},
                "privacy_status": {
                    "type": "string",
                    "enum": ["private", "unlisted", "public"],
                    "default": "private",
                    "description": "Initial visibility in YouTube Studio (default: 'private'). Forced to 'private' whenever publish_at is set.",
                },
                "publish_at": {
                    "type": "string",
                    "description": "Optional future ISO 8601 timestamp with timezone offset for scheduled publication (e.g. '2026-11-04T18:00:00+01:00'). Forces privacy_status='private' until release.",
                },
                "language": {"type": "string", "default": "en", "description": "BCP-47 language code for defaultLanguage and defaultAudioLanguage (default: 'en')."},
                "category_id": {"type": "string", "default": "28", "description": "YouTube numeric category ID (default: '28' for Science & Technology)."},
                "made_for_kids": {"type": "boolean", "default": False, "description": "COPPA selfDeclaredMadeForKids flag (default: false)."},
                "contains_synthetic_media": {
                    "type": "boolean",
                    "default": False,
                    "description": "YouTube Studio altered/synthetic media disclosure flag (status.containsSyntheticMedia, default: false).",
                },
                "auto_post_comment": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true and pinned_comment is non-empty, immediately posts pinned_comment as a top-level comment (requires video to allow comments).",
                },
            },
            "required": ["video_path"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "videoId": {"type": "string"},
                "studioUrl": {"type": "string"},
                "watchUrl": {"type": "string"},
                "privacyStatus": {"type": "string"},
                "publishAt": {"type": ["string", "null"]},
            },
            "required": ["videoId", "studioUrl", "watchUrl"],
        },
        "annotations": {
            "title": "Upload Video Draft or Scheduled Release to YouTube Studio",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_update_video",
        "description": (
            "Perform a partial, idempotent update on an existing YouTube video's metadata, visibility, schedule, or custom thumbnail "
            "in YouTube Studio via YouTube Data API v3 (videos.list + videos.update, costs ~51 quota units). Requires channel-owner OAuth2. "
            "Fetches current snippet/status first so omitted parameters (title, description, tags, privacy_status, publish_at) are preserved unchanged rather than cleared. "
            "Setting publish_at automatically forces privacy_status='private' as required by YouTube's scheduling API. Returns {videoId, studioUrl, updatedFields}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9_-]{11}$",
                    "description": "11-character YouTube video ID to update.",
                },
                "title": {"type": "string", "maxLength": 100, "description": "New video title (1–100 characters). Leave omitted to keep existing title."},
                "description": {"type": "string", "maxLength": 5000, "description": "New video description (up to 5,000 characters). Leave omitted to keep existing description."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Replacement list of YouTube SEO keyword tags. Leave omitted to keep existing tags.",
                },
                "privacy_status": {
                    "type": "string",
                    "enum": ["private", "unlisted", "public"],
                    "description": "Updated visibility status. Ignored and forced to 'private' if publish_at is provided.",
                },
                "publish_at": {
                    "type": "string",
                    "description": "Future ISO 8601 timestamp with timezone offset to schedule publication (e.g. '2026-11-05T17:00:00+01:00'). Forces privacy_status='private'.",
                },
                "thumbnail_path": {
                    "type": "string",
                    "description": "Optional absolute local filesystem path to a readable PNG/JPG image (<=2MB) to upload via thumbnails.set.",
                },
            },
            "required": ["video_id"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "videoId": {"type": "string"},
                "studioUrl": {"type": "string"},
            },
            "required": ["videoId", "studioUrl"],
        },
        "annotations": {
            "title": "Update Existing YouTube Video Metadata, Schedule, or Thumbnail",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_post_comment",
        "description": (
            "Post a public top-level comment thread on a YouTube video or Short via YouTube Data API v3 "
            "(commentThreads.insert, costs ~50 daily quota units). Requires OAuth2 with youtube.force-ssl scope. "
            "Non-idempotent: each call publishes a new visible comment immediately under the authenticated channel identity "
            "and returns {commentId, videoId, text}. Fails if comments are disabled on the target video or the video is private."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9_-]{11}$",
                    "description": "11-character YouTube video ID where the top-level comment will be posted.",
                },
                "text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 10000,
                    "description": "Plain-text comment body (1–10,000 characters) to publish publicly on the video.",
                },
            },
            "required": ["video_id", "text"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "commentId": {"type": "string"},
                "videoId": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["commentId", "videoId"],
        },
        "annotations": {
            "title": "Post Public Top-Level YouTube Comment",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_list_videos",
        "description": (
            "List the authenticated channel's uploads (including private, unlisted and scheduled), newest first, with "
            "videoId, title, privacyStatus, publishAt, views and URL. Optional `query` is a case-insensitive substring "
            "match on title or description, applied locally. Costs ~2 quota units per 50 videos paged. Requires OAuth2."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional text to match in title or description."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 25, "description": "Max videos to return."},
            },
            "additionalProperties": False,
        },
        "annotations": {
            "title": "List or Search Own YouTube Videos",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_list_comments",
        "description": (
            "Read top-level comment threads on a video (commentThreads.list, ~1 quota unit): commentId, author, text, likes, "
            "publishedAt, replyCount and the first few replies. Single page, max 100. Use a returned commentId as "
            "yt_reply_comment's parent_id. Fails if comments are disabled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{11}$", "description": "11-character YouTube video ID."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "order": {"type": "string", "enum": ["time", "relevance"], "default": "time"},
            },
            "required": ["video_id"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Read YouTube Video Comments",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_reply_comment",
        "description": (
            "Publish a public reply to a top-level comment (comments.insert, ~50 quota units) under the authenticated "
            "channel identity. parent_id must be a top-level commentId from yt_list_comments. Non-idempotent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_id": {"type": "string", "minLength": 1, "description": "commentId of the top-level comment to reply to."},
                "text": {"type": "string", "minLength": 1, "maxLength": 10000, "description": "Plain-text reply body."},
            },
            "required": ["parent_id", "text"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Reply to a YouTube Comment",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "yt_delete_video",
        "description": (
            "PERMANENTLY delete one of the channel's videos (videos.delete, ~50 quota units). Irreversible: views, "
            "watch hours and comments are lost. To merely hide a video use yt_update_video with privacy_status. "
            "Refuses unless confirm_title exactly equals the video's current title."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{11}$", "description": "11-character YouTube video ID."},
                "confirm_title": {"type": "string", "minLength": 1, "description": "Exact current title of the video, as a deliberate confirmation."},
            },
            "required": ["video_id", "confirm_title"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Permanently Delete a YouTube Video",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "tiktok_channel_snapshot",
        "description": (
            "Fetch authenticated TikTok profile statistics (followers, total likes, video count) and recent videos "
            "(views, likes, comments, shares, duration, publish date, share URL) via the official TikTok Display API v2 "
            "(user.info.basic, user.info.profile, user.info.stats, video.list) and cache to tiktok_snapshot.json. "
            "Requires OAuth2 setup via `python3 tiktok_studio.py setup`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Fetch Official TikTok Profile & Video Snapshot",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "tiktok_upload_draft",
        "description": (
            "Upload a local MP4/MOV video file as an Inbox Draft to the creator's TikTok mobile app notifications "
            "via the official TikTok Content Posting API (/v2/post/publish/inbox/video/init/, which accepts source_info only). "
            "Builds and returns the ready-to-paste caption (from spec_path or title/hashtags, with #Shorts stripped) "
            "plus an AI-generated content label reminder so the creator can paste the caption and turn on TikTok's "
            "AI-generated toggle in the mobile app before publishing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_path": {
                    "type": "string",
                    "description": "Absolute local filesystem path to a readable MP4/MOV video file.",
                },
                "spec_path": {
                    "type": "string",
                    "description": "Optional absolute path to a MateAI upload Markdown spec (## Title, ## Description, ## Tags).",
                },
                "title": {
                    "type": "string",
                    "description": "Optional caption title override (used when spec_path is omitted or to override ## Title).",
                },
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of hashtags to append to the returned caption.",
                },
            },
            "required": ["video_path"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Upload Video to TikTok App Inbox & Return Caption",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "cross_platform_shorts_table",
        "description": (
            "Generate a GitHub-Flavored Markdown comparison table pairing YouTube Shorts with TikTok videos "
            "(matching normalized YouTube Short titles against TikTok title or video_description, while keeping unmatched "
            "videos from either platform) across official API metrics: Views, Likes, Comments, YouTube Avg % Viewed, and TikTok Shares."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "yt_handle": {
                    "type": "string",
                    "pattern": "^@?[A-Za-z0-9._-]+$",
                    "default": "@mateai-c6m",
                    "description": "YouTube channel handle (default '@mateai-c6m').",
                },
                "yt_force_public": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, allow public scraping fallback for the YouTube snapshot.",
                },
            },
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Generate YouTube Shorts vs. TikTok Comparison Table",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
]


ALWAYS_CONFIRM = {"yt_delete_video"}
CONFIRM_ENV = "MATEAI_YT_CONFIRM"


def confirm_tools() -> set[str]:
    """Tools that bounce until the user has explicitly said yes in chat.

    yt_delete_video is always included. MATEAI_YT_CONFIRM adds more: a comma-separated list of
    tool names, e.g. "yt_reply_comment,yt_post_comment". Unknown names are warned about on stderr.
    """
    known = {t["name"] for t in TOOLS}
    extra = {s.strip() for s in os.environ.get(CONFIRM_ENV, "").split(",") if s.strip()}
    for bad in sorted(extra - known):
        print(f"mateai-youtube-mcp: ignoring unknown tool {bad!r} in {CONFIRM_ENV}", file=sys.stderr)
    return ALWAYS_CONFIRM | (extra & known)


def listed_tools() -> list[dict[str, Any]]:
    """TOOLS as advertised to the client: gated tools get a DANGEROUS marker and a user_confirmed flag."""
    gated = confirm_tools()
    out = copy.deepcopy(TOOLS)
    for tool in out:
        if tool["name"] in gated:
            tool["description"] = (
                "DANGEROUS — ask the user for an explicit yes in chat before calling; the first call is refused "
                "until user_confirmed=true. " + tool["description"]
            )
            tool["inputSchema"]["properties"]["user_confirmed"] = {
                "type": "boolean",
                "description": "Set true ONLY after the user explicitly approved this exact action in chat. Never set it on your own.",
            }
    return out


def _handle_tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name in confirm_tools() and not args.get("user_confirmed"):
        shown = {k: v for k, v in args.items() if k != "user_confirmed"}
        return {
            "isError": True,
            "content": [{
                "type": "text",
                "text": (
                    f"CONFIRMATION REQUIRED — nothing was done. {name} is marked dangerous. "
                    f"Tell the user exactly what this call will do (tool {name}, arguments {json.dumps(shown)}) "
                    "and ask for an explicit yes. Only after they say yes, repeat the same call with user_confirmed=true. "
                    "Never set user_confirmed on your own."
                ),
            }],
        }

    if name == "tiktok_channel_snapshot":
        snap = fetch_tiktok_snapshot()
        TIKTOK_CACHE_FILE.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        return {"content": [{"type": "text", "text": json.dumps(snap, indent=2)}]}

    if name == "tiktok_upload_draft":
        res = upload_tiktok_inbox_draft(
            video_path=Path(args["video_path"]),
            spec_path=Path(args["spec_path"]) if args.get("spec_path") else None,
            title=args.get("title"),
            hashtags=args.get("hashtags"),
        )
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "cross_platform_shorts_table":
        yt_handle = args.get("yt_handle") or DEFAULT_HANDLE
        yt_force_public = bool(args.get("yt_force_public", False))
        yt_snap = get_best_snapshot(handle=yt_handle, force_public=yt_force_public)
        tt_snap = fetch_tiktok_snapshot()
        md = build_cross_platform_table(yt_snap, tt_snap)
        return {"content": [{"type": "text", "text": md}]}

    if name == "yt_channel_snapshot":
        handle = args.get("handle") or DEFAULT_HANDLE
        force_public = bool(args.get("force_public", False))
        snap = get_best_snapshot(handle=handle, force_public=force_public)
        render_html_report(snap, REPORT_FILE)
        snap["dashboardPath"] = str(REPORT_FILE)
        return {"content": [{"type": "text", "text": json.dumps(snap, indent=2)}]}

    if name == "yt_shorts_experiment_table":
        handle = args.get("handle") or DEFAULT_HANDLE
        snap = get_best_snapshot(handle=handle)
        md = build_shorts_experiment_markdown(snap)
        return {"content": [{"type": "text", "text": md}]}

    if name == "yt_video_details":
        video_id = args["video_id"]
        words_path = Path(args["words_or_script_path"]) if args.get("words_or_script_path") else None
        if PUBLIC_SCRAPE_ENV or bool(args.get("force_public", False)):
            details = fetch_video_public_details(video_id)
        else:
            details = {"videoId": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "sourceMode": "studio_only"}
        try:
            diag = fetch_video_retention_diagnosis(video_id, words_or_script_path=words_path)
            details["studioDiagnosis"] = diag
        except Exception as exc:
            details["studioDiagnosisError"] = str(exc)
        return {"content": [{"type": "text", "text": json.dumps(details, indent=2)}]}

    if name == "yt_upload_draft":
        res = upload_private_draft(
            video_path=Path(args["video_path"]),
            spec_path=Path(args["spec_path"]) if args.get("spec_path") else None,
            title=args.get("title"),
            description=args.get("description"),
            tags=args.get("tags"),
            hashtags=args.get("hashtags"),
            pinned_comment=args.get("pinned_comment"),
            category_id=args.get("category_id", "28"),
            language=args.get("language", "en"),
            made_for_kids=bool(args.get("made_for_kids", False)),
            contains_synthetic_media=bool(args.get("contains_synthetic_media", False)),
            thumbnail_path=Path(args["thumbnail_path"]) if args.get("thumbnail_path") else None,
            privacy_status=args.get("privacy_status", "private"),
            publish_at=args.get("publish_at"),
            auto_post_comment=bool(args.get("auto_post_comment", False)),
        )
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "yt_update_video":
        res = update_video_metadata(
            video_id=args["video_id"],
            title=args.get("title"),
            description=args.get("description"),
            tags=args.get("tags"),
            privacy_status=args.get("privacy_status"),
            publish_at=args.get("publish_at"),
            thumbnail_path=Path(args["thumbnail_path"]) if args.get("thumbnail_path") else None,
        )
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "yt_post_comment":
        res = post_video_comment(video_id=args["video_id"], text=args["text"])
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "yt_list_videos":
        res = list_channel_videos(query=args.get("query"), limit=int(args.get("limit", 25)))
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "yt_list_comments":
        res = list_video_comments(
            video_id=args["video_id"],
            limit=int(args.get("limit", 20)),
            order=args.get("order", "time"),
        )
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "yt_reply_comment":
        res = reply_to_comment(parent_id=args["parent_id"], text=args["text"])
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "yt_delete_video":
        res = delete_video(video_id=args["video_id"], confirm_title=args["confirm_title"])
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            params = msg.get("params") or {}
            client_proto = params.get("protocolVersion") or "2024-11-05"
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": client_proto,
                    "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                    "serverInfo": SERVER_INFO,
                    "instructions": SERVER_INSTRUCTIONS,
                },
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method and method.startswith("notifications/"):
            continue
        elif method == "ping":
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {}}) + "\n")
            sys.stdout.flush()
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": listed_tools()},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "prompts/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"prompts": []},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "resources/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"resources": []},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "resources/templates/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"resourceTemplates": []},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "tools/call":
            params = msg.get("params", {})
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {}) or {}
            try:
                result = _handle_tool_call(tool_name, tool_args)
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": result}
            except Exception as exc:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Error: {exc}"}],
                    },
                }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif msg_id is not None:
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
