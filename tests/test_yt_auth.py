import datetime as dt
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yt_auth
import yt_studio

os.environ["MATEAI_DESKTOP_LOGIN"] = "off"  # never read the real MateAI Studio login in tests


class FakeRefreshError(Exception):
    pass


def _fake_google_modules(creds):
    """Stand-ins for the Google auth libraries so the test needs no pip install."""
    mods = {}
    for name in (
        "google", "google.auth", "google.auth.transport", "google.auth.transport.requests",
        "google.auth.exceptions", "google.oauth2", "google.oauth2.credentials",
        "google_auth_oauthlib", "google_auth_oauthlib.flow",
    ):
        mods[name] = types.ModuleType(name)
    mods["google.auth.transport.requests"].Request = object
    mods["google.auth.exceptions"].RefreshError = FakeRefreshError
    mods["google.oauth2.credentials"].Credentials = types.SimpleNamespace(
        from_authorized_user_file=lambda *a, **k: creds
    )
    mods["google_auth_oauthlib.flow"].InstalledAppFlow = object
    return mods


class TestExpiredLogin(unittest.TestCase):
    def _run(self, creds):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text("{}", encoding="utf-8")
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, _fake_google_modules(creds)):
                result = yt_studio.get_oauth_credentials()
            return result, token.exists()

    def test_refresh_failure_says_how_to_sign_in_again(self):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r")
        creds.refresh.side_effect = FakeRefreshError("invalid_grant: Token has been expired or revoked.")
        with self.assertRaises(RuntimeError) as ctx:
            self._run(creds)
        msg = str(ctx.exception)
        self.assertIn("/yt-setup", msg)
        self.assertIn("expired", msg)
        self.assertNotIn("invalid_grant", msg.split("\n")[0])

    def test_failed_refresh_keeps_the_token_file(self):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r")
        creds.refresh.side_effect = FakeRefreshError("invalid_grant")
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text("{}", encoding="utf-8")
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, _fake_google_modules(creds)):
                with self.assertRaises(RuntimeError):
                    yt_studio.get_oauth_credentials()
            self.assertTrue(token.exists())

    def test_successful_refresh_still_returns_credentials(self):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r")
        creds.to_json.return_value = "{}"
        result, _ = self._run(creds)
        self.assertIs(result, creds)
        creds.refresh.assert_called_once()


