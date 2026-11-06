import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import tiktok_studio
import yt_auth
import yt_common
import yt_studio
from test_silent_failures import FakeClient, _modules

TOP_KEYS = ["generatedAt", "mode", "channel", "totals", "videos", "attribution"]
YT_TOTALS = ["videoCount", "shortsCount", "longCount", "totalViews", "topVideo"]
TT_TOTALS = ["videoCount", "totalViews", "topVideo"]


class EnvelopeShapeTests(unittest.TestCase):
    def test_public_snapshot_shape(self):
        with mock.patch.object(yt_common, "_http_get", return_value="<html></html>"):
            snap = yt_studio.fetch_public_channel_snapshot("@x")
        self.assertEqual(list(snap), TOP_KEYS)
        self.assertEqual(snap["mode"], "public")
        self.assertEqual(list(snap["totals"]), YT_TOTALS)
        self.assertEqual(snap["attribution"], yt_common.AUTHOR_ATTRIBUTION)
        self.assertRegex(snap["generatedAt"], r"^\d{4}-\d\d-\d\d \d\d:\d\d UTC$")

    def test_studio_snapshot_shape(self):
        with mock.patch.dict(sys.modules, _modules(FakeClient([{"rows": []}] * 4))), \
                mock.patch.object(yt_auth, "get_oauth_credentials", return_value=object()):
            snap = yt_studio.fetch_studio_channel_snapshot()
        self.assertEqual(list(snap), TOP_KEYS)
        self.assertEqual(snap["mode"], "studio_oauth")
        self.assertEqual(list(snap["totals"]), YT_TOTALS)
        self.assertEqual(snap["channel"]["handle"], "@t")
        self.assertEqual(snap["channel"]["subscribersText"], "3 subscribers")

    def test_tiktok_snapshot_shape_has_no_youtube_counts(self):
        user = {"data": {"user": {"username": "mate", "display_name": "Mate", "follower_count": 5}}}
        videos = {"data": {"videos": [{"id": "1", "view_count": 7}, {"id": "2", "view_count": 9}]}}
        with mock.patch.object(tiktok_studio, "get_valid_tiktok_token", return_value="tok"), \
                mock.patch.object(tiktok_studio, "_http_json", side_effect=[user, videos]):
            snap = tiktok_studio.fetch_tiktok_snapshot()
        self.assertEqual(list(snap), TOP_KEYS)
        self.assertEqual(snap["mode"], "tiktok_oauth")
        self.assertEqual(list(snap["totals"]), TT_TOTALS)
        self.assertEqual(snap["totals"]["totalViews"], 16)
        self.assertEqual(snap["totals"]["topVideo"]["videoId"], "2")
        self.assertEqual(snap["channel"]["handle"], "@mate")

    def test_envelope_counts_formats_and_sums_views(self):
        vids = [{"format": "short", "views": 3}, {"format": "long", "views": 0}, {"format": "short", "views": 10}]
        env = yt_common.snapshot_envelope("m", {"c": 1}, vids, youtube_counts=True)
        self.assertEqual(env["totals"]["shortsCount"], 2)
        self.assertEqual(env["totals"]["longCount"], 1)
        self.assertEqual(env["totals"]["totalViews"], 13)
        self.assertEqual(env["totals"]["topVideo"], vids[2])
        self.assertEqual(env["channel"], {"c": 1})

    def test_write_snapshot_cache_matches_indented_json(self):
        snap = {"a": [1, 2], "b": "é"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snap.json"
            yt_common.write_snapshot_cache(snap, path)
            self.assertEqual(path.read_text(encoding="utf-8"), json.dumps(snap, indent=2))

    def test_report_json_cannot_close_its_script_block(self):
        import yt_snapshot

        snap = {"videos": [{"title": "</script><script>alert(1)</script>"}]}
        with tempfile.TemporaryDirectory() as tmp:
            html = yt_snapshot.render_html_report(snap, Path(tmp) / "report.html").read_text(encoding="utf-8")
        payload = html.split("const SNAP = ", 1)[1].split(";\n", 1)[0]
        self.assertNotIn("<", payload)
        self.assertEqual(json.loads(payload), snap)


class ClientScopeTests(unittest.TestCase):
    def setUp(self):
        self.built = []
        mods = _modules(None)
        mods["googleapiclient.discovery"].build = lambda name, version, **kw: self.built.append((name, version)) or (name, version)
        self.creds = mock.Mock(return_value=object())
        for p in (mock.patch.dict(sys.modules, mods), mock.patch.object(yt_auth, "get_oauth_credentials", self.creds)):
            p.start()
            self.addCleanup(p.stop)

    def scopes(self):
        return [c.kwargs["upload_scope"] for c in self.creds.call_args_list]

    def test_youtube_client_defaults_to_upload_scope(self):
        self.assertEqual(yt_auth._youtube_client(Path("s.json")), ("youtube", "v3"))
        self.assertEqual(self.scopes(), [True])

    def test_youtube_client_can_request_read_only(self):
        yt_auth._youtube_client(Path("s.json"), upload_scope=False)
        self.assertEqual(self.scopes(), [False])

    def test_paired_client_is_read_only_and_builds_both_apis(self):
        yt, yta = yt_auth._youtube_and_analytics_clients(Path("s.json"))
        self.assertEqual((yt, yta), (("youtube", "v3"), ("youtubeAnalytics", "v2")))
        self.assertEqual(self.scopes(), [False])

    def test_callers_keep_their_scopes(self):
        import yt_retention
        import yt_snapshot
        import yt_videos

        for fn in (yt_snapshot.fetch_studio_channel_snapshot, yt_retention.fetch_video_retention_diagnosis):
            self.creds.reset_mock()
            with self.assertRaises(Exception):  # the stub clients are plain tuples, so the call fails after setup
                fn(*(["abcdefghijk"] if fn is yt_retention.fetch_video_retention_diagnosis else []))
            self.assertEqual(self.scopes(), [False], fn.__name__)

        self.creds.reset_mock()
        with self.assertRaises(Exception):
            yt_videos.post_video_comment("abcdefghijk", "hi")
        self.assertEqual(self.scopes(), [True])
