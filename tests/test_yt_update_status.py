import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yt_auth
import yt_studio
import yt_videos

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
                # Like the real API: the response carries only the parts that were sent.
                return mock.Mock(execute=lambda: {k: body[k] for k in ("snippet", "status") if k in body})
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

    def test_title_only_result_reports_title_and_unchanged_privacy(self):
        res = self._update(title="New")
        self.assertEqual(res["title"], "New")
        self.assertEqual(res["privacyStatus"], "private")

    def test_privacy_only_result_keeps_existing_title(self):
        res = self._update(privacy_status="unlisted", contains_synthetic_media=False)
        self.assertEqual(res["title"], "Old")
        self.assertEqual(res["privacyStatus"], "unlisted")

    def test_privacy_change_without_synthetic_flag_is_refused(self):
        # videos.list can't read the flag back, so re-sending status could silently reset it.
        for kw in ({"privacy_status": "unlisted"}, {"publish_at": "2030-01-01T10:00:00+01:00"}):
            with self.assertRaisesRegex(ValueError, "contains_synthetic_media"):
                self._update(**kw)
        self.assertEqual(self.fake.updates, [])

    def test_privacy_change_sends_status_with_the_explicit_flag(self):
        self._update(privacy_status="unlisted", contains_synthetic_media=True)
        self.assertEqual(self.fake.updates[0]["part"], "status")
        self.assertEqual(self.fake.updates[0]["body"]["status"]["privacyStatus"], "unlisted")
        self.assertIs(self.fake.updates[0]["body"]["status"]["containsSyntheticMedia"], True)

    def test_title_and_privacy_send_both_parts(self):
        self._update(title="New", privacy_status="unlisted", contains_synthetic_media=False)
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


    def test_thumbnail_failure_after_metadata_update_is_reported_not_raised(self):
        def failing_set(**kw):
            raise RuntimeError("thumbnail too large")
        with mock.patch.object(FakeYouTube, "thumbnails",
                               lambda yt: types.SimpleNamespace(set=failing_set)):
            res = self._update(title="New", thumbnail_path=self.thumb)
        self.assertEqual(len(self.fake.updates), 1)
        self.assertEqual(res["title"], "New")
        self.assertIs(res["thumbnailUpdated"], False)
        self.assertIn("thumbnail too large", res["thumbnailError"])


class TestTitleDescriptionChecks(unittest.TestCase):
    """One check for upload, update and dry run, before anything is sent."""

    def test_rejects_angle_brackets_long_title_and_long_description(self):
        bad = [({"title": "Retention >75%"}, "over 75%"), ({"description": "a <b> c"}, "'<' or '>'"),
               ({"title": "x" * 101}, "at most 100"), ({"description": "é" * 2501}, "5000")]
        for kw, msg in bad:
            with self.subTest(kw=list(kw)), \
                    mock.patch.object(yt_auth, "get_oauth_credentials", side_effect=AssertionError("OAuth")):
                with self.assertRaisesRegex(ValueError, msg):
                    yt_studio.update_video_metadata("abcdefghijk", dry_run=True, **kw)
                with self.assertRaisesRegex(ValueError, msg):
                    yt_studio.update_video_metadata("abcdefghijk", **kw)

    def test_limits_are_inclusive(self):
        yt_videos._check_title_description("x" * 100, "é" * 2500)

    def test_upload_checks_the_description_after_hashtags_are_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"0")
            ok = yt_studio.upload_private_draft(video, title="t", description="d" * 4990, dry_run=True)
            self.assertEqual(len(ok["description"]), 4990)
            with self.assertRaisesRegex(ValueError, "5000"):
                yt_studio.upload_private_draft(video, title="t", description="d" * 4990,
                                               hashtags=["shorts", "ai"], dry_run=True)
            with self.assertRaisesRegex(ValueError, "over 75%"):
                yt_studio.upload_private_draft(video, title="Up >75%", dry_run=True)


if __name__ == "__main__":
    unittest.main()
