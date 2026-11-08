import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yt_auth
import yt_common
import yt_studio
import yt_videos


class FakeHttpError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.resp = types.SimpleNamespace(status=status)


def _modules(client):
    mods = {n: types.ModuleType(n) for n in ("googleapiclient", "googleapiclient.discovery", "googleapiclient.http")}
    mods["googleapiclient.discovery"].build = lambda *a, **k: client
    mods["googleapiclient.http"].MediaFileUpload = lambda path, **kw: path
    return mods


class FakeClient:
    """YouTube Data + Analytics client. `reports` is a list of results or exceptions, consumed in order."""

    def __init__(self, reports=()):
        self.reports_left = list(reports)
        self.metrics_asked = []

    def reports(self):
        client = self

        class Reports:
            def query(self, **kw):
                client.metrics_asked.append(kw["metrics"])
                out = client.reports_left.pop(0)

                def run():
                    if isinstance(out, Exception):
                        raise out
                    return out
                return mock.Mock(execute=run)
        return Reports()

    def channels(self):
        item = {"snippet": {"title": "T", "customUrl": "@t"}, "statistics": {"subscriberCount": "3"},
                "contentDetails": {"relatedPlaylists": {"uploads": "UU"}}}
        return mock.Mock(list=lambda **kw: mock.Mock(execute=lambda: {"items": [item]}))

    def playlistItems(self):
        return mock.Mock(list=lambda **kw: mock.Mock(execute=lambda: {"items": []}))

    def videos(self):
        item = {"id": "abcdefghijk", "snippet": {"title": "V"}, "contentDetails": {"duration": "PT1M40S"}}
        return mock.Mock(list=lambda **kw: mock.Mock(execute=lambda: {"items": [item]}))


