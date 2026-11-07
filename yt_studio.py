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
import json
from pathlib import Path

# The code now lives in focused modules; this file is the CLI entry point plus a compatibility
# facade so `from yt_studio import ...` (mcp_server, tiktok_studio, hooks) keeps working.
# Tests that patch a name must patch the module that owns it (e.g. yt_auth.TOKEN_FILE), because
# patching a re-exported alias here does not affect the code that actually runs.
from yt_auth import (  # noqa: F401
    DEFAULT_CLIENT_SECRET,
    SCOPES_READONLY,
    SCOPES_WITH_UPLOAD,
    TOKEN_FILE,
    _expired_marker,
    _resolve_default_client_secret,
    _saved_scopes,
    _youtube_client,
    get_oauth_credentials,
)
from yt_common import (  # noqa: F401
    AUTHOR_ATTRIBUTION,
    CACHE_FILE,
    DEFAULT_HANDLE,
    HERE,
    HTTP_HEADERS,
    REPORT_FILE,
    SSL_CONTEXT,
    STATE_DIR,
    TEMPLATE_FILE,
    _http_get,
    _parse_iso_duration,
    _ssl_context,
    use_utf8_stdio,
    purge_stale_youtube_cache,
)
from yt_manage import (  # noqa: F401
    delete_video,
    fetch_video_text,
    list_channel_videos,
    list_video_comments,
    reply_to_comment,
)
from yt_public import (  # noqa: F401
    _extract_yt_initial_data,
    fetch_public_channel_snapshot,
    fetch_video_public_details,
)
from yt_retention import fetch_video_retention_diagnosis  # noqa: F401
from yt_setup import run_interactive_setup_wizard
from yt_snapshot import (  # noqa: F401
    PUBLIC_SCRAPE_ENV,
    SCRAPE_DISABLED_MSG,
    _http_status,
    _load_shorts_styles,
    build_shorts_experiment_markdown,
    fetch_studio_channel_snapshot,
    get_best_snapshot,
    print_cli_summary,
    render_html_report,
)
from yt_videos import (  # noqa: F401
    _build_update_changes,
    _build_upload_body,
    _describe_publish_at,
    parse_upload_markdown,
    post_video_comment,
    update_video_metadata,
    upload_private_draft,
)


def main() -> None:
    use_utf8_stdio()
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
    purge_stale_youtube_cache()
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
