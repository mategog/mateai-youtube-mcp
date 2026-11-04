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


if __name__ == "__main__":
    unittest.main()
