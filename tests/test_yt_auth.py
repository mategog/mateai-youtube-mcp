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
yt_auth.BUILTIN_CLIENT_FILE = Path(os.devnull) / "oauth_client.json"  # nor the real bundled Google client
# A token file as earlier versions saved it; its scopes cover every call, so expiry means refresh.
FULL_TOKEN = json.dumps({"refresh_token": "r", "scopes": yt_auth.SCOPES_WITH_UPLOAD})


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
            token.write_text(FULL_TOKEN, encoding="utf-8")
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, _fake_google_modules(creds)):
                result = yt_studio.get_oauth_credentials()
            return result, token.exists()

    def test_refresh_failure_says_how_to_sign_in_again(self):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r", granted_scopes=None)
        creds.refresh.side_effect = FakeRefreshError("invalid_grant: Token has been expired or revoked.")
        with self.assertRaises(RuntimeError) as ctx:
            self._run(creds)
        msg = str(ctx.exception)
        self.assertIn("/yt-setup", msg)
        self.assertIn("expired", msg)
        self.assertNotIn("invalid_grant", msg.split("\n")[0])

    def test_failed_refresh_keeps_the_token_file(self):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r", granted_scopes=None)
        creds.refresh.side_effect = FakeRefreshError("invalid_grant")
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text(FULL_TOKEN, encoding="utf-8")
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, _fake_google_modules(creds)):
                with self.assertRaises(RuntimeError):
                    yt_studio.get_oauth_credentials()
            self.assertTrue(token.exists())

    def test_successful_refresh_still_returns_credentials(self):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r", granted_scopes=None)
        creds.to_json.return_value = "{}"
        result, _ = self._run(creds)
        self.assertIs(result, creds)
        creds.refresh.assert_called_once()

    def _refresh_while(self, change):
        """A tool call refreshes the old login while `change(token)` runs in another process."""
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text(FULL_TOKEN, encoding="utf-8")
            creds = mock.Mock(valid=False, expired=True, refresh_token="r", granted_scopes=None)
            creds.to_json.return_value = json.dumps({"refresh_token": "r", "token": "refreshed-old"})
            creds.refresh.side_effect = lambda _: change(token)
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, _fake_google_modules(creds)):
                self.assertIs(yt_studio.get_oauth_credentials(), creds)
            return json.loads(token.read_text(encoding="utf-8")) if token.exists() else None

    def test_a_refresh_never_overwrites_a_login_saved_meanwhile_by_yt_setup_switch(self):
        new = {"refresh_token": "r-new-account", "scopes": yt_auth.SCOPES_WITH_UPLOAD}
        saved = self._refresh_while(lambda t: t.write_text(json.dumps(new), encoding="utf-8"))
        self.assertEqual(saved, new)

    def test_a_refresh_never_brings_back_a_login_deleted_meanwhile_by_yt_disconnect(self):
        self.assertIsNone(self._refresh_while(lambda t: t.unlink()))