class TestExpiredMarker(unittest.TestCase):
    """A failed refresh leaves `.tokens/expired` so /yt-setup knows the saved login is dead."""

    def _refresh_fails(self, token):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r")
        creds.refresh.side_effect = FakeRefreshError("invalid_grant")
        with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                mock.patch.dict(sys.modules, _fake_google_modules(creds)):
            with self.assertRaises(RuntimeError) as ctx:
                yt_studio.get_oauth_credentials()
        return str(ctx.exception)

    def test_failed_refresh_writes_the_marker_next_to_the_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"
            token.parent.mkdir()
            token.write_text("{}", encoding="utf-8")
            self._refresh_fails(token)
            self.assertTrue((token.parent / "expired").exists())

    @unittest.skipIf(os.name == "nt", "chmod cannot make a folder read-only on Windows")
    def test_marker_that_cannot_be_written_does_not_hide_the_friendly_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"
            token.parent.mkdir()
            token.write_text("{}", encoding="utf-8")
            token.parent.chmod(0o500)
            try:
                msg = self._refresh_fails(token)
            finally:
                token.parent.chmod(0o700)
            self.assertIn("/yt-setup", msg)

    def test_successful_refresh_removes_the_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"
            token.parent.mkdir()
            token.write_text(json.dumps({
                "token": "FAKE-OLD", "refresh_token": "FAKE-REFRESH",
                "scopes": yt_studio.SCOPES_READONLY,
                "expiry": (dt.datetime.now() - dt.timedelta(hours=2)).isoformat(),
            }), encoding="utf-8")
            (token.parent / "expired").write_text("", encoding="utf-8")
            mods = _fake_google_modules(None)
            mods["google.oauth2.credentials"].Credentials = FakeScopedCredentials
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, mods):
                yt_studio.get_oauth_credentials()
            self.assertFalse((token.parent / "expired").exists())

    def test_fresh_sign_in_removes_the_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"
            token.parent.mkdir()
            (token.parent / "expired").write_text("", encoding="utf-8")
            secret = Path(tmp) / "client_secret.json"
            secret.write_text("{}", encoding="utf-8")
            new_creds = mock.Mock()
            new_creds.to_json.return_value = "{}"
            flow = mock.Mock()
            flow.run_local_server.return_value = new_creds
            mods = _fake_google_modules(None)
            mods["google_auth_oauthlib.flow"].InstalledAppFlow = types.SimpleNamespace(
                from_client_secrets_file=lambda *a, **k: flow
            )
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, mods):
                yt_studio.get_oauth_credentials(client_secret_path=secret, force_reauth=True)
            self.assertTrue(token.exists())
            self.assertFalse((token.parent / "expired").exists())

    def test_marker_left_behind_by_a_deleted_tokens_folder_does_not_block_sign_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"  # the folder (and its marker) is gone
            secret = Path(tmp) / "client_secret.json"
            secret.write_text("{}", encoding="utf-8")
            new_creds = mock.Mock()
            new_creds.to_json.return_value = "{}"
            flow = mock.Mock()
            flow.run_local_server.return_value = new_creds
            mods = _fake_google_modules(None)
            mods["google_auth_oauthlib.flow"].InstalledAppFlow = types.SimpleNamespace(
                from_client_secrets_file=lambda *a, **k: flow
            )
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, mods):
                yt_studio.get_oauth_credentials(client_secret_path=secret)
            self.assertTrue(token.exists())


class FakeScopedCredentials:
    """Mirrors google.oauth2.credentials.Credentials (google-auth 2.62): token and expiry come from
    the file, `scopes` come from the caller when given, `valid` ignores scopes, `to_json` writes
    `self.scopes`, and a refresh mints a token for exactly `self.scopes`."""

    def __init__(self, info, scopes):
        self.token = info.get("token")
        self.refresh_token = info.get("refresh_token")
        self.expiry = dt.datetime.fromisoformat(info["expiry"]) if info.get("expiry") else None
        self.scopes = scopes if scopes is not None else info.get("scopes")
        self.refreshes = 0

    @classmethod
    def from_authorized_user_file(cls, filename, scopes=None):
        return cls(json.loads(Path(filename).read_text(encoding="utf-8")), scopes)

    @property
    def expired(self):
        return self.expiry is not None and self.expiry <= dt.datetime.now()

    @property
    def valid(self):
        return self.token is not None and not self.expired

    def refresh(self, request):
        self.refreshes += 1
        self.token = "FAKE-TOKEN-FOR " + " ".join(sorted(self.scopes))
        self.expiry = dt.datetime.now() + dt.timedelta(hours=1)

    def to_json(self):
        return json.dumps({
            "token": self.token, "refresh_token": self.refresh_token,
            "scopes": self.scopes, "expiry": self.expiry.isoformat(),
        })


