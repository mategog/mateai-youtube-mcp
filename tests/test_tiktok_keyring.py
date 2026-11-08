import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import tiktok_studio
import yt_auth

STORED = {"access_token": "acc", "refresh_token": "ref", "expires_at": int(time.time()) + 3600,
          "refresh_expires_at": int(time.time()) + 86400, "open_id": "oid", "scope": "video.list",
          "client_key": "ck", "client_secret": "cs", "account": "@mate"}


class FakeKeyring:
    def __init__(self, value=None):
        self.items = {} if value is None else {(yt_auth.KEYRING_SERVICE, "tiktok-oauth-token"): value}

    def get_password(self, service, user):
        return self.items.get((service, user))

    def set_password(self, service, user, value):
        self.items[(service, user)] = value


class TestTikTokKeyring(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.token_file = Path(tmp.name) / ".tokens" / "tiktok_token.json"
        self.client_file = Path(tmp.name) / "tiktok_client.json"
        env = mock.patch.dict(os.environ, {"MATEAI_TOKEN_BACKEND": "keyring"})
        env.start()
        self.addCleanup(env.stop)

    def get(self, ring):
        with mock.patch.object(yt_auth, "_keyring", return_value=ring):
            return tiktok_studio.get_valid_tiktok_token(token_file=self.token_file, client_file=self.client_file)

    def test_valid_token_is_read_from_the_keychain(self):
        with mock.patch.object(tiktok_studio, "_post_form", side_effect=AssertionError("refreshed")):
            self.assertEqual(self.get(FakeKeyring(json.dumps(STORED))), "acc")
        self.assertFalse(self.token_file.exists())

    def test_refresh_uses_stored_client_and_writes_back_keeping_client_fields(self):
        ring = FakeKeyring(json.dumps({**STORED, "expires_at": 10}))
        resp = {"access_token": "new", "refresh_token": "ref2", "expires_in": 100, "refresh_expires_in": 1000,
                "open_id": "oid", "scope": "video.list"}
        with mock.patch.object(tiktok_studio, "_post_form", return_value=resp) as post:
            self.assertEqual(self.get(ring), "new")
        fields = post.call_args.args[1]
        self.assertEqual((fields["client_key"], fields["client_secret"], fields["refresh_token"]), ("ck", "cs", "ref"))
        saved = json.loads(ring.get_password(yt_auth.KEYRING_SERVICE, "tiktok-oauth-token"))
        self.assertEqual((saved["access_token"], saved["refresh_token"]), ("new", "ref2"))
        self.assertEqual((saved["client_key"], saved["client_secret"], saved["account"]), ("ck", "cs", "@mate"))
        self.assertAlmostEqual(saved["expires_at"], int(time.time()) + 100, delta=5)
        self.assertFalse(self.token_file.exists())

    def test_missing_entry_points_to_mateai(self):
        with self.assertRaisesRegex(RuntimeError, "No TikTok login found. Open MateAI and connect TikTok."):
            self.get(FakeKeyring())

    def test_expired_refresh_token_points_to_mateai(self):
        with self.assertRaisesRegex(RuntimeError, "open MateAI and connect TikTok again"):
            self.get(FakeKeyring(json.dumps({**STORED, "expires_at": 10, "refresh_expires_at": 20})))

    def test_file_mode_unchanged_without_the_env_var(self):
        self.token_file.parent.mkdir(parents=True)
        self.token_file.write_text(json.dumps(STORED), encoding="utf-8")
        with mock.patch.dict(os.environ, {"MATEAI_TOKEN_BACKEND": ""}), \
                mock.patch.object(yt_auth, "_keyring", side_effect=AssertionError("keyring used")):
            self.assertEqual(
                tiktok_studio.get_valid_tiktok_token(token_file=self.token_file, client_file=self.client_file), "acc")


if __name__ == "__main__":
    unittest.main()
