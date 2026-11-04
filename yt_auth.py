"""
mateai-youtube-mcp — OAuth2 credentials and authenticated YouTube client
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import yt_common

TOKEN_FILE = yt_common.STATE_DIR / ".tokens" / "token.json"


def _resolve_default_client_secret() -> Path:
    direct = yt_common.STATE_DIR / "client_secret.json"
    if direct.exists():
        return direct
    secret_dir = yt_common.STATE_DIR / "google_auth_secret"
    if secret_dir.is_dir():
        matches = sorted(secret_dir.glob("client_secret*.json"))
        if matches:
            return matches[0]
    root_matches = sorted(yt_common.STATE_DIR.glob("client_secret*.json"))
    if root_matches:
        return root_matches[0]
    return direct


DEFAULT_CLIENT_SECRET = _resolve_default_client_secret()

SCOPES_READONLY = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
SCOPES_WITH_UPLOAD = SCOPES_READONLY + [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


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


def _youtube_client(client_secret_path: Path = DEFAULT_CLIENT_SECRET):
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=True)
    return build("youtube", "v3", credentials=creds)
