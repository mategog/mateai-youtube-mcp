import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yt_auth
import yt_studio

# What a real videos.list(part="snippet,status") returns: no containsSyntheticMedia.
LISTED_STATUS = {
    "embeddable": True, "license": "youtube", "madeForKids": False,
    "privacyStatus": "private", "publicStatsViewable": True,
    "selfDeclaredMadeForKids": False, "uploadStatus": "processed",
}


class FakeYouTube:
    """Records every videos.update call; never touches the network."""

    def __init__(self):
        self.updates = []
        self.thumbnail_calls = []

    def videos(self):
        yt = self

        class Videos:
            def list(self, part, id):
                item = {"id": id,
                        "snippet": {"title": "Old", "description": "d", "categoryId": "28", "tags": ["a"]},
                        "status": dict(LISTED_STATUS)}
                return mock.Mock(execute=lambda: {"items": [item]})

            def update(self, part, body):
                yt.updates.append({"part": part, "body": body})
                return mock.Mock(execute=lambda: {
                    "snippet": body.get("snippet", {"title": "Old"}),
                    "status": body.get("status", {}),
                })
        return Videos()

    def thumbnails(self):
        yt = self
        return types.SimpleNamespace(set=lambda **kw: (yt.thumbnail_calls.append(kw), mock.Mock(execute=lambda: {}))[1])


class TestUpdatePreservesSyntheticFlag(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.thumb = Path(self.tmp.name) / "cover.png"
        self.thumb.write_bytes(b"png")
        self.fake = FakeYouTube()
        mods = {name: types.ModuleType(name) for name in (
            "googleapiclient", "googleapiclient.discovery", "googleapiclient.http")}
        mods["googleapiclient.discovery"].build = lambda *a, **k: self.fake
        mods["googleapiclient.http"].MediaFileUpload = lambda path: path
        patches = [mock.patch.dict(sys.modules, mods),
                   mock.patch.object(yt_auth, "get_oauth_credentials", return_value=object())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _update(self, **kw):
        return yt_studio.update_video_metadata("abcdefghijk", **kw)

    def test_thumbnail_only_does_not_resend_status(self):
        self._update(thumbnail_path=self.thumb)
        self.assertEqual(len(self.fake.thumbnail_calls), 1)
        for call in self.fake.updates:
            self.assertNotIn("status", call["part"])
            self.assertNotIn("status", call["body"])

    def test_title_only_sends_snippet_without_status(self):
        self._update(title="New")
        self.assertEqual(len(self.fake.updates), 1)
        self.assertEqual(self.fake.updates[0]["part"], "snippet")
        self.assertNotIn("status", self.fake.updates[0]["body"])
        self.assertEqual(self.fake.updates[0]["body"]["snippet"]["title"], "New")

    def test_privacy_change_still_sends_status(self):
        self._update(privacy_status="unlisted")
        self.assertEqual(self.fake.updates[0]["part"], "status")
        self.assertEqual(self.fake.updates[0]["body"]["status"]["privacyStatus"], "unlisted")
        self.assertNotIn("containsSyntheticMedia", self.fake.updates[0]["body"]["status"])

    def test_title_and_privacy_send_both_parts(self):
        self._update(title="New", privacy_status="unlisted")
        self.assertEqual(self.fake.updates[0]["part"], "snippet,status")

    def test_explicit_flag_is_sent(self):
        self._update(contains_synthetic_media=True)
        call = self.fake.updates[0]
        self.assertEqual(call["part"], "status")
        self.assertIs(call["body"]["status"]["containsSyntheticMedia"], True)

    def test_explicit_false_is_sent(self):
        self._update(contains_synthetic_media=False)
        self.assertIs(self.fake.updates[0]["body"]["status"]["containsSyntheticMedia"], False)

    def test_dry_run_reports_flag(self):
        with mock.patch.object(yt_auth, "get_oauth_credentials", side_effect=AssertionError("touched OAuth")):
            res = self._update(contains_synthetic_media=True, dry_run=True)
        self.assertIs(res["wouldChange"]["containsSyntheticMedia"], True)
        self.assertEqual(self.fake.updates, [])


if __name__ == "__main__":
    unittest.main()
