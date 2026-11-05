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
# youtube.force-ssl accepts every write call the tools make (insert, thumbnails.set, update,
# delete, comments), so the broader `youtube` and `youtube.upload` scopes are not requested.
SCOPES_WITH_UPLOAD = SCOPES_READONLY + [
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


KEYRING_SERVICE = "mateai-youtube-mcp"
KEYRING_USER = "google-oauth-token"


def _use_keyring() -> bool:
    """Opt in with MATEAI_TOKEN_BACKEND=keyring; the default stays the 0600 token file."""
    return os.environ.get("MATEAI_TOKEN_BACKEND", "").strip().lower() == "keyring"


def _keyring():
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError(
            "MATEAI_TOKEN_BACKEND=keyring needs the `keyring` package: pip install keyring"
        ) from exc
    return keyring


def _keyring_get() -> str | None:
    return _keyring().get_password(KEYRING_SERVICE, KEYRING_USER)


def _keyring_set(token_json: str) -> None:
    _keyring().set_password(KEYRING_SERVICE, KEYRING_USER, token_json)


def _builtin_client_config() -> dict | None:
    """Shared Desktop client from MATEAI_OAUTH_CLIENT_ID/_SECRET (spike: env; a build would embed it)."""
    client_id = os.environ.get("MATEAI_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("MATEAI_OAUTH_CLIENT_SECRET", "").strip()
    if not (client_id and client_secret):
        return None
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def _scopes_of(info: dict) -> list[str]:
    scopes = info.get("scopes") or []
    return scopes.split(" ") if isinstance(scopes, str) else list(scopes)


def _saved_scopes(token_file: Path) -> list[str]:
    return _scopes_of(json.loads(token_file.read_text(encoding="utf-8")))


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
    use_keyring = _use_keyring()
    stored = _keyring_get() if use_keyring and not force_reauth else None
    if not force_reauth and stored:
        info = json.loads(stored)
        granted = _scopes_of(info)
        covers_request = set(scopes) <= set(granted)
        creds = Credentials.from_authorized_user_info(
            info, granted + [s for s in scopes if s not in granted]
        )
    elif not force_reauth and not use_keyring and TOKEN_FILE.exists():
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
            builtin = None if client_secret_path.exists() else _builtin_client_config()
            if builtin:
                flow = InstalledAppFlow.from_client_config(builtin, scopes)
            elif client_secret_path.exists():
                flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes)
            else:
                raise FileNotFoundError(
                    f"Missing OAuth credentials at {client_secret_path}.\n"
                    "Download an OAuth 2.0 Desktop client JSON from Google Cloud Console "
                    "and save it as client_secret.json (see README.md)."
                )
            # google-auth-oauthlib adds a PKCE code_verifier/challenge (S256) by default.
            creds = flow.run_local_server(port=0, prompt="consent")

        if use_keyring:
            _keyring_set(creds.to_json())
        else:
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            os.chmod(TOKEN_FILE, 0o600)
        with contextlib.suppress(OSError):
            _expired_marker().unlink(missing_ok=True)

    return creds


def _youtube_client(client_secret_path: Path = DEFAULT_CLIENT_SECRET, upload_scope: bool = True):
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=upload_scope)
    return build("youtube", "v3", credentials=creds)


def _youtube_and_analytics_clients(client_secret_path: Path = DEFAULT_CLIENT_SECRET):
    """YouTube Data v3 + YouTube Analytics v2 clients on one read-only credential."""
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=False)
    return build("youtube", "v3", credentials=creds), build("youtubeAnalytics", "v2", credentials=creds)
