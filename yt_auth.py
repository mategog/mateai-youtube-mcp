"""
mateai-youtube-mcp — OAuth2 credentials and authenticated YouTube client
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
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


# The desktop app sets its own service name: macOS refuses to let one program overwrite a Keychain
# item another program created (error -25244), so each program family keeps its own item.
KEYRING_SERVICE = os.environ.get("MATEAI_KEYRING_SERVICE") or "mateai-youtube-mcp"
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


# The verified MateAI Studio Desktop client, shipped with the plugin in Google's "Download JSON" format.
BUILTIN_CLIENT_FILE = yt_common.HERE / "oauth_client.json"


def _builtin_client_config() -> dict | None:
    """Shared Desktop client: MATEAI_OAUTH_CLIENT_ID/_SECRET if set, else the bundled oauth_client.json.

    None when neither gives a client_id and client_secret (file missing or not a Desktop client)."""
    client_id = os.environ.get("MATEAI_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("MATEAI_OAUTH_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
    try:
        data = json.loads(BUILTIN_CLIENT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    installed = data.get("installed") if isinstance(data, dict) else None
    if isinstance(installed, dict) and installed.get("client_id") and installed.get("client_secret"):
        return {"installed": installed}
    return None


def _scopes_of(info: dict) -> list[str]:
    scopes = info.get("scopes") or []
    return scopes.split(" ") if isinstance(scopes, str) else list(scopes)


def _saved_scopes(token_file: Path) -> list[str]:
    return _scopes_of(json.loads(token_file.read_text(encoding="utf-8")))


def _saved_refresh_token() -> str | None:
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8")).get("refresh_token")
    except (OSError, ValueError, AttributeError):
        return None


def _has_own_token() -> bool:
    """A readable token file; an empty or corrupt one must not hide a working MateAI Studio login."""
    try:
        _saved_scopes(TOKEN_FILE)
        return True
    except (OSError, ValueError, AttributeError):
        return False


def _launched_by_desktop() -> bool:
    """MateAI Studio sets MATEAI_LAUNCHER=desktop in the MCP entry it writes; its users sign in there."""
    return os.environ.get("MATEAI_LAUNCHER", "").strip().lower() == "desktop"


# MateAI Studio's login (macOS Keychain). The plugin falls back to it when it has no login of its own
# (/yt-setup makes one, for any account the user picks), so one Connect in Studio covers both. Read-only:
# macOS won't let this program overwrite the app's item, so refreshed access tokens are kept in memory only.
DESKTOP_KEYCHAIN_SERVICE = "dev.mateai.desktop"
_desktop_cache = None  # Credentials refreshed from the app's login, reused while valid


def _desktop_login() -> dict | None:
    """MateAI Studio's saved login, or None (not macOS, no app login, access denied, turned off with
    MATEAI_DESKTOP_LOGIN=off, signed out with /yt-disconnect, or we are the app's own MCP)."""
    off = os.environ.get("MATEAI_DESKTOP_LOGIN", "").strip().lower() in ("off", "0", "false")
    if off or sys.platform != "darwin" or _use_keyring() or _launched_by_desktop() or _signed_out_marker().exists():
        return None
    try:
        # The first read shows a macOS prompt ("security wants to use ... dev.mateai.desktop"): Always Allow.
        out = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", DESKTOP_KEYCHAIN_SERVICE,
             "-a", KEYRING_USER, "-w"],
            capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
        )
        info = json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return info if isinstance(info, dict) and info.get("refresh_token") else None


def _desktop_credentials(info, scopes, Credentials, Request, RefreshError):
    global _desktop_cache
    granted = _scopes_of(info)
    if not set(scopes) <= set(granted):
        raise RuntimeError(
            "YouTube is connected through MateAI Studio, but only for reading. To upload or edit, "
            "open MateAI Studio, disconnect YouTube and connect again with managing videos allowed."
        )
    cached = _desktop_cache
    if cached is not None and cached.refresh_token == info["refresh_token"] and cached.valid:
        return cached
    creds = Credentials.from_authorized_user_info(info, granted)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise RuntimeError(
                "Your YouTube login in MateAI Studio expired or was revoked, so Google refused to "
                "renew it. Open MateAI Studio and click Connect YouTube; this plugin uses that login."
                f"\nDetails: {exc}"
            ) from exc
    _desktop_cache = creds
    return creds


def has_login() -> bool:
    """A saved login exists: this plugin's token file or MateAI Studio's."""
    return TOKEN_FILE.exists() or _desktop_login() is not None


