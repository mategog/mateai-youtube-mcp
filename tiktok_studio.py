#!/usr/bin/env python3
"""
mateai-youtube-mcp — Official TikTok OAuth2 v2 Connector & Cross-Platform Shorts Table
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import hashlib
import re
import secrets
from pathlib import Path
from typing import Any

from yt_studio import (
    AUTHOR_ATTRIBUTION,
    SSL_CONTEXT,
    STATE_DIR,
    get_best_snapshot,
    parse_upload_markdown,
)

TIKTOK_TOKEN_FILE = STATE_DIR / ".tokens" / "tiktok_token.json"
TIKTOK_CLIENT_FILE = STATE_DIR / "tiktok_auth_secret" / "tiktok_client.json"
TIKTOK_CACHE_FILE = STATE_DIR / "tiktok_snapshot.json"
REDIRECT_URI = "http://127.0.0.1:8765/callback/"
TIKTOK_SCOPES = "user.info.basic,user.info.profile,user.info.stats,video.list,video.upload"

SINGLE_CHUNK_MAX_BYTES = 64_000_000
MULTI_CHUNK_SIZE_BYTES = 32_000_000
PKCE_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
HASHTAG_RE = re.compile(r"(?<!\w)#[A-Za-z][A-Za-z0-9_]*")


def build_pkce_pair(verifier: str | None = None) -> tuple[str, str]:
    """Generate or validate a 43-128 char RFC 7636 verifier and hex SHA-256 challenge for TikTok Desktop Login Kit."""
    if verifier is None:
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
        verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    if not PKCE_VERIFIER_RE.match(verifier):
        raise ValueError("PKCE code_verifier must be 43-128 characters matching [A-Za-z0-9._~-].")
    challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()
    return verifier, challenge


def compute_upload_chunks(file_size: int) -> tuple[int, int, list[tuple[int, int]]]:
    """Compute (chunk_size, total_chunk_count, [(start, end_inclusive), ...]) per TikTok Content Posting API rules."""
    if file_size <= 0:
        raise ValueError("file_size must be positive")
    if file_size <= SINGLE_CHUNK_MAX_BYTES:
        return file_size, 1, [(0, file_size - 1)]

    chunk_size = MULTI_CHUNK_SIZE_BYTES
    total_chunks = file_size // chunk_size
    ranges: list[tuple[int, int]] = []
    for idx in range(total_chunks):
        start = idx * chunk_size
        end = (file_size - 1) if (idx == total_chunks - 1) else (start + chunk_size - 1)
        ranges.append((start, end))
    return chunk_size, total_chunks, ranges


def parse_tiktok_caption_from_spec(
    spec_path: Path | None = None,
    title: str | None = None,
    hashtags: list[str] | None = None,
) -> str:
    """Build a ready-to-paste TikTok caption (<=2200 chars) from an upload Markdown spec or explicit title/hashtags."""
    meta = (
        parse_upload_markdown(spec_path)
        if (spec_path and spec_path.exists())
        else {"title": "", "description": "", "tags": []}
    )
    final_title = (title if title is not None else meta.get("title", "")).strip()

    raw_tags: list[str] = []
    if hashtags is not None:
        raw_tags = [h if h.startswith("#") else f"#{h}" for h in hashtags if h.strip()]
    else:
        desc = meta.get("description") or ""
        raw_tags = HASHTAG_RE.findall(desc)
        if not raw_tags and meta.get("tags"):
            for t in meta["tags"][:6]:
                cleaned = re.sub(r"[^A-Za-z0-9]", "", t)
                if cleaned and cleaned[0].isalpha():
                    raw_tags.append(f"#{cleaned}")

    filtered_tags: list[str] = []
    seen_lower: set[str] = set()
    for tag in raw_tags:
        low = tag.lower()
        if low in ("#shorts", "#short") or low in seen_lower:
            continue
        seen_lower.add(low)
        filtered_tags.append(tag)

    tag_line = " ".join(filtered_tags)
    if final_title and tag_line:
        caption = f"{final_title}\n\n{tag_line}"
    else:
        caption = final_title or tag_line
    return caption[:2200]


def normalize_short_title(text: str) -> str:
    """Strip hashtags and punctuation and collapse whitespace for cross-platform Short matching."""
    without_tags = re.sub(r"#\w+", " ", text or "")
    alpha_num = re.sub(r"[^\w\s]", " ", without_tags)
    return re.sub(r"\s+", " ", alpha_num).strip().lower()


def _fmt_int(val: Any) -> str:
    return f"{int(val):,}" if val is not None else "—"


def _fmt_pct(val: Any) -> str:
    return f"{float(val):.1f}%" if val is not None else "—"


def build_cross_platform_table(yt_snapshot: dict[str, Any], tt_snapshot: dict[str, Any]) -> str:
    """Build a Markdown table comparing YouTube Shorts and TikTok videos on official API fields."""
    lines = [
        "| Video | Published | YT Views | TT Views | YT Likes | TT Likes | YT Comments | TT Comments | YT Avg % | TT Shares |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    yt_shorts = [v for v in yt_snapshot.get("videos", []) if v.get("format") == "short"]
    tt_videos = list(tt_snapshot.get("videos", []))
    matched_tt_indices: set[int] = set()

    for yv in yt_shorts:
        yt_norm = normalize_short_title(yv.get("title", ""))
        matched_tt: dict[str, Any] | None = None
        if yt_norm:
            for idx, tv in enumerate(tt_videos):
                if idx in matched_tt_indices:
                    continue
                tt_title_norm = normalize_short_title(tv.get("title", ""))
                tt_desc_norm = normalize_short_title(tv.get("videoDescription", ""))
                if yt_norm in (tt_title_norm, tt_desc_norm):
                    matched_tt = tv
                    matched_tt_indices.add(idx)
                    break

        display_title = re.sub(r"\s*#Shorts\b", "", yv.get("title") or yv.get("videoId", ""), flags=re.IGNORECASE).strip()
        pub = yv.get("publishDate") or (matched_tt.get("publishDate") if matched_tt else None) or "—"
        lines.append(
            f"| {display_title} | {pub} | {_fmt_int(yv.get('views'))} | "
            f"{_fmt_int(matched_tt.get('views') if matched_tt else None)} | "
            f"{_fmt_int(yv.get('likes'))} | "
            f"{_fmt_int(matched_tt.get('likes') if matched_tt else None)} | "
            f"{_fmt_int(yv.get('comments'))} | "
            f"{_fmt_int(matched_tt.get('comments') if matched_tt else None)} | "
            f"{_fmt_pct(yv.get('avgViewPct'))} | "
            f"{_fmt_int(matched_tt.get('shares') if matched_tt else None)} |"
        )

    for idx, tv in enumerate(tt_videos):
        if idx in matched_tt_indices:
            continue
        raw_label = (tv.get("title") or tv.get("videoDescription") or tv.get("videoId") or "TikTok Video").strip()
        display_title = re.sub(r"(?<!\w)#\w+", "", raw_label).strip() or raw_label
        pub = tv.get("publishDate") or "—"
        lines.append(
            f"| {display_title} | {pub} | — | {_fmt_int(tv.get('views'))} | "
            f"— | {_fmt_int(tv.get('likes'))} | "
            f"— | {_fmt_int(tv.get('comments'))} | "
            f"— | {_fmt_int(tv.get('shares'))} |"
        )

    return "\n".join(lines)
