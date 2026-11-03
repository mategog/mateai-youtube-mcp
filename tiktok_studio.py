#!/usr/bin/env python3
"""
mateai-youtube-mcp — Official TikTok OAuth2 v2 Connector & Cross-Platform Shorts Table
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.server
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from yt_studio import (
    AUTHOR_ATTRIBUTION,
    DEFAULT_HANDLE,
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

OAUTH_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
OAUTH_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = (
    "https://open.tiktokapis.com/v2/user/info/"
    "?fields=open_id,union_id,avatar_url,display_name,username,follower_count,likes_count,video_count"
)
VIDEO_LIST_URL = (
    "https://open.tiktokapis.com/v2/video/list/"
    "?fields=id,title,video_description,create_time,duration,view_count,like_count,comment_count,share_count,cover_image_url,share_url"
)
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"

SINGLE_CHUNK_MAX_BYTES = 64_000_000
MULTI_CHUNK_SIZE_BYTES = 32_000_000
PKCE_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
HASHTAG_RE = re.compile(r"(?<!\w)#[A-Za-z][A-Za-z0-9_]*")

AI_LABEL_REMINDER = (
    "Turn on TikTok's AI-generated content toggle in the mobile app before posting "
    "(synthetic voice cannot be flagged via the Inbox API)."
)


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


# ---------------------------------------------------------------------------
# Private HTTP & OAuth2 Token Helpers
# ---------------------------------------------------------------------------

def _post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError(f"TikTok OAuth error: {payload.get('error_description') or payload.get('error')}")
    return payload


def _http_json(url: str, *, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    data: bytes | None = None
    method = "GET"
    if body is not None:
        headers["Content-Type"] = "application/json; charset=UTF-8"
        data = json.dumps(body).encode("utf-8")
        method = "POST"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=25, context=SSL_CONTEXT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    err = payload.get("error") or {}
    if isinstance(err, dict) and err.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok API error ({err.get('code')}): {err.get('message')}")
    return payload


def _put_chunk(upload_url: str, data: bytes, start: int, end: int, total: int) -> None:
    req = urllib.request.Request(
        upload_url,
        data=data,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(len(data)),
            "Content-Range": f"bytes {start}-{end}/{total}",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        resp.read()


def _load_client_credentials(client_file: Path = TIKTOK_CLIENT_FILE) -> tuple[str, str]:
    if not client_file.exists():
        raise RuntimeError(
            f"TikTok OAuth client file not found at {client_file}. "
            "Run `python3 tiktok_studio.py setup` to configure your TikTok Desktop app credentials."
        )
    raw = json.loads(client_file.read_text(encoding="utf-8"))
    key = (raw.get("client_key") or "").strip()
    secret = (raw.get("client_secret") or "").strip()
    if not key or not secret:
        raise RuntimeError(f"Invalid TikTok client credentials in {client_file}: expected client_key and client_secret.")
    return key, secret


def _save_token_payload(token_file: Path, resp: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    saved = {
        "access_token": resp["access_token"],
        "refresh_token": resp.get("refresh_token", ""),
        "expires_at": now + int(resp.get("expires_in", 86400)),
        "refresh_expires_at": now + int(resp.get("refresh_expires_in", 31536000)),
        "open_id": resp.get("open_id", ""),
        "scope": resp.get("scope", ""),
    }
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    os.chmod(token_file, 0o600)
    return saved


def exchange_code_for_token(
    code: str,
    verifier: str,
    client_file: Path = TIKTOK_CLIENT_FILE,
    token_file: Path = TIKTOK_TOKEN_FILE,
) -> dict[str, Any]:
    client_key, client_secret = _load_client_credentials(client_file)
    resp = _post_form(
        OAUTH_TOKEN_URL,
        {
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )
    return _save_token_payload(token_file, resp)


def refresh_tiktok_token(
    refresh_token: str,
    client_file: Path = TIKTOK_CLIENT_FILE,
    token_file: Path = TIKTOK_TOKEN_FILE,
) -> dict[str, Any]:
    client_key, client_secret = _load_client_credentials(client_file)
    resp = _post_form(
        OAUTH_TOKEN_URL,
        {
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    return _save_token_payload(token_file, resp)


def get_valid_tiktok_token(
    token_file: Path = TIKTOK_TOKEN_FILE,
    client_file: Path = TIKTOK_CLIENT_FILE,
) -> str:
    """Return a valid TikTok access_token, refreshing via refresh_token when expired."""
    if not token_file.exists():
        raise RuntimeError(
            "No TikTok OAuth token found. Run `python3 tiktok_studio.py setup` to connect your TikTok account."
        )
    data = json.loads(token_file.read_text(encoding="utf-8"))
    now = int(time.time())
    if int(data.get("expires_at", 0)) > now + 60 and data.get("access_token"):
        return str(data["access_token"])

    refresh_exp = data.get("refresh_expires_at")
    if refresh_exp is not None and int(refresh_exp) <= now:
        raise RuntimeError(
            "TikTok refresh token expired; run `python3 tiktok_studio.py setup` to re-authenticate."
        )
    refresh_tok = (data.get("refresh_token") or "").strip()
    if not refresh_tok:
        raise RuntimeError(
            "TikTok access token expired and no refresh_token is stored; run `python3 tiktok_studio.py setup`."
        )
    refreshed = refresh_tiktok_token(refresh_tok, client_file=client_file, token_file=token_file)
    return str(refreshed["access_token"])


# ---------------------------------------------------------------------------
# Official TikTok Snapshot & Inbox Draft Upload
# ---------------------------------------------------------------------------

def fetch_tiktok_snapshot(
    token_file: Path = TIKTOK_TOKEN_FILE,
    client_file: Path = TIKTOK_CLIENT_FILE,
) -> dict[str, Any]:
    """Fetch official TikTok user stats and recent videos via Display API v2."""
    token = get_valid_tiktok_token(token_file=token_file, client_file=client_file)
    user_payload = _http_json(USER_INFO_URL, token=token, body=None)
    u = (user_payload.get("data") or {}).get("user") or {}

    username = (u.get("username") or "").strip()
    handle = f"@{username}" if username and not username.startswith("@") else (username or "@tiktok")
    display_name = u.get("display_name") or handle

    videos_payload = _http_json(VIDEO_LIST_URL, token=token, body={"max_count": 20})
    raw_videos = ((videos_payload.get("data") or {}).get("videos")) or []

    items: list[dict[str, Any]] = []
    for rv in raw_videos:
        vid_id = str(rv.get("id") or "")
        create_ts = rv.get("create_time")
        pub_date = (
            dt.datetime.fromtimestamp(int(create_ts), tz=dt.timezone.utc).strftime("%Y-%m-%d")
            if create_ts
            else ""
        )
        items.append(
            {
                "videoId": vid_id,
                "title": rv.get("title") or "",
                "videoDescription": rv.get("video_description") or "",
                "publishDate": pub_date,
                "durationSec": int(rv.get("duration") or 0),
                "views": int(rv.get("view_count") or 0),
                "likes": int(rv.get("like_count") or 0),
                "comments": int(rv.get("comment_count") or 0),
                "shares": int(rv.get("share_count") or 0),
                "url": rv.get("share_url") or (f"https://www.tiktok.com/{handle}/video/{vid_id}" if vid_id else ""),
                "thumbnail": rv.get("cover_image_url") or "",
                "sourceMode": "tiktok_oauth",
            }
        )

    total_views = sum(v["views"] for v in items)
    return {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": "tiktok_oauth",
        "channel": {
            "handle": handle,
            "title": display_name,
            "followers": int(u.get("follower_count") or 0),
            "likes": int(u.get("likes_count") or 0),
            "videoCount": int(u.get("video_count") or len(items)),
            "avatarUrl": u.get("avatar_url") or "",
            "url": f"https://www.tiktok.com/{handle}",
        },
        "totals": {
            "videoCount": len(items),
            "totalViews": total_views,
            "topVideo": max(items, key=lambda x: x.get("views", 0)) if items else None,
        },
        "videos": items,
        "attribution": AUTHOR_ATTRIBUTION,
    }


def upload_tiktok_inbox_draft(
    video_path: Path,
    spec_path: Path | None = None,
    title: str | None = None,
    hashtags: list[str] | None = None,
    token_file: Path = TIKTOK_TOKEN_FILE,
    client_file: Path = TIKTOK_CLIENT_FILE,
) -> dict[str, Any]:
    """Upload a local MP4/MOV to the creator's TikTok mobile app inbox via /v2/post/publish/inbox/video/init/."""
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    file_size = video_path.stat().st_size
    chunk_size, total_chunks, ranges = compute_upload_chunks(file_size)
    caption = parse_tiktok_caption_from_spec(spec_path=spec_path, title=title, hashtags=hashtags)
    token = get_valid_tiktok_token(token_file=token_file, client_file=client_file)

    init_body = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        }
    }
    init_resp = _http_json(INBOX_INIT_URL, token=token, body=init_body)
    data = init_resp.get("data") or {}
    publish_id = str(data.get("publish_id") or "")
    upload_url = str(data.get("upload_url") or "")
    if not upload_url:
        raise RuntimeError(f"TikTok inbox init did not return upload_url: {init_resp}")

    with video_path.open("rb") as fh:
        for start, end in ranges:
            fh.seek(start)
            chunk_bytes = fh.read(end - start + 1)
            _put_chunk(upload_url, chunk_bytes, start, end, file_size)

    return {
        "publishId": publish_id,
        "videoPath": str(video_path),
        "videoSize": file_size,
        "totalChunks": total_chunks,
        "caption": caption,
        "aiLabelReminder": AI_LABEL_REMINDER,
    }


