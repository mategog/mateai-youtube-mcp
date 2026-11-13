import io
import json
import os
import tempfile
import types
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

import yt_auth


def _google(status=200, error=None):
    """Fake urlopen: records each request, answers `status` or raises `error`."""
    calls = []

    def urlopen(req, timeout=None, context=None):
        calls.append(req)
        if error:
            raise error
        return mock.MagicMock(__enter__=lambda s: types.SimpleNamespace(status=status))

    return urlopen, calls


class TestDisconnect(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.token = Path(tmp.name) / ".tokens" / "token.json"
        self.token.parent.mkdir()
        self.secret = Path(tmp.name) / "google_auth_secret" / "client_secret.json"
        self.secret.parent.mkdir()
        self.secret.write_text("{}", encoding="utf-8")
        patcher = mock.patch.object(yt_auth, "TOKEN_FILE", self.token)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {"MATEAI_TOKEN_BACKEND": ""})
        env.start()
        self.addCleanup(env.stop)

    def _run(self, revoke=True, **google):
        urlopen, calls = _google(**google)
        with mock.patch("urllib.request.urlopen", urlopen):
            return yt_auth.disconnect(revoke), calls

    def test_nothing_connected_revokes_nothing(self):
        result, calls = self._run()
        self.assertEqual(result, {"had_login": False, "revoked": False})
        self.assertEqual(calls, [])

    def test_revokes_refresh_token_in_body_then_deletes_login(self):
        self.token.write_text(json.dumps({"refresh_token": "r1", "token": "a1"}), encoding="utf-8")
        (self.token.parent / "expired").write_text("", encoding="utf-8")
        result, calls = self._run(status=200)
        self.assertEqual(result, {"had_login": True, "revoked": True})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].full_url, yt_auth.REVOKE_URL)  # token not in the URL
        self.assertEqual(urllib.parse.parse_qs(calls[0].data.decode()), {"token": ["r1"]})
        self.assertFalse(self.token.exists())
        self.assertFalse((self.token.parent / "expired").exists())
        self.assertTrue(self.secret.exists())  # the user's own client file stays

    def test_falls_back_to_access_token(self):
        self.token.write_text(json.dumps({"token": "a1"}), encoding="utf-8")
        _, calls = self._run(status=200)
        self.assertEqual(urllib.parse.parse_qs(calls[0].data.decode()), {"token": ["a1"]})

    def test_failed_revoke_still_deletes_login(self):
        bad = urllib.error.HTTPError(yt_auth.REVOKE_URL, 400, "invalid_token", {}, io.BytesIO())
        for google in ({"error": bad}, {"error": urllib.error.URLError("offline")}):
            self.token.write_text(json.dumps({"refresh_token": "r"}), encoding="utf-8")
            result, _ = self._run(**google)
            self.assertEqual(result, {"had_login": True, "revoked": False})
            self.assertFalse(self.token.exists())

    def test_unreadable_token_file_is_still_deleted(self):
        self.token.write_text("not json", encoding="utf-8")
        result, calls = self._run()
        self.assertEqual(result, {"had_login": True, "revoked": False})
        self.assertEqual(calls, [])
        self.assertFalse(self.token.exists())

    def test_empty_token_file_is_deleted(self):
        self.token.write_text("", encoding="utf-8")
        result, calls = self._run()
        self.assertEqual(result, {"had_login": True, "revoked": False})
        self.assertEqual(calls, [])
        self.assertFalse(self.token.exists())

    def test_revoke_false_deletes_without_calling_google(self):
        self.token.write_text(json.dumps({"refresh_token": "r"}), encoding="utf-8")
        result, calls = self._run(revoke=False, status=200)
        self.assertEqual(result, {"had_login": True, "revoked": False})
        self.assertEqual(calls, [])
        self.assertFalse(self.token.exists())

    def test_leaves_the_plugin_signed_out_so_it_cannot_fall_back_to_mateai_studio(self):
        self.token.write_text(json.dumps({"refresh_token": "r"}), encoding="utf-8")
        self._run(revoke=False)
        self.assertTrue((self.token.parent / "signed_out").exists())

    def test_signs_out_without_a_login_of_its_own(self):
        self.token.parent.rmdir()  # only MateAI Studio's login was in use: no .tokens folder yet
        result, _ = self._run(revoke=False)
        self.assertEqual(result, {"had_login": False, "revoked": False})
        self.assertTrue((self.token.parent / "signed_out").exists())

    def test_if_the_signed_out_marker_cannot_be_written_nothing_is_disconnected(self):
        self.token.write_text(json.dumps({"refresh_token": "r"}), encoding="utf-8")
        urlopen, calls = _google(status=200)
        with mock.patch("urllib.request.urlopen", urlopen), \
                mock.patch.object(yt_auth, "_write_private", side_effect=OSError("read-only")), \
                self.assertRaises(OSError):
            yt_auth.disconnect()
        self.assertEqual(calls, [])
        self.assertTrue(self.token.exists())

    def test_keyring_backend_deletes_the_keyring_entry(self):
        fake = types.SimpleNamespace(delete_password=mock.Mock())
        with mock.patch.dict(os.environ, {"MATEAI_TOKEN_BACKEND": "keyring"}), \
                mock.patch.object(yt_auth, "_keyring_get", return_value=json.dumps({"refresh_token": "r"})), \
                mock.patch.object(yt_auth, "_keyring", return_value=fake):
            result, _ = self._run(status=200)
        self.assertEqual(result, {"had_login": True, "revoked": True})
        fake.delete_password.assert_called_once_with(yt_auth.KEYRING_SERVICE, yt_auth.KEYRING_USER)


if __name__ == "__main__":
    unittest.main()
