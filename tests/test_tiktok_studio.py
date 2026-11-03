import hashlib
import tempfile
import unittest
from pathlib import Path
from tiktok_studio import (
    build_cross_platform_table,
    build_pkce_pair,
    compute_upload_chunks,
    normalize_short_title,
    parse_tiktok_caption_from_spec,
)


class TestTikTokPureLogic(unittest.TestCase):
    def test_pkce_challenge_matches_sha256_hex_and_validates_length(self):
        raw = "v" * 43
        verifier, challenge = build_pkce_pair(raw)
        self.assertEqual(verifier, raw)
        self.assertEqual(challenge, hashlib.sha256(raw.encode("ascii")).hexdigest())
        with self.assertRaises(ValueError):
            build_pkce_pair("too_short_42_chars________________________")

    def test_compute_upload_chunks_handles_3mb_8mb_25mb_and_70mb(self):
        for sz in (3_200_000, 8_000_000, 25_000_000):
            chunk_size, total_chunks, ranges = compute_upload_chunks(sz)
            self.assertEqual((chunk_size, total_chunks, ranges), (sz, 1, [(0, sz - 1)]))

        chunk_size, total_chunks, ranges_70m = compute_upload_chunks(70_000_000)
        self.assertEqual(chunk_size, 32_000_000)
        self.assertEqual(total_chunks, 2)
        self.assertEqual(ranges_70m, [(0, 31_999_999), (32_000_000, 69_999_999)])
        self.assertLessEqual(ranges_70m[-1][1] - ranges_70m[-1][0] + 1, 128_000_000)

    def test_parse_caption_ignores_rank_numbers_on_real_spec_format(self):
        md_text = (
            "## Title (38 characters)\n\n```\nGemini 4 Carbon: Only Defenders Get It\n```\n\n"
            "## Description\n\n```\n• Ranks #1 on the Artificial Analysis Intelligence Index\n\n"
            "#Gemini4Carbon #GoogleDeepMind #AINews #Cybersecurity #Shorts\n```\n\n"
            "## Tags\n\n```\ngemini 4 carbon, ai news\n```\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "gemini-4-carbon-upload.md"
            p.write_text(md_text, encoding="utf-8")
            caption = parse_tiktok_caption_from_spec(spec_path=p)
        self.assertEqual(
            caption,
            "Gemini 4 Carbon: Only Defenders Get It\n\n#Gemini4Carbon #GoogleDeepMind #AINews #Cybersecurity",
        )

    def test_normalize_title_collapses_whitespace_and_hashtags(self):
        self.assertEqual(
            normalize_short_title("Gemini 4 #AINews  Carbon: Explained! #Shorts"),
            "gemini 4 carbon explained",
        )

    def test_cross_platform_table_matches_via_description_keeps_unmatched_and_handles_none_comments(self):
        yt = {"videos": [
            {"format": "short", "title": "Genie 4 Explained #Shorts", "publishDate": "2026-10-29", "views": 1500, "likes": 90, "comments": None, "avgViewPct": 78.5, "url": "https://youtube.com/shorts/abc"},
            {"format": "short", "title": "YouTube Only Short #Shorts", "publishDate": "2026-10-30", "views": 300, "likes": 12, "comments": 2, "avgViewPct": 60.0, "url": "https://youtube.com/shorts/def"},
        ]}
        tt = {"videos": [
            # Non-empty title that differs: the match must come from videoDescription
            {"videoId": "743001", "title": "Auto title from TikTok", "videoDescription": "Genie 4 Explained #AINews #tiktok", "publishDate": "2026-10-29", "views": 4200, "likes": 310, "comments": 28, "shares": 45, "url": "https://tiktok.com/@user/video/743001"},
            {"videoId": "743002", "title": "", "videoDescription": "TikTok Only Clip #AINews", "publishDate": "2026-10-31", "views": 900, "likes": 40, "comments": 3, "shares": 7, "url": "https://tiktok.com/@user/video/743002"},
        ]}
        md = build_cross_platform_table(yt, tt)
        genie_rows = [line for line in md.splitlines() if "Genie 4 Explained" in line]
        self.assertEqual(len(genie_rows), 1)  # paired into a single row
        self.assertIn("1,500", genie_rows[0])
        self.assertIn("4,200", genie_rows[0])
        self.assertIn("78.5%", genie_rows[0])
        self.assertIn("| 45 |", genie_rows[0])
        self.assertIn("| — |", genie_rows[0])  # YouTube comments: None
        self.assertIn("YouTube Only Short", md)  # unmatched rows are kept
        self.assertIn("TikTok Only Clip", md)


if __name__ == "__main__":
    unittest.main()