class TestExpiredMarker(unittest.TestCase):
    """A failed refresh leaves `.tokens/expired` so /yt-setup knows the saved login is dead."""

    def _refresh_fails(self, token):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r", granted_scopes=None)
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
            token.write_text(FULL_TOKEN, encoding="utf-8")
            self._refresh_fails(token)
            self.assertTrue((token.parent / "expired").exists())

    @unittest.skipIf(os.name == "nt", "chmod cannot make a folder read-only on Windows")
    def test_marker_that_cannot_be_written_does_not_hide_the_friendly_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"
            token.parent.mkdir()
            token.write_text(FULL_TOKEN, encoding="utf-8")
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

    def test_after_yt_disconnect_a_tool_call_never_starts_a_sign_in(self):
        # With the user's own client file a tool call used to open the browser; /yt-disconnect must stick.
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"
            token.parent.mkdir()
            (token.parent / "signed_out").write_text("", encoding="utf-8")
            secret = Path(tmp) / "client_secret.json"
            secret.write_text("{}", encoding="utf-8")
            mods = _fake_google_modules(None)
            mods["google_auth_oauthlib.flow"].InstalledAppFlow = types.SimpleNamespace(
                from_client_secrets_file=mock.Mock(side_effect=AssertionError("sign-in started"))
            )
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, mods), \
                    self.assertRaisesRegex(FileNotFoundError, "/yt-setup"):
                yt_studio.get_oauth_credentials(client_secret_path=secret)

    def test_fresh_sign_in_removes_the_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"
            token.parent.mkdir()
            (token.parent / "expired").write_text("", encoding="utf-8")
            (token.parent / "signed_out").write_text("", encoding="utf-8")  # left by /yt-disconnect
            secret = Path(tmp) / "client_secret.json"
            secret.write_text("{}", encoding="utf-8")
            new_creds = mock.Mock(granted_scopes=None)
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
            self.assertFalse((token.parent / "signed_out").exists())

    def test_marker_left_behind_by_a_deleted_tokens_folder_does_not_block_sign_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / ".tokens" / "token.json"  # the folder (and its marker) is gone
            secret = Path(tmp) / "client_secret.json"
            secret.write_text("{}", encoding="utf-8")
            new_creds = mock.Mock(granted_scopes=None)
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
        self.granted_scopes = None  # set from Google's token response, like the real class
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
        self.granted_scopes = list(self.scopes)
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

    def test_upload_call_on_a_readonly_login_asks_for_consent_instead_of_refreshing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, self.READ, "FAKE-READONLY", hours_left=1)
            secret = Path(tmp) / "client_secret.json"
            secret.write_text("{}", encoding="utf-8")
            granted = FakeScopedCredentials({"token": "NEW", "refresh_token": "NEW-R",
                                             "expiry": dt.datetime.now().isoformat()}, self.UPLOAD)
            granted.granted_scopes = list(self.UPLOAD)
            flow = mock.Mock()
            flow.run_local_server.return_value = granted
            from_file = mock.Mock(return_value=flow)
            mods = _fake_google_modules(None)
            mods["google.oauth2.credentials"].Credentials = FakeScopedCredentials
            mods["google_auth_oauthlib.flow"].InstalledAppFlow = types.SimpleNamespace(
                from_client_secrets_file=from_file)
            with mock.patch.object(yt_auth, "TOKEN_FILE", path), mock.patch.dict(sys.modules, mods):
                creds = yt_auth.get_oauth_credentials(secret, upload_scope=True)
            self.assertIs(creds, granted)
            self.assertEqual(from_file.call_args.args[1], self.UPLOAD)
            saved = self._saved(path)
            self.assertEqual(set(saved["scopes"]), set(self.UPLOAD))
            self.assertEqual(saved["refresh_token"], "NEW-R")

    def test_cached_token_that_covers_the_request_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, self.UPLOAD, "FAKE-FULL", hours_left=1)
            for upload_scope in (False, True):
                creds = self._call(path, upload_scope=upload_scope)
                self.assertEqual(creds.refreshes, 0)
                self.assertEqual(creds.token, "FAKE-FULL")
            self.assertEqual(set(self._saved(path)["scopes"]), set(self.UPLOAD))