def _expired_marker() -> Path:
    """`.tokens/expired`: left by a failed refresh so /yt-setup knows the saved login is dead."""
    return TOKEN_FILE.with_name("expired")


def _signed_out_marker() -> Path:
    """`.tokens/signed_out`: left by /yt-disconnect so the plugin stays signed out, instead of falling
    back to MateAI Studio's login, until the next sign-in."""
    return TOKEN_FILE.with_name("signed_out")


def _sign_in_again() -> str:
    return (
        "Sign in again: open MateAI Studio and click Connect YouTube."
        if _launched_by_desktop()
        else "Sign in again: type /yt-setup in Claude Code, or run `python3 yt_studio.py setup`."
    )


# The wording Google's consent screen shows for each scope, so the error names the box to tick.
_SCOPE_LABELS = {
    "https://www.googleapis.com/auth/youtube.readonly": "View your YouTube account",
    "https://www.googleapis.com/auth/yt-analytics.readonly": "View YouTube Analytics reports for your YouTube content",
    "https://www.googleapis.com/auth/youtube.force-ssl": "Manage your YouTube account",
}


def _missing_scopes_message(needed, granted) -> str:
    missing = ", ".join(f"'{_SCOPE_LABELS.get(s, s)}'" for s in needed if s not in set(granted))
    return (
        f"Google didn't grant {missing}: you unticked it on Google's consent screen. "
        f"{_sign_in_again()} Keep it ticked this time."
    )


def _token_json(creds) -> str:
    """to_json() records the scopes we asked for; save the ones Google says it granted instead."""
    if not creds.granted_scopes:
        return creds.to_json()
    info = json.loads(creds.to_json())
    info["scopes"] = list(creds.granted_scopes)
    return json.dumps(info)


