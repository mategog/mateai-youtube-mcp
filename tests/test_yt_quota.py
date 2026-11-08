import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from googleapiclient.errors import HttpError
from googleapiclient.http import HttpMockSequence, MediaInMemoryUpload

import yt_quota

CHUNK = 256 * 1024


def _request(responses, **kw):
    return yt_quota.CountingRequest(
        HttpMockSequence(responses), lambda resp, content: content,
        "https://www.googleapis.com/youtube/v3/videos", methodId=kw.pop("methodId", "youtube.videos.list"), **kw,
    )


class TestQuotaCounter(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Path(tmp.name) / "youtube_quota.json"
        env = mock.patch.dict(os.environ, {"MATEAI_YT_HOME": tmp.name, "MATEAI_LAUNCHER": "desktop"})
        env.start()
        self.addCleanup(env.stop)

    def calls(self):
        return json.loads(self.store.read_text())[yt_quota.today().isoformat()]

    def test_one_call_is_counted_once(self):
        _request([({"status": "200"}, "{}")]).execute()
        self.assertEqual(self.calls(), {"youtube.videos.list": 1})

    def test_failed_call_is_counted_and_still_raises(self):
        with self.assertRaises(HttpError):
            _request([({"status": "403"}, "{}")], methodId="youtube.videos.update").execute()
        self.assertEqual(self.calls(), {"youtube.videos.update": 1})
        self.assertEqual(yt_quota.summary()["today"]["units"], 50)

    def test_resumable_upload_is_counted_once(self):
        media = MediaInMemoryUpload(b"x" * (2 * CHUNK), mimetype="video/mp4", chunksize=CHUNK, resumable=True)
        _request([
            ({"status": "200", "location": "https://upload.example/session"}, ""),
            ({"status": "308", "range": f"bytes=0-{CHUNK - 1}"}, ""),
            ({"status": "200"}, '{"id": "v"}'),
        ], methodId="youtube.videos.insert", method="POST", resumable=media).execute()
        self.assertEqual(self.calls(), {"youtube.videos.insert": 1})
        self.assertEqual(yt_quota.summary()["today"], {"date": yt_quota.today().isoformat(), "units": 0, "uploads": 1})

    def test_plain_plugin_writes_no_file(self):
        with mock.patch.dict(os.environ, {"MATEAI_LAUNCHER": ""}):
            _request([({"status": "200"}, "{}")]).execute()
        self.assertFalse(self.store.exists())

    def test_counting_error_never_breaks_the_call(self):
        with mock.patch.object(yt_quota, "load", side_effect=OSError("disk full")):
            self.assertEqual(_request([({"status": "200"}, '{"ok": 1}')]).execute(), b'{"ok": 1}')


if __name__ == "__main__":
    unittest.main()
