import unittest
from unittest import mock

import tiktok_studio
import yt_common
import yt_public


def watch_page(title, views, length, date, desc=""):
    return ('"videoDetails":{"title":"%s"} "viewCount":"%d" "lengthSeconds":"%d" '
            '"publishDate":"%s" "shortDescription":"%s"' % (title, views, length, date, desc))


A, B, C = "A" * 11, "B" * 11, "C" * 11  # A: long only, B: on both pages, C: short only
PAGES = {
    "https://www.youtube.com/@x/videos": ('"videoRenderer":{"videoId":"%s"} "videoRenderer":{"videoId":"%s"} '
                                          '"videoRenderer":{"videoId":"%s"}' % (A, B, A)),
    "https://www.youtube.com/@x/shorts": '"/shorts/%s" "/shorts/%s" "/shorts/%s"' % (C, B, C),
    f"https://www.youtube.com/watch?v={A}": watch_page("Alpha", 10, 600, "2026-01-01"),
    f"https://www.youtube.com/watch?v={B}": watch_page("Beta", 20, 50, "2026-03-01"),
    f"https://www.youtube.com/watch?v={C}": watch_page("Gamma", 30, 40, "2026-02-01"),
}


class PublicScrapeTests(unittest.TestCase):
    def test_each_video_fetched_once_shorts_first_and_sorted_newest_first(self):
        calls = []

        def fake_get(url):
            calls.append(url)
            return PAGES[url]
        with mock.patch.object(yt_common, "_http_get", side_effect=fake_get):
            snap = yt_public.fetch_public_channel_snapshot("@x")
        watch_calls = [u for u in calls if "watch?v=" in u]
        self.assertEqual(sorted(watch_calls), sorted(set(watch_calls)))  # no duplicates
        self.assertEqual(len(watch_calls), 3)
        self.assertEqual([v["videoId"] for v in snap["videos"]], [B, C, A])  # newest first
        formats = {v["videoId"]: v["format"] for v in snap["videos"]}
        self.assertEqual(formats, {A: "long", B: "short", C: "short"})  # B is on both pages: a Short

    def test_first_failure_still_raises(self):
        def fake_get(url):
            if url.endswith(C):
                raise OSError("boom")
            return PAGES[url]
        with mock.patch.object(yt_common, "_http_get", side_effect=fake_get):
            with self.assertRaises(OSError):
                yt_public.fetch_public_channel_snapshot("@x")

    def test_short_needs_the_hint_or_a_shorts_tag(self):
        def detail(desc, hint):
            page = watch_page("T", 1, 100, "2026-01-01", desc)
            with mock.patch.object(yt_common, "_http_get", return_value=page):
                return yt_public.fetch_video_public_details("D" * 11, is_short_hint=hint)["format"]
        self.assertEqual(detail("", False), "long")
        self.assertEqual(detail("#Shorts fun", False), "short")
        self.assertEqual(detail("", True), "short")


class CrossTableTests(unittest.TestCase):
    def test_titles_are_normalized_once_each(self):
        yt = {"videos": [{"format": "short", "videoId": "v1", "title": "One #Shorts"},
                         {"format": "short", "videoId": "v2", "title": "Two #Shorts"}]}
        tt = {"videos": [{"title": "Two", "videoDescription": ""}, {"title": "One", "videoDescription": "d"},
                         {"title": "Three", "videoDescription": ""}]}
        real = tiktok_studio.normalize_short_title
        with mock.patch.object(tiktok_studio, "normalize_short_title", side_effect=real) as spy:
            table = tiktok_studio.build_cross_platform_table(yt, tt)
        self.assertEqual(spy.call_count, 2 + 3 * 2)  # 2 YouTube titles + (title, description) per TikTok video
        self.assertEqual(sum(1 for line in table.splitlines() if line.startswith("| ")), 1 + 3)  # header + 2 matched Shorts + 1 unmatched TikTok


class SnapshotTypesTests(unittest.TestCase):
    def test_declared_keys_match_what_the_fetchers_build(self):
        snap = yt_common.snapshot_envelope("public", {}, [], youtube_counts=True)
        self.assertEqual(set(snap), set(yt_common.Snapshot.__annotations__))


if __name__ == "__main__":
    unittest.main()


class CacheExpiryTests(unittest.TestCase):
    def test_purges_snapshot_and_report_older_than_30_days_only(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            cache, report = Path(d) / "channel_snapshot.json", Path(d) / "report.html"
            cache.write_text("{}")
            report.write_text("<html>")
            now = 1_800_000_000.0
            os.utime(cache, (now - 31 * 86400,) * 2)  # stale
            os.utime(report, (now - 29 * 86400,) * 2)  # still fresh
            with mock.patch.object(yt_common, "CACHE_FILE", cache), mock.patch.object(yt_common, "REPORT_FILE", report):
                yt_common.purge_stale_youtube_cache(now=now)
                self.assertFalse(cache.exists())
                self.assertTrue(report.exists())
                yt_common.purge_stale_youtube_cache(now=now + 2 * 86400)  # report now 31 days old; cache missing is fine
                self.assertFalse(report.exists())