def _write_private(path: Path, text: str) -> None:
    """Folder 0700, file 0600 from the moment it exists (both are mostly no-ops on Windows)."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)  # O_CREAT's mode doesn't touch a file that already existed


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
            f"  python3 -m venv .venv && {Path('.venv', 'Scripts' if yt_common.IS_WINDOWS else 'bin', 'pip')} "
            "install -r requirements.txt"
        ) from exc

    scopes = SCOPES_WITH_UPLOAD if upload_scope else SCOPES_READONLY
    # The plugin's own login (made by /yt-setup) wins, so the user can pick another account than Studio's.
    desktop = None if force_reauth or _has_own_token() else _desktop_login()
    if desktop is not None:
        return _desktop_credentials(desktop, scopes, Credentials, Request, RefreshError)
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
        if not covers_request and _launched_by_desktop():
            raise RuntimeError(
                "Your YouTube login doesn't allow this yet (it was connected for reading only). "
                "Open MateAI Studio, disconnect YouTube and connect again with managing videos allowed."
            )
        # A refresh can't add scopes the user never granted, so a missing scope always means consent.
        if not force_reauth and creds and creds.expired and covers_request and creds.refresh_token:
            loaded_refresh_token = creds.refresh_token
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                with contextlib.suppress(OSError):
                    _expired_marker().write_text("", encoding="utf-8")
                # The 7-day limit applies to a user's own unverified client, not the verified built-in one.
                builtin = _builtin_client_config()
                own_client = not (builtin and creds.client_id == builtin["installed"]["client_id"])
                testing_note = " (Google ends logins after 7 days for apps in 'Testing' mode.)" if own_client else ""
                raise RuntimeError(
                    "Your YouTube login expired or was revoked, so Google refused to renew it. "
                    f"{_sign_in_again()}{testing_note}\nDetails: {exc}"
                ) from exc
            # /yt-setup switch or /yt-disconnect may have replaced or deleted the file while this
            # refresh ran (another process): use the refreshed login for this call, but don't save it back.
            # shortcut: the keyring backend has no such check; add one if it ever gets a switch.
            if not use_keyring and _saved_refresh_token() != loaded_refresh_token:
                return creds
        else:
            builtin = None if client_secret_path.exists() else _builtin_client_config()
            if builtin and force_reauth:
                flow = InstalledAppFlow.from_client_config(builtin, scopes)
            elif client_secret_path.exists() and (force_reauth or not _signed_out_marker().exists()):
                flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes)
            elif _launched_by_desktop():
                raise FileNotFoundError("YouTube isn't connected yet. Open MateAI Studio and click Connect YouTube.")
            elif builtin or client_secret_path.exists():
                # Only setup (force_reauth) starts a browser sign-in with the built-in client, or after
                # /yt-disconnect: started from a tool call it would block the single-threaded MCP server
                # until someone clicks Allow, and would undo the sign-out.
                raise FileNotFoundError(
                    "YouTube sign-in needed. Type /yt-setup in Claude Code, or run `python3 yt_studio.py setup`."
                )
            else:
                raise FileNotFoundError(
                    f"Missing OAuth credentials at {client_secret_path}.\n"
                    "Download an OAuth 2.0 Desktop client JSON from Google Cloud Console "
                    "and save it as client_secret.json (see README.md)."
                )
            # google-auth-oauthlib adds a PKCE code_verifier/challenge (S256) by default.
            # select_account: always show Google's account chooser instead of reusing the last account.
            try:
                creds = flow.run_local_server(port=0, prompt="select_account consent")
            except Warning as exc:  # oauthlib: "Scope has changed", i.e. the user unticked a box
                if not hasattr(exc, "new_scope"):
                    raise
                raise RuntimeError(_missing_scopes_message(scopes, exc.new_scope or [])) from exc

        token_json = _token_json(creds)
        if use_keyring:
            _keyring_set(token_json)
        else:
            _write_private(TOKEN_FILE, token_json)
        for marker in (_expired_marker(), _signed_out_marker()):
            with contextlib.suppress(OSError):
                marker.unlink(missing_ok=True)
        if creds.granted_scopes and not set(scopes) <= set(creds.granted_scopes):
            raise RuntimeError(_missing_scopes_message(scopes, creds.granted_scopes))

    return creds


REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def _revoke_at_google(token: str) -> bool:
    """True only when Google answers 200; the token goes in the POST body, never the URL."""
    import urllib.parse
    import urllib.request

    req = urllib.request.Request(
        REVOKE_URL,
        data=urllib.parse.urlencode({"token": token}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=yt_common.SSL_CONTEXT) as resp:
            return resp.status == 200
    except OSError:  # offline, or HTTPError (a URLError subclass) for an already-invalid token
        return False


def disconnect(revoke: bool = True) -> dict:
    """Revoke this plugin's saved login at Google (best effort), then delete it locally either way.

    revoke=False only deletes it: the built-in client is MateAI Studio's, and Google revokes the whole
    user+client grant, so revoking here would also sign Studio out. client_secret.json is left alone.
    Either way the plugin stays signed out (no fallback to Studio's login) until the next sign-in."""
    _write_private(_signed_out_marker(), "")  # first: if this fails, nothing was disconnected
    use_keyring = _use_keyring()
    has_file = not use_keyring and TOKEN_FILE.exists()
    stored = _keyring_get() if use_keyring else (TOKEN_FILE.read_text(encoding="utf-8") if has_file else None)
    revoked = False
    if stored and revoke:
        try:
            info = json.loads(stored)
            token = info.get("refresh_token") or info.get("token")
        except (ValueError, AttributeError):
            token = None  # unreadable token file: nothing to revoke, still delete it
        if token:
            revoked = _revoke_at_google(token)
    if use_keyring and stored:
        _keyring().delete_password(KEYRING_SERVICE, KEYRING_USER)
    elif has_file:
        TOKEN_FILE.unlink(missing_ok=True)  # even an empty file, or it would count as a login
    _expired_marker().unlink(missing_ok=True)
    return {"had_login": has_file or bool(stored), "revoked": revoked}


def _quota_kwargs() -> dict:
    """Count Data API calls for MateAI Studio's quota meter; plugin users (who also have MATEAI_YT_HOME) skip it."""
    if not _launched_by_desktop():
        return {}
    import yt_quota

    return {"requestBuilder": yt_quota.CountingRequest}


def _youtube_client(client_secret_path: Path = DEFAULT_CLIENT_SECRET, upload_scope: bool = True):
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=upload_scope)
    return build("youtube", "v3", credentials=creds, **_quota_kwargs())


def _youtube_and_analytics_clients(client_secret_path: Path = DEFAULT_CLIENT_SECRET):
    """YouTube Data v3 + YouTube Analytics v2 clients on one read-only credential."""
    from googleapiclient.discovery import build

    creds = get_oauth_credentials(client_secret_path, upload_scope=False)
    return build("youtube", "v3", credentials=creds, **_quota_kwargs()), build("youtubeAnalytics", "v2", credentials=creds)
