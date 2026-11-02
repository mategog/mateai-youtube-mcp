#!/usr/bin/env python3
"""
mateai-youtube-mcp — Model Context Protocol (MCP) Server for Antigravity & Claude Code
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from yt_studio import (
    AUTHOR_ATTRIBUTION,
    DEFAULT_HANDLE,
    REPORT_FILE,
    build_shorts_experiment_markdown,
    fetch_video_public_details,
    fetch_video_retention_diagnosis,
    get_best_snapshot,
    post_video_comment,
    render_html_report,
    update_video_metadata,
    upload_private_draft,
)

SERVER_INFO = {
    "name": "mateai-youtube-mcp",
    "version": "1.0.0",
    "author": AUTHOR_ATTRIBUTION,
}

TOOLS = [
    {
        "name": "yt_channel_snapshot",
        "description": (
            "Fetch live YouTube channel stats, Long-form videos, Shorts performance, "
            "and Studio analytics (retention, engaged views, swipe-away rate when OAuth is active). "
            "Also updates the local report.html dashboard."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "YouTube channel handle (e.g. '@mateai-c6m'). Defaults to '@mateai-c6m'.",
                },
                "force_public": {
                    "type": "boolean",
                    "description": "If true, use zero-config public snapshot even if OAuth token exists.",
                },
            },
        },
    },
    {
        "name": "yt_shorts_experiment_table",
        "description": (
            "Generate the Markdown experiment tracking table for Shorts visual styles "
            "(Views, Viewed vs swiped, Avg % viewed, Engaged views, Subs gained)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "YouTube channel handle (default '@mateai-c6m').",
                },
            },
        },
    },
    {
        "name": "yt_video_details",
        "description": (
            "Fetch deep retention diagnosis (100-point retention curve, exact MM:SS drop-off cliffs, "
            "YouTube peer percentiles, traffic sources, and optional spoken-word mapping) for a video or Short."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {
                    "type": "string",
                    "description": "11-character YouTube video ID (e.g. 'I9c6W135VZk').",
                },
                "words_or_script_path": {
                    "type": "string",
                    "description": "Optional path to Whisper words.js / JSON timing file to map drop-off cliffs to exact spoken words.",
                },
            },
            "required": ["video_id"],
        },
    },
    {
        "name": "yt_upload_draft",
        "description": (
            "Upload and configure a YouTube video or Short end-to-end. The AI can pass title, description, "
            "hashtags, tags, language, category, synthetic-media disclosure, thumbnail, pinned comment, "
            "and scheduled publish_at timestamp directly (or via a spec_path markdown file)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "Absolute path to MP4/MOV file."},
                "title": {"type": "string", "description": "Video title (up to 100 characters)."},
                "description": {"type": "string", "description": "Full video description (up to 5000 characters)."},
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Hashtags to append to description (e.g. ['#AINews', '#Shorts']).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "YouTube SEO keyword tags.",
                },
                "pinned_comment": {"type": "string", "description": "Top-level comment to post on the video."},
                "spec_path": {"type": "string", "description": "Optional path to upload markdown file (fallback if title/description omitted)."},
                "thumbnail_path": {"type": "string", "description": "Optional absolute path to thumbnail PNG/JPG."},
                "privacy_status": {
                    "type": "string",
                    "enum": ["private", "unlisted", "public"],
                    "description": "Visibility in YouTube Studio (default: 'private'). Automatically set to 'private' when publish_at is used.",
                },
                "publish_at": {
                    "type": "string",
                    "description": "Optional ISO 8601 timestamp to schedule automatic publication (e.g. '2026-11-04T18:00:00+01:00').",
                },
                "language": {"type": "string", "description": "BCP-47 language code for title/audio (default: 'en')."},
                "category_id": {"type": "string", "description": "YouTube category ID (default: '28' for Science & Technology)."},
                "made_for_kids": {"type": "boolean", "description": "Whether video is made for kids (default: false)."},
                "contains_synthetic_media": {
                    "type": "boolean",
                    "description": "Altered/synthetic media disclosure flag in YouTube Studio (default: false).",
                },
                "auto_post_comment": {
                    "type": "boolean",
                    "description": "If true, automatically post the pinned_comment onto the video.",
                },
            },
            "required": ["video_path"],
        },
    },
    {
        "name": "yt_update_video",
        "description": (
            "Update an existing video's title, description, tags, privacy status, "
            "scheduled publishAt timestamp, or thumbnail in YouTube Studio."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "description": "11-character YouTube video ID."},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "privacy_status": {"type": "string", "enum": ["private", "unlisted", "public"]},
                "publish_at": {"type": "string", "description": "ISO 8601 schedule time (e.g. '2026-11-05T17:00:00+01:00')."},
                "thumbnail_path": {"type": "string", "description": "Optional absolute path to new thumbnail image."},
            },
            "required": ["video_id"],
        },
    },
    {
        "name": "yt_post_comment",
        "description": "Post a top-level comment on a YouTube video or Short.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "description": "11-character YouTube video ID."},
                "text": {"type": "string", "description": "Comment text to post."},
            },
            "required": ["video_id", "text"],
        },
    },
]


def _handle_tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
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
        details = fetch_video_public_details(video_id)
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
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {}}) + "\n")
            sys.stdout.flush()
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
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
