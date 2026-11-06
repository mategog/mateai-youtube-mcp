import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import mcp_server
import yt_auth
import yt_common
import yt_snapshot
import yt_studio

os.environ["MATEAI_DESKTOP_LOGIN"] = "off"  # never read the real MateAI Studio login in tests

VID = "v" * 11


class FakeHttpError(Exception):
    def __init__(self, status, reason="forbidden"):
        super().__init__(f"HTTP {status}")
        self.resp = types.SimpleNamespace(status=status)
        self.content = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode()


class GuardTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = Path(tmp.name) / "comment_log.json"
        self.safety = Path(tmp.name) / "safety.json"
        for p in (mock.patch.object(mcp_server, "COMMENT_LOG_FILE", self.log),
                  mock.patch.object(mcp_server, "SAFETY_FILE", self.safety)):
            p.start()
            self.addCleanup(p.stop)

    def seed(self, ages_sec, text="seed"):
        now = time.time()
        for age in ages_sec:
            mcp_server.record_comment(text if text is not None else f"t{age}", now=now - age)

    def post(self, text="hello", video_id=VID):
        with mock.patch.object(mcp_server, "post_video_comment", return_value={"commentId": "c"}) as m:
            out = mcp_server._handle_tool_call("yt_post_comment", {"video_id": video_id, "text": text})
        return out, m

    def reply(self, text="hello"):
        with mock.patch.object(mcp_server, "reply_to_comment", return_value={"commentId": "c"}) as m:
            out = mcp_server._handle_tool_call("yt_reply_comment", {"parent_id": "P1", "text": text})
        return out, m


class CommentRateLimitTests(GuardTestCase):
    def test_hourly_limit_refuses_and_says_when(self):
        self.seed([3000 - i for i in range(mcp_server.COMMENTS_PER_HOUR)], text=None)
        out, m = self.post()
        m.assert_not_called()
        self.assertTrue(out["isError"])
        text = out["content"][0]["text"]
        self.assertIn("COMMENT LIMIT REACHED", text)
        self.assertIn("nothing was posted", text)
        self.assertIn("allowed again at", text)
        # The oldest of the last 20 (3000 s ago) leaves the hour window in 600 s.
        self.assertIn(mcp_server._local_time(time.time() + 600)[:13], text)

    def test_daily_limit_counts_older_posts(self):
        # 100 posts, all more than an hour ago but within 24 hours.
        self.seed([4000 + i * 600 for i in range(mcp_server.COMMENTS_PER_DAY)], text=None)
        out, m = self.post()
        m.assert_not_called()
        self.assertIn("per 24 hours", out["content"][0]["text"])

    def test_replies_and_comments_share_the_budget(self):
        self.seed([10 + i for i in range(mcp_server.COMMENTS_PER_HOUR - 1)], text=None)
        out, m = self.reply("first")
        m.assert_called_once()
        self.assertNotIn("isError", out)
        out, m = self.post("second")
        m.assert_not_called()
        self.assertTrue(out["isError"])

    def test_posts_older_than_a_day_are_forgotten(self):
        self.seed([mcp_server._DAY + 60 + i for i in range(mcp_server.COMMENTS_PER_DAY)], text=None)
        out, m = self.post()
        m.assert_called_once()
        self.assertEqual(len(json.loads(self.log.read_text())["posted"]), 1)

    def test_failed_post_is_not_counted(self):
        with mock.patch.object(mcp_server, "post_video_comment", side_effect=RuntimeError("comments disabled")):
            with self.assertRaises(RuntimeError):
                mcp_server._handle_tool_call("yt_post_comment", {"video_id": VID, "text": "x"})
        self.assertFalse(self.log.exists())

    def test_dry_run_is_neither_refused_nor_counted(self):
        self.seed([10 + i for i in range(mcp_server.COMMENTS_PER_HOUR)], text=None)
        out = mcp_server._handle_tool_call("yt_post_comment", {"video_id": VID, "text": "x", "dry_run": True})
        self.assertNotIn("isError", out)
        self.assertEqual(len(json.loads(self.log.read_text())["posted"]), mcp_server.COMMENTS_PER_HOUR)

    def test_upload_auto_comment_respects_the_limit(self):
        self.seed([10 + i for i in range(mcp_server.COMMENTS_PER_HOUR)], text=None)
        with mock.patch.object(mcp_server, "upload_private_draft", return_value={"videoId": VID}) as up:
            out = mcp_server._handle_tool_call(
                "yt_upload_draft", {"video_path": "/x.mp4", "pinned_comment": "hi", "auto_post_comment": True}
            )
        self.assertFalse(up.call_args.kwargs["auto_post_comment"])
        self.assertIn("COMMENT LIMIT REACHED", json.loads(out["content"][0]["text"])["commentError"])

    def test_limits_are_in_tool_descriptions(self):
        by_name = {t["name"]: t for t in mcp_server.listed_tools()}
        for name in ("yt_post_comment", "yt_reply_comment"):
            self.assertIn(f"{mcp_server.COMMENTS_PER_HOUR} comments+replies per rolling hour", by_name[name]["description"])
            self.assertIn(f"{mcp_server.COMMENTS_PER_DAY} per rolling 24 hours", by_name[name]["description"])

    def test_safety_settings_cannot_raise_the_limits(self):
        props = next(t for t in mcp_server.TOOLS if t["name"] == "yt_set_safety_settings")["inputSchema"]["properties"]
        self.assertEqual(set(props), {"confirm"})
        mcp_server.set_safety_settings([])
        self.safety.write_text(json.dumps({"confirm": [], "limits": {"perHour": 10000}, "COMMENTS_PER_HOUR": 10000}))
        self.seed([10 + i for i in range(mcp_server.COMMENTS_PER_HOUR)], text=None)
        out, m = self.post()
        m.assert_not_called()
        self.assertTrue(out["isError"])