class TestGrantedScopes(unittest.TestCase):
    """The saved scopes are the ones Google granted, never just the ones we asked for."""
    READ = yt_auth.SCOPES_READONLY
    UPLOAD = yt_auth.SCOPES_WITH_UPLOAD

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.token = self.dir / ".tokens" / "token.json"
        self.secret = self.dir / "client_secret.json"
        self.secret.write_text("{}", encoding="utf-8")

    def _consent_returns(self, creds=None, error=None):
        flow = mock.Mock()
        flow.run_local_server.return_value = creds
        flow.run_local_server.side_effect = error
        mods = _fake_google_modules(None)
        mods["google_auth_oauthlib.flow"].InstalledAppFlow = types.SimpleNamespace(
            from_client_secrets_file=mock.Mock(return_value=flow))
        return mods, flow

    def _call(self, mods, **kw):
        with mock.patch.object(yt_auth, "TOKEN_FILE", self.token), mock.patch.dict(sys.modules, mods):
            return yt_auth.get_oauth_credentials(self.secret, **kw)

    def _new_creds(self, requested, granted):
        creds = mock.Mock(granted_scopes=granted)
        creds.to_json.return_value = json.dumps({"refresh_token": "r", "scopes": requested})
        return creds

    def test_refresh_saves_what_google_granted_not_what_the_file_claimed(self):
        self.token.parent.mkdir()
        self.token.write_text(json.dumps({
            "token": "OLD", "refresh_token": "r", "scopes": self.UPLOAD,
            "expiry": (dt.datetime.now() - dt.timedelta(hours=1)).isoformat()}), encoding="utf-8")
        mods = _fake_google_modules(None)
        mods["google.oauth2.credentials"].Credentials = FakeScopedCredentials
        with mock.patch.object(FakeScopedCredentials, "refresh",
                               lambda self, req: setattr(self, "granted_scopes", list(TestGrantedScopes.READ))):
            self._call(mods)
        self.assertEqual(json.loads(self.token.read_text(encoding="utf-8"))["scopes"], self.READ)

    def test_keyring_saves_granted_scopes_too(self):
        creds = self._new_creds(self.UPLOAD, self.READ)
        mods, _ = self._consent_returns(creds)
        with mock.patch.dict(os.environ, {"MATEAI_TOKEN_BACKEND": "keyring"}), \
                mock.patch.object(yt_auth, "_keyring_get", return_value=None), \
                mock.patch.object(yt_auth, "_keyring_set") as saved:
            self._call(mods, force_reauth=True)
        self.assertEqual(json.loads(saved.call_args.args[0])["scopes"], self.READ)

    def test_unticked_manage_box_gives_a_clear_error_and_saves_only_what_was_granted(self):
        mods, _ = self._consent_returns(self._new_creds(self.UPLOAD, self.READ))
        with self.assertRaises(RuntimeError) as ctx:
            self._call(mods, upload_scope=True, force_reauth=True)
        self.assertIn("'Manage your YouTube account'", str(ctx.exception))
        self.assertIn("unticked", str(ctx.exception))
        self.assertEqual(json.loads(self.token.read_text(encoding="utf-8"))["scopes"], self.READ)

    def test_oauthlib_scope_changed_warning_becomes_the_same_clear_error(self):
        warning = Warning('Scope has changed from "a" to "b".')
        warning.new_scope = list(self.READ)
        mods, _ = self._consent_returns(error=warning)
        with self.assertRaises(RuntimeError) as ctx:
            self._call(mods, upload_scope=True, force_reauth=True)
        self.assertIn("'Manage your YouTube account'", str(ctx.exception))
        self.assertFalse(self.token.exists())

    def test_desktop_launch_with_a_readonly_login_points_to_the_app_and_opens_no_browser(self):
        self.token.parent.mkdir()
        self.token.write_text(json.dumps({"token": "t", "refresh_token": "r", "scopes": self.READ}),
                              encoding="utf-8")
        mods, flow = self._consent_returns(self._new_creds(self.UPLOAD, self.UPLOAD))
        mods["google.oauth2.credentials"].Credentials = FakeScopedCredentials
        with mock.patch.dict(os.environ, {"MATEAI_LAUNCHER": "desktop"}):
            with self.assertRaisesRegex(RuntimeError, "Open MateAI Studio, disconnect YouTube"):
                self._call(mods, upload_scope=True)
        flow.run_local_server.assert_not_called()

    @unittest.skipIf(os.name == "nt", "POSIX modes")
    def test_token_folder_is_0700_and_file_is_0600(self):
        mods, _ = self._consent_returns(self._new_creds(self.READ, None))
        old = os.umask(0o022)
        try:
            self._call(mods, force_reauth=True)
        finally:
            os.umask(old)
        self.assertEqual(self.token.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.token.stat().st_mode & 0o777, 0o600)

    @unittest.skipIf(os.name == "nt", "POSIX modes")
    def test_token_file_is_never_created_world_readable(self):
        modes = []
        real_open = os.open
        def spy(path, flags, mode=0o777, *a, **k):
            modes.append(mode)
            return real_open(path, flags, mode, *a, **k)
        mods, _ = self._consent_returns(self._new_creds(self.READ, None))
        with mock.patch.object(yt_auth.os, "open", spy):
            self._call(mods, force_reauth=True)
        self.assertEqual(modes, [0o600])


class TestDesktopSignInMessages(unittest.TestCase):
    """Launched by MateAI Studio (MATEAI_LAUNCHER=desktop), the fix is the app's Connect YouTube button."""

    def _refresh_error(self, launcher):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r", granted_scopes=None)
        creds.refresh.side_effect = FakeRefreshError("invalid_grant")
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text(FULL_TOKEN, encoding="utf-8")
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
        self.assertIn("open MateAI Studio and click Connect YouTube", msg)
        self.assertIn("7 days", msg)
        self.assertNotIn("/yt-setup", msg)
        self.assertNotIn("yt_studio.py", msg)

    def test_expired_login_message_unchanged_for_plugin_users(self):
        msg = self._refresh_error("")
        self.assertIn("type /yt-setup in Claude Code, or run `python3 yt_studio.py setup`.", msg)
        self.assertNotIn("MateAI Studio", msg)

    def test_expired_login_from_the_builtin_client_does_not_blame_testing_mode(self):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r", granted_scopes=None, client_id="shared-id")
        creds.refresh.side_effect = FakeRefreshError("invalid_grant")
        env = {"MATEAI_OAUTH_CLIENT_ID": "shared-id", "MATEAI_OAUTH_CLIENT_SECRET": "shared-sec"}
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text(FULL_TOKEN, encoding="utf-8")
            with mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.dict(sys.modules, _fake_google_modules(creds)), \
                    mock.patch.dict(os.environ, env):
                with self.assertRaises(RuntimeError) as ctx:
                    yt_studio.get_oauth_credentials()
        self.assertIn("/yt-setup", str(ctx.exception))
        self.assertNotIn("7 days", str(ctx.exception))

    def test_no_login_points_desktop_users_to_the_app(self):
        msg = self._no_login_error("desktop")
        self.assertIn("Open MateAI Studio and click Connect YouTube", msg)
        self.assertNotIn("client_secret", msg)

    def test_no_login_message_unchanged_for_plugin_users(self):
        msg = self._no_login_error("")
        self.assertIn("client_secret.json", msg)
        self.assertNotIn("MateAI Studio", msg)


if __name__ == "__main__":
    unittest.main()