class TestScopesSurviveReadCalls(unittest.TestCase):
    READ = yt_studio.SCOPES_READONLY
    UPLOAD = yt_studio.SCOPES_WITH_UPLOAD

    def _call(self, token_path, upload_scope):
        mods = _fake_google_modules(None)
        mods["google.oauth2.credentials"].Credentials = FakeScopedCredentials
        with mock.patch.object(yt_auth, "TOKEN_FILE", token_path), \
                mock.patch.dict(sys.modules, mods):
            return yt_studio.get_oauth_credentials(upload_scope=upload_scope)

    def _write(self, tmp, scopes, token, hours_left):
        path = Path(tmp) / "token.json"
        expiry = dt.datetime.now() + dt.timedelta(hours=hours_left)
        path.write_text(json.dumps({
            "token": token, "refresh_token": "FAKE-REFRESH", "scopes": scopes,
            "expiry": expiry.isoformat(),
        }), encoding="utf-8")
        return path

    def _saved(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_read_call_after_expiry_then_upload_call_gets_an_upload_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, self.UPLOAD, "FAKE-OLD", hours_left=-2)
            self._call(path, upload_scope=False)
            saved = self._saved(path)
            self.assertEqual(set(saved["scopes"]), set(self.UPLOAD))
            self.assertEqual(saved["refresh_token"], "FAKE-REFRESH")
            creds = self._call(path, upload_scope=True)
            for scope in self.UPLOAD:
                self.assertIn(scope, creds.token)

    def test_upload_call_does_not_reuse_a_cached_readonly_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, self.READ, "FAKE-READONLY", hours_left=1)
            creds = self._call(path, upload_scope=True)
            self.assertEqual(creds.refreshes, 1)
            for scope in self.UPLOAD:
                self.assertIn(scope, creds.token)
            saved = self._saved(path)
            self.assertEqual(set(saved["scopes"]), set(self.UPLOAD))
            self.assertEqual(saved["refresh_token"], "FAKE-REFRESH")

    def test_cached_token_that_covers_the_request_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, self.UPLOAD, "FAKE-FULL", hours_left=1)
            for upload_scope in (False, True):
                creds = self._call(path, upload_scope=upload_scope)
                self.assertEqual(creds.refreshes, 0)
                self.assertEqual(creds.token, "FAKE-FULL")
            self.assertEqual(set(self._saved(path)["scopes"]), set(self.UPLOAD))


class TestDesktopSignInMessages(unittest.TestCase):
    """Launched by MateAI Desktop (MATEAI_LAUNCHER=desktop), the fix is the app's Connect YouTube button."""

    def _refresh_error(self, launcher):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r")
        creds.refresh.side_effect = FakeRefreshError("invalid_grant")
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text("{}", encoding="utf-8")
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, _fake_google_modules(creds)), \
                    mock.patch.dict(os.environ, {"MATEAI_LAUNCHER": launcher}):
                with self.assertRaises(RuntimeError) as ctx:
                    yt_studio.get_oauth_credentials()
        return str(ctx.exception)

    def _no_login_error(self, launcher):
        env = {"MATEAI_LAUNCHER": launcher, "MATEAI_OAUTH_CLIENT_ID": "", "MATEAI_OAUTH_CLIENT_SECRET": ""}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(yt_auth, "TOKEN_FILE", Path(tmp) / "token.json"), \
                    mock.patch.dict(sys.modules, _fake_google_modules(None)), \
                    mock.patch.dict(os.environ, env):
                with self.assertRaises(FileNotFoundError) as ctx:
                    yt_auth.get_oauth_credentials(Path(tmp) / "client_secret.json")
        return str(ctx.exception)

    def test_expired_login_points_desktop_users_to_the_app(self):
        msg = self._refresh_error("desktop")
        self.assertIn("open MateAI Desktop and click Connect YouTube", msg)
        self.assertIn("7 days", msg)
        self.assertNotIn("/yt-setup", msg)
        self.assertNotIn("yt_studio.py", msg)

    def test_expired_login_message_unchanged_for_plugin_users(self):
        msg = self._refresh_error("")
        self.assertIn("type /yt-setup in Claude Code, or run `python3 yt_studio.py setup`.", msg)
        self.assertNotIn("MateAI Desktop", msg)

    def test_no_login_points_desktop_users_to_the_app(self):
        msg = self._no_login_error("desktop")
        self.assertIn("Open MateAI Desktop and click Connect YouTube", msg)
        self.assertNotIn("client_secret", msg)

    def test_no_login_message_unchanged_for_plugin_users(self):
        msg = self._no_login_error("")
        self.assertIn("client_secret.json", msg)
        self.assertNotIn("MateAI Desktop", msg)


if __name__ == "__main__":
    unittest.main()