class DuplicateCommentTests(GuardTestCase):
    def test_same_normalized_text_refused_on_third_post_across_videos(self):
        self.assertNotIn("isError", self.post("Great video!", video_id="a" * 11)[0])
        self.assertNotIn("isError", self.post("great   VIDEO!", video_id="b" * 11)[0])
        out, m = self.post("  GREAT video!\n", video_id="c" * 11)
        m.assert_not_called()
        self.assertIn("DUPLICATE COMMENT", out["content"][0]["text"])
        self.assertIn("posted again at", out["content"][0]["text"])

    def test_duplicate_reply_is_refused_too(self):
        self.seed([100, 200], text="Thanks!")
        out, m = self.reply("thanks!")
        m.assert_not_called()
        self.assertTrue(out["isError"])

    def test_different_text_and_old_duplicates_are_allowed(self):
        self.seed([mcp_server._DAY + 10, mcp_server._DAY + 20], text="Thanks!")
        self.seed([100], text="Thanks!")
        self.assertNotIn("isError", self.post("Thanks!")[0])
        self.assertNotIn("isError", self.post("Thanks, Anna!")[0])

    def test_log_stores_no_comment_text(self):
        self.post("my secret wording")
        self.assertNotIn("secret", self.log.read_text())


class QuotaTests(unittest.TestCase):
    def test_detects_quota_and_rate_limit_errors_only(self):
        self.assertTrue(yt_common.is_quota_error(FakeHttpError(403, "quotaExceeded")))
        self.assertTrue(yt_common.is_quota_error(FakeHttpError(429, "rateLimitExceeded")))
        self.assertFalse(yt_common.is_quota_error(FakeHttpError(403, "forbidden")))
        self.assertFalse(yt_common.is_quota_error(FakeHttpError(400, "quotaExceeded")))
        self.assertFalse(yt_common.is_quota_error(RuntimeError("quotaExceeded")))

    def test_tool_stops_with_clear_message_and_no_retry(self):
        err = FakeHttpError(403, "quotaExceeded")
        with mock.patch.object(mcp_server, "list_channel_videos", side_effect=err) as m:
            out = mcp_server._handle_tool_call("yt_list_videos", {})
        m.assert_called_once()
        self.assertTrue(out["isError"])
        self.assertIn("midnight Pacific time", out["content"][0]["text"])

    def test_other_errors_still_raise(self):
        with mock.patch.object(mcp_server, "list_channel_videos", side_effect=FakeHttpError(403)):
            with self.assertRaises(FakeHttpError):
                mcp_server._handle_tool_call("yt_list_videos", {})

    def test_video_details_does_not_hide_quota_error(self):
        with mock.patch.object(mcp_server, "fetch_video_retention_diagnosis", side_effect=FakeHttpError(429, "rateLimitExceeded")):
            out = mcp_server._handle_tool_call("yt_video_details", {"video_id": VID})
        self.assertIn("midnight Pacific time", out["content"][0]["text"])

    def test_snapshot_does_not_fall_back_to_scraping_on_quota(self):
        with mock.patch.object(yt_snapshot, "fetch_studio_channel_snapshot", side_effect=FakeHttpError(403, "quotaExceeded")), \
             mock.patch.object(yt_snapshot.yt_public, "fetch_public_channel_snapshot") as scrape, \
             mock.patch.object(yt_snapshot, "DEFAULT_CLIENT_SECRET", mock.Mock(exists=lambda: True)), \
             mock.patch.object(yt_snapshot, "PUBLIC_SCRAPE_ENV", True):
            with self.assertRaises(FakeHttpError):
                yt_snapshot.get_best_snapshot()
        scrape.assert_not_called()

    def test_retention_stops_after_first_quota_error(self):
        asked = []

        class Reports:
            def query(self, **kw):
                asked.append(kw["metrics"])
                return mock.Mock(execute=mock.Mock(side_effect=FakeHttpError(403, "quotaExceeded")))

        client = mock.Mock(reports=Reports)
        item = {"id": VID, "snippet": {"title": "V"}, "contentDetails": {"duration": "PT1M40S"}}
        client.videos().list().execute.return_value = {"items": [item]}
        mods = {n: types.ModuleType(n) for n in ("googleapiclient", "googleapiclient.discovery")}
        mods["googleapiclient.discovery"].build = lambda *a, **k: client
        with mock.patch.dict(sys.modules, mods), mock.patch.object(yt_auth, "get_oauth_credentials", return_value=object()):
            with self.assertRaises(FakeHttpError):
                yt_studio.fetch_video_retention_diagnosis(VID)
        self.assertEqual(len(asked), 1)


if __name__ == "__main__":
    unittest.main()
