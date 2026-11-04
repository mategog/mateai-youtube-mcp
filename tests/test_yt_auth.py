import datetime as dt
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yt_studio


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
            with mock.patch.object(yt_studio, "TOKEN_FILE", token), \
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
            with mock.patch.object(yt_studio, "TOKEN_FILE", token), \
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
        with mock.patch.object(yt_studio, "TOKEN_FILE", token_path), \
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


if __name__ == "__main__":
    unittest.main()
