import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yt_auth

TOKEN_INFO = {"token": "a", "refresh_token": "r", "client_id": "cid", "client_secret": "sec",
              "scopes": yt_auth.SCOPES_READONLY}


def _google_modules(creds, flow_cls=object):
    """Stand-ins for the Google libraries; from_authorized_user_info returns `creds`."""
    mods = {}
    for name in (
        "google", "google.auth", "google.auth.transport", "google.auth.transport.requests",
        "google.auth.exceptions", "google.oauth2", "google.oauth2.credentials",
        "google_auth_oauthlib", "google_auth_oauthlib.flow",
    ):
        mods[name] = types.ModuleType(name)
    mods["google.auth.transport.requests"].Request = object
    mods["google.auth.exceptions"].RefreshError = Exception
    mods["google.oauth2.credentials"].Credentials = types.SimpleNamespace(
        from_authorized_user_file=lambda *a, **k: creds,
        from_authorized_user_info=mock.Mock(return_value=creds),
    )
    mods["google_auth_oauthlib.flow"].InstalledAppFlow = flow_cls
    return mods


class TestKeyringBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.token_file = Path(self.tmp.name) / ".tokens" / "token.json"
        self.env = mock.patch.dict(os.environ, {"MATEAI_TOKEN_BACKEND": "keyring"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _call(self, mods, **kw):
        with mock.patch.object(yt_auth, "TOKEN_FILE", self.token_file), \
                mock.patch.dict(sys.modules, mods):
            return yt_auth.get_oauth_credentials(**kw)

    def test_stored_token_is_read_from_keyring_not_the_file(self):
        creds = mock.Mock(valid=True)
        mods = _google_modules(creds)
        with mock.patch.object(yt_auth, "_keyring_get", return_value=json.dumps(TOKEN_INFO)):
            result = self._call(mods)
        self.assertIs(result, creds)
        mods["google.oauth2.credentials"].Credentials.from_authorized_user_info.assert_called_once()
        self.assertFalse(self.token_file.exists())

    def test_refreshed_token_is_saved_to_keyring_and_no_file_is_written(self):
        creds = mock.Mock(valid=False, expired=True, refresh_token="r")
        creds.to_json.return_value = '{"token": "new"}'
        with mock.patch.object(yt_auth, "_keyring_get", return_value=json.dumps(TOKEN_INFO)), \
                mock.patch.object(yt_auth, "_keyring_set") as saved:
            self._call(_google_modules(creds))
        creds.refresh.assert_called_once()
        saved.assert_called_once_with('{"token": "new"}')
        self.assertFalse(self.token_file.exists())

    def test_builtin_client_is_used_when_no_client_file_exists(self):
        creds = mock.Mock(valid=True)
        creds.to_json.return_value = "{}"
        flow = mock.Mock()
        flow.run_local_server.return_value = creds
        flow_cls = types.SimpleNamespace(
            from_client_config=mock.Mock(return_value=flow),
            from_client_secrets_file=mock.Mock(side_effect=AssertionError("file flow used")),
        )
        env = {"MATEAI_OAUTH_CLIENT_ID": "shared-id", "MATEAI_OAUTH_CLIENT_SECRET": "shared-sec"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(yt_auth, "_keyring_get", return_value=None), \
                mock.patch.object(yt_auth, "_keyring_set") as saved:
            self._call(_google_modules(creds, flow_cls), client_secret_path=Path(self.tmp.name) / "none.json")
        config, scopes = flow_cls.from_client_config.call_args.args
        self.assertEqual(config["installed"]["client_id"], "shared-id")
        self.assertEqual(scopes, yt_auth.SCOPES_READONLY)
        flow.run_local_server.assert_called_once_with(port=0, prompt="consent")
        saved.assert_called_once_with("{}")

    def test_a_users_own_client_file_wins_over_the_builtin_client(self):
        secret = Path(self.tmp.name) / "client_secret.json"
        secret.write_text("{}", encoding="utf-8")
        creds = mock.Mock(valid=True)
        creds.to_json.return_value = "{}"
        flow = mock.Mock()
        flow.run_local_server.return_value = creds
        flow_cls = types.SimpleNamespace(
            from_client_config=mock.Mock(side_effect=AssertionError("builtin used")),
            from_client_secrets_file=mock.Mock(return_value=flow),
        )
        env = {"MATEAI_OAUTH_CLIENT_ID": "shared-id", "MATEAI_OAUTH_CLIENT_SECRET": "shared-sec"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(yt_auth, "_keyring_get", return_value=None), \
                mock.patch.object(yt_auth, "_keyring_set"):
            self._call(_google_modules(creds, flow_cls), client_secret_path=secret)
        flow_cls.from_client_secrets_file.assert_called_once()

    def test_no_token_and_no_client_raises_the_existing_error(self):
        creds = mock.Mock(valid=True)
        env = {"MATEAI_OAUTH_CLIENT_ID": "", "MATEAI_OAUTH_CLIENT_SECRET": ""}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(yt_auth, "_keyring_get", return_value=None):
            with self.assertRaises(FileNotFoundError):
                self._call(_google_modules(creds), client_secret_path=Path(self.tmp.name) / "none.json")

    def test_missing_keyring_package_gives_a_clear_error(self):
        with mock.patch.dict(sys.modules, {"keyring": None}):
            with self.assertRaisesRegex(RuntimeError, "pip install keyring"):
                yt_auth._keyring_get()


class TestDefaultBackendUnchanged(unittest.TestCase):
    def test_without_the_env_var_the_keyring_is_never_touched(self):
        creds = mock.Mock(valid=True)
        mods = _google_modules(creds)
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text(json.dumps(TOKEN_INFO), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k != "MATEAI_TOKEN_BACKEND"}
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(yt_auth, "TOKEN_FILE", token), \
                    mock.patch.object(yt_auth, "_keyring_get", side_effect=AssertionError("keyring touched")), \
                    mock.patch.dict(sys.modules, mods):
                self.assertIs(yt_auth.get_oauth_credentials(), creds)


if __name__ == "__main__":
    unittest.main()
