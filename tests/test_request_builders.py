import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yt_auth
import yt_studio
import yt_videos

SCHEDULE = "2099-01-01T20:00:00+01:00"


class FakeYouTube:
    """Records the body of every videos.insert / videos.update call."""

    def __init__(self):
        self.inserts = []
        self.updates = []

    def videos(self):
        yt = self

        class Videos:
            def insert(self, part, body, media_body):
                yt.inserts.append({"part": part, "body": body})
                return mock.Mock(next_chunk=lambda: (None, {"id": "newvideo123"}))

            def list(self, part, id):
                item = {"snippet": {"title": "Old", "description": "d", "tags": ["a"]},
                        "status": {"privacyStatus": "private", "uploadStatus": "processed"}}
                return mock.Mock(execute=lambda: {"items": [item]})

            def update(self, part, body):
                yt.updates.append({"part": part, "body": body})
                return mock.Mock(execute=lambda: {"snippet": body.get("snippet", {"title": "Old"}),
                                                  "status": body.get("status", {})})
        return Videos()


def _spy(name):
    """Patch yt_videos.<name> with a wrapper that records each call's return value."""
    real, results = getattr(yt_videos, name), []

    def wrapper(*a, **k):
        results.append(real(*a, **k))
        return results[-1]
    return mock.patch.object(yt_videos, name, side_effect=wrapper), results


class TestRequestBuilders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.video = Path(self.tmp.name) / "v.mp4"
        self.video.write_bytes(b"x" * 10)
        self.fake = FakeYouTube()
        mods = {name: types.ModuleType(name) for name in (
            "googleapiclient", "googleapiclient.discovery", "googleapiclient.http")}
        mods["googleapiclient.discovery"].build = lambda *a, **k: self.fake
        mods["googleapiclient.http"].MediaFileUpload = lambda path, **kw: path
        for p in (mock.patch.dict(sys.modules, mods),
                  mock.patch.object(yt_auth, "get_oauth_credentials", return_value=object())):
            p.start()
            self.addCleanup(p.stop)

    UPLOAD_ARGS = dict(title="T", description="D", tags=["x", "y"], hashtags=["Shorts"],
                       category_id="27", language="de", made_for_kids=True,
                       contains_synthetic_media=True, privacy_status="unlisted")

    def test_upload_sends_exactly_the_built_body(self):
        for publish_at in (None, SCHEDULE):
            with self.subTest(publish_at=publish_at):
                self.fake.inserts.clear()
                yt_studio.upload_private_draft(self.video, publish_at=publish_at, **self.UPLOAD_ARGS)
                expected = yt_studio._build_upload_body(
                    "T", "D\n\n#Shorts", ["x", "y"], "27", "de", True, True, "unlisted", publish_at)
                self.assertEqual(self.fake.inserts, [{"part": "snippet,status", "body": expected}])

    def test_upload_dry_run_preview_matches_built_body(self):
        patch, built = _spy("_build_upload_body")
        with patch:
            res = yt_studio.upload_private_draft(self.video, publish_at=SCHEDULE, dry_run=True, **self.UPLOAD_ARGS)
        self.assertEqual(len(built), 1)
        body = built[0]
        self.assertEqual(res["privacyStatus"], "private")  # schedule forces private, decided once in the builder
        self.assertEqual(res["privacyStatus"], body["status"]["privacyStatus"])
        self.assertEqual(res["description"], body["snippet"]["description"])
        self.assertEqual(res["tags"], body["snippet"]["tags"])
        self.assertEqual(res["language"], body["snippet"]["defaultLanguage"])
        self.assertEqual(res["madeForKids"], body["status"]["selfDeclaredMadeForKids"])
        self.assertEqual(body["status"]["publishAt"], SCHEDULE)
        self.assertEqual(self.fake.inserts, [])

    def test_update_sends_built_changes_merged_into_existing(self):
        kwargs = dict(title="New", privacy_status="unlisted", publish_at=SCHEDULE,
                      contains_synthetic_media=False)
        yt_studio.update_video_metadata("abcdefghijk", **kwargs)
        changes = yt_studio._build_update_changes(
            "New", None, None, "unlisted", SCHEDULE, False)
        sent = self.fake.updates[0]
        self.assertEqual(sent["part"], "snippet,status")
        self.assertEqual(sent["body"]["snippet"], {**{"title": "Old", "description": "d", "tags": ["a"]},
                                                  **changes["snippet"]})
        self.assertEqual(sent["body"]["status"], {**{"privacyStatus": "private", "uploadStatus": "processed"},
                                                 **changes["status"]})

    def test_update_builder_only_contains_changed_parts(self):
        self.assertEqual(yt_studio._build_update_changes(None, None, None, None, None, None), {})
        self.assertEqual(yt_studio._build_update_changes("T", None, None, None, None, None),
                         {"snippet": {"title": "T"}})
        self.assertEqual(yt_studio._build_update_changes(None, None, None, None, SCHEDULE, None),
                         {"status": {"privacyStatus": "private", "publishAt": SCHEDULE}})

    def test_update_dry_run_preview_derives_from_builder(self):
        patch, built = _spy("_build_update_changes")
        with patch, mock.patch.object(yt_auth, "get_oauth_credentials", side_effect=AssertionError("OAuth")):
            res = yt_studio.update_video_metadata(
                "abcdefghijk", title="New", tags=["z"], privacy_status="unlisted", publish_at=SCHEDULE,
                contains_synthetic_media=True, dry_run=True)
        self.assertEqual(len(built), 1)
        changes = built[0]
        self.assertEqual(res["wouldChange"], {**changes["snippet"], **changes["status"]})
        self.assertEqual(res["wouldChange"]["privacyStatus"], "private")
        self.assertEqual(self.fake.updates, [])


if __name__ == "__main__":
    unittest.main()