class SilentFailureTests(unittest.TestCase):
    def use(self, client):
        for p in (mock.patch.dict(sys.modules, _modules(client)),
                  mock.patch.object(yt_auth, "get_oauth_credentials", return_value=object())):
            p.start()
            self.addCleanup(p.stop)

    def test_engaged_views_unsupported_retries_without_it(self):
        client = FakeClient([FakeHttpError(400), {"columnHeaders": [], "rows": []}])
        self.use(client)
        yt_studio.fetch_studio_channel_snapshot()
        self.assertIn("engagedViews", client.metrics_asked[0])
        self.assertNotIn("engagedViews", client.metrics_asked[1])

    def test_quota_or_auth_error_is_not_retried_or_hidden(self):
        for status in (401, 403, 429):
            with self.subTest(status=status):
                self.use(FakeClient([FakeHttpError(status)]))
                with self.assertRaises(FakeHttpError):
                    yt_studio.fetch_studio_channel_snapshot()

    def test_retention_failures_are_reported_not_swallowed(self):
        self.use(FakeClient([FakeHttpError(403), FakeHttpError(403)]))
        diag = yt_studio.fetch_video_retention_diagnosis("abcdefghijk")
        self.assertFalse(diag["hasRetentionCurve"])
        self.assertEqual(len(diag["errors"]), 2)
        self.assertTrue(diag["errors"][0].startswith("trafficSources:"))
        self.assertTrue(diag["errors"][1].startswith("retentionCurve:"))

    def test_retention_success_has_no_errors_key(self):
        self.use(FakeClient([{"rows": []}, {"rows": [[0.5, 0.6, 0.7]]}]))
        diag = yt_studio.fetch_video_retention_diagnosis("abcdefghijk")
        self.assertNotIn("errors", diag)
        self.assertTrue(diag["hasRetentionCurve"])

    def test_unparseable_word_timings_are_reported(self):
        self.use(FakeClient([{"rows": []}, {"rows": []}]))
        with tempfile.TemporaryDirectory() as tmp:
            words = Path(tmp) / "words.js"
            words.write_text("const W = [not json];")
            diag = yt_studio.fetch_video_retention_diagnosis("abcdefghijk", words_or_script_path=words)
        self.assertTrue(any(e.startswith("wordTimings:") for e in diag["errors"]))

    def test_upload_reports_why_thumbnail_and_comment_failed(self):
        class Videos:
            def insert(self, **kw):
                return mock.Mock(next_chunk=lambda: (None, {"id": "newvideo123"}))

            def list(self, **kw):
                return mock.Mock(execute=lambda: {"items": [{"processingDetails": {"processingStatus": "succeeded"}}]})

        def boom(**kw):
            raise FakeHttpError(403)
        client = mock.Mock(videos=lambda: Videos(), thumbnails=lambda: mock.Mock(set=boom))
        self.use(client)
        with tempfile.TemporaryDirectory() as tmp:
            video, thumb = Path(tmp) / "v.mp4", Path(tmp) / "t.png"
            video.write_bytes(b"x")
            thumb.write_bytes(b"x")
            with mock.patch.object(yt_videos, "post_video_comment", side_effect=FakeHttpError(403)):
                res = yt_studio.upload_private_draft(video, title="T", thumbnail_path=thumb,
                                                     pinned_comment="hi", auto_post_comment=True)
        self.assertFalse(res["thumbnailUploaded"])
        self.assertIsNone(res["commentPostedId"])
        self.assertEqual(res["thumbnailError"], "HTTP 403")
        self.assertEqual(res["commentError"], "HTTP 403")

    def _upload_with_processing(self, statuses):
        """Upload with a thumbnail while videos.list reports `statuses` in order (the last one repeats)."""
        left, set_calls = list(statuses), []

        class Videos:
            def insert(self, **kw):
                return mock.Mock(next_chunk=lambda: (None, {"id": "newvideo123"}))

            def list(self, **kw):
                status = left.pop(0) if len(left) > 1 else left[0]
                return mock.Mock(execute=lambda: {"items": [{"processingDetails": {"processingStatus": status}}]})

        thumbs = mock.Mock(set=lambda **kw: (set_calls.append(kw), mock.Mock(execute=lambda: {}))[1])
        self.use(mock.Mock(videos=lambda: Videos(), thumbnails=lambda: thumbs))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(yt_videos.time, "sleep") as sleep:
            video, thumb = Path(tmp) / "v.mp4", Path(tmp) / "t.png"
            video.write_bytes(b"x")
            thumb.write_bytes(b"x")
            res = yt_studio.upload_private_draft(video, title="T", thumbnail_path=thumb)
        return res, set_calls, sleep

    def test_thumbnail_is_set_once_processing_succeeds(self):
        res, set_calls, sleep = self._upload_with_processing(["processing", "processing", "succeeded"])
        self.assertTrue(res["thumbnailUploaded"])
        self.assertNotIn("thumbnailError", res)
        self.assertEqual(len(set_calls), 1)
        self.assertEqual(sleep.call_count, 2)

    def test_thumbnail_is_not_set_when_processing_times_out_or_fails(self):
        for statuses in (["processing"], ["processing", "failed"]):
            with self.subTest(statuses=statuses):
                res, set_calls, _ = self._upload_with_processing(statuses)
                self.assertFalse(res["thumbnailUploaded"])
                self.assertEqual(set_calls, [])
                self.assertIn("yt_update_video", res["thumbnailError"])
                self.assertEqual(res["videoId"], "newvideo123")

    def test_unknown_subscriber_count_is_none_not_invented(self):
        with mock.patch.object(yt_common, "_http_get", return_value="<html></html>"):
            snap = yt_studio.fetch_public_channel_snapshot("@x")
        self.assertIsNone(snap["channel"]["subscribersText"])

    def test_shorts_style_comes_from_data_not_title_keywords(self):
        snap = {"videos": [{"format": "short", "videoId": "aaaaaaaaaaa", "title": "Gemini Carbon", "url": "u"},
                           {"format": "short", "videoId": "bbbbbbbbbbb", "title": "Other", "url": "u"}]}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(yt_common, "STATE_DIR", Path(tmp)):
                rows = yt_studio.build_shorts_experiment_markdown(snap).splitlines()[2:]
                self.assertTrue(all("| — |" in r for r in rows))
                (Path(tmp) / "shorts_styles.json").write_text(json.dumps({"aaaaaaaaaaa": "C (Poster)"}))
                rows = yt_studio.build_shorts_experiment_markdown(snap).splitlines()[2:]
        self.assertIn("| C (Poster) |", rows[0])
        self.assertIn("| — |", rows[1])


if __name__ == "__main__":
    unittest.main()
