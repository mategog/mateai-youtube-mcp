import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import yt_auth
import yt_studio


def _no_network():
    """A dry run must not sign in or touch Google at all."""
    return mock.patch.object(
        yt_auth, "get_oauth_credentials", side_effect=AssertionError("dry run touched OAuth")
    )


def _future(hours=24):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


class TestUploadDryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / "short.mp4"
        self.video.write_bytes(b"x" * 2048)
        self.thumb = Path(self.tmp.name) / "cover.png"
        self.thumb.write_bytes(b"png")
        self.addCleanup(self.tmp.cleanup)

    def test_reports_what_would_be_uploaded_without_signing_in(self):
        when = _future()
        with _no_network():
            res = yt_studio.upload_private_draft(
                self.video, title="My Short", description="Hello", hashtags=["Shorts"],
                tags=["ai"], publish_at=when, thumbnail_path=self.thumb,
                pinned_comment="Question?", auto_post_comment=True, dry_run=True,
            )
        self.assertTrue(res["dryRun"])
        self.assertEqual(res["title"], "My Short")
        self.assertIn("#Shorts", res["description"])
        self.assertEqual(res["privacyStatus"], "private")
        self.assertEqual(res["scheduledPublishAt"], when)
        self.assertTrue(res["scheduledPublishAtLocal"])
        self.assertTrue(res["thumbnailFound"])
        self.assertTrue(res["willPostComment"])
        self.assertEqual(res["warnings"], [])
        self.assertNotIn("videoId", res)

    def test_warns_when_schedule_is_in_the_past_or_has_no_timezone(self):
        with _no_network():
            past = yt_studio.upload_private_draft(
                self.video, title="t", publish_at=_future(-5), dry_run=True)
            naive = yt_studio.upload_private_draft(
                self.video, title="t", publish_at="2099-01-01T20:00:00", dry_run=True)
        self.assertTrue(any("past" in w for w in past["warnings"]))
        self.assertTrue(any("timezone" in w for w in naive["warnings"]))

    def test_still_fails_on_missing_video_or_title(self):
        with _no_network():
            with self.assertRaises(FileNotFoundError):
                yt_studio.upload_private_draft(Path(self.tmp.name) / "nope.mp4", title="t", dry_run=True)
            with self.assertRaises(ValueError):
                yt_studio.upload_private_draft(self.video, dry_run=True)


class TestUpdateAndCommentDryRun(unittest.TestCase):
    def test_update_lists_only_requested_changes(self):
        with _no_network():
            res = yt_studio.update_video_metadata(
                "abcdefghijk", title="New", publish_at=_future(), contains_synthetic_media=False,
                dry_run=True)
        self.assertTrue(res["dryRun"])
        self.assertEqual(res["wouldChange"]["title"], "New")
        self.assertEqual(res["wouldChange"]["privacyStatus"], "private")
        self.assertNotIn("description", res["wouldChange"])
        self.assertTrue(res["scheduledPublishAtLocal"])

    def test_status_change_without_synthetic_flag_is_refused_in_dry_run_too(self):
        with _no_network():
            with self.assertRaisesRegex(ValueError, "contains_synthetic_media"):
                yt_studio.update_video_metadata("abcdefghijk", privacy_status="public", dry_run=True)

    def test_comment_is_not_posted(self):
        with _no_network():
            res = yt_studio.post_video_comment("abcdefghijk", "hi", dry_run=True)
        self.assertEqual(res, {
            "dryRun": True, "message": "Nothing was posted.",
            "videoId": "abcdefghijk", "text": "hi",
        })


if __name__ == "__main__":
    unittest.main()