# ---------------------------------------------------------------------------
# Guided Desktop Login Kit Setup & Standalone CLI
# ---------------------------------------------------------------------------

def run_tiktok_setup_wizard(
    client_file: Path = TIKTOK_CLIENT_FILE,
    token_file: Path = TIKTOK_TOKEN_FILE,
) -> None:
    print("=" * 72)
    print("  MateAI TikTok Connector — Official Desktop OAuth2 Setup")
    print("=" * 72)
    client_file.parent.mkdir(parents=True, exist_ok=True)
    if not client_file.exists():
        print(f"\n1. Create a Desktop app at https://developers.tiktok.com/")
        print(f"2. Add Redirect URI: {REDIRECT_URI}")
        print(f"3. Enable scopes: {TIKTOK_SCOPES}")
        ck = input("Enter TikTok Client Key: ").strip()
        cs = input("Enter TikTok Client Secret: ").strip()
        client_file.write_text(json.dumps({"client_key": ck, "client_secret": cs}, indent=2), encoding="utf-8")
        os.chmod(client_file, 0o600)

    client_key, _ = _load_client_credentials(client_file)
    verifier, challenge = build_pkce_pair()
    state = secrets.token_hex(16)
    params = urllib.parse.urlencode(
        {
            "client_key": client_key,
            "scope": TIKTOK_SCOPES,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    auth_url = f"{OAUTH_AUTHORIZE_URL}?{params}"
    captured: dict[str, str] = {}

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if "code" in qs:
                captured["code"] = qs["code"][0]
                captured["state"] = qs.get("state", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h3>TikTok connected! You may close this browser tab.</h3>")

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    server = http.server.HTTPServer(("127.0.0.1", 8765), _CallbackHandler)
    print(f"\nOpening TikTok authorization screen in your browser...\n{auth_url}")
    webbrowser.open(auth_url)
    server.handle_request()
    server.server_close()

    if captured.get("state") != state or not captured.get("code"):
        raise RuntimeError("TikTok OAuth callback failed or state mismatch.")
    exchange_code_for_token(captured["code"], verifier, client_file=client_file, token_file=token_file)
    print(f"✓ TikTok OAuth token saved to {token_file} (mode 0600)")


def main() -> None:
    parser = argparse.ArgumentParser(description="MateAI Official TikTok OAuth Connector")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("setup", help="Interactive TikTok Desktop Login Kit OAuth2 setup")
    sub.add_parser("snapshot", help="Fetch TikTok profile and video stats")

    p_up = sub.add_parser("upload-draft", help="Upload MP4 to TikTok mobile app inbox and print ready-to-paste caption")
    p_up.add_argument("--video", required=True, type=Path, help="Path to MP4/MOV file")
    p_up.add_argument("--spec", type=Path, help="Optional path to upload Markdown spec")
    p_up.add_argument("--title", help="Optional title override")
    p_up.add_argument("--hashtags", help="Optional comma-separated hashtags")

    p_cross = sub.add_parser("cross-table", help="Print YouTube Shorts vs. TikTok Markdown comparison table")
    p_cross.add_argument("--yt-handle", default=DEFAULT_HANDLE)
    p_cross.add_argument("--yt-public", action="store_true")

    args = parser.parse_args()
    cmd = args.cmd or "snapshot"

    if cmd == "setup":
        run_tiktok_setup_wizard()
        return

    if cmd == "upload-draft":
        tags = [h.strip() for h in args.hashtags.split(",") if h.strip()] if args.hashtags else None
        res = upload_tiktok_inbox_draft(video_path=args.video, spec_path=args.spec, title=args.title, hashtags=tags)
        print(json.dumps(res, indent=2))
        return

    if cmd == "cross-table":
        yt_snap = get_best_snapshot(handle=args.yt_handle, force_public=args.yt_public)
        tt_snap = fetch_tiktok_snapshot()
        print(build_cross_platform_table(yt_snap, tt_snap))
        return

    snap = fetch_tiktok_snapshot()
    TIKTOK_CACHE_FILE.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    print(json.dumps(snap, indent=2))


if __name__ == "__main__":
    main()
