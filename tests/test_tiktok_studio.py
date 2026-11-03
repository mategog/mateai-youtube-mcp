import hashlib
import re
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

    def test_missing_credentials_and_expired_refresh_token_raise_clear_errors(self):
        from tiktok_studio import get_valid_tiktok_token
        with tempfile.TemporaryDirectory() as tmp:
            missing_tok = Path(tmp) / ".tokens" / "tiktok_token.json"
            missing_cli = Path(tmp) / "tiktok_client.json"
            with self.assertRaisesRegex(RuntimeError, "tiktok_studio.py setup"):
                get_valid_tiktok_token(token_file=missing_tok, client_file=missing_cli)

            missing_tok.parent.mkdir(parents=True, exist_ok=True)
            missing_tok.write_text('{"access_token":"old","refresh_token":"r","expires_at":10,"refresh_expires_at":20}', encoding="utf-8")
            missing_cli.write_text('{"client_key":"ck","client_secret":"cs"}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "refresh token expired"):
                get_valid_tiktok_token(token_file=missing_tok, client_file=missing_cli)

    def test_expired_token_triggers_refresh_and_creates_tokens_dir_mode_0600(self):
        from unittest.mock import patch
        from tiktok_studio import get_valid_tiktok_token
        with tempfile.TemporaryDirectory() as tmp:
            tok_p = Path(tmp) / ".tokens" / "tiktok_token.json"
            cli_p = Path(tmp) / "tiktok_client.json"
            tok_p.parent.mkdir(parents=True, exist_ok=True)
            tok_p.write_text('{"access_token":"old","refresh_token":"ref123","expires_at":100,"refresh_expires_at":9999999999}', encoding="utf-8")
            cli_p.write_text('{"client_key":"ck","client_secret":"cs"}', encoding="utf-8")
            with patch("tiktok_studio._post_form", return_value={"access_token": "new_tok", "refresh_token": "ref456", "expires_in": 86400, "refresh_expires_in": 31536000}):
                token = get_valid_tiktok_token(token_file=tok_p, client_file=cli_p)
            self.assertEqual(token, "new_tok")
            self.assertEqual(tok_p.stat().st_mode & 0o777, 0o600)

    def test_fetch_tiktok_snapshot_maps_user_info_and_video_list_fields(self):
        from unittest.mock import patch
        from tiktok_studio import fetch_tiktok_snapshot
        user_resp = {"data": {"user": {"display_name": "MateAI", "username": "mateai", "follower_count": 450, "likes_count": 3200, "video_count": 5, "avatar_url": "https://example.com/a.jpg"}}}
        videos_resp = {"data": {"videos": [{"id": "743001", "title": "", "video_description": "Carbon Short #AINews", "create_time": 1761696000, "duration": 42, "view_count": 4200, "like_count": 310, "comment_count": 28, "share_count": 45, "share_url": "https://www.tiktok.com/@mateai/video/743001"}], "has_more": False}}
        with patch("tiktok_studio.get_valid_tiktok_token", return_value="tok"), patch("tiktok_studio._http_json", side_effect=[user_resp, videos_resp]):
            snap = fetch_tiktok_snapshot()
        self.assertEqual(snap["channel"]["handle"], "@mateai")
        self.assertEqual(snap["videos"][0]["views"], 4200)
        self.assertEqual(snap["videos"][0]["publishDate"], "2025-10-29")
        self.assertEqual(snap["videos"][0]["url"], "https://www.tiktok.com/@mateai/video/743001")
        self.assertEqual(snap["videos"][0]["videoDescription"], "Carbon Short #AINews")

    def test_upload_inbox_draft_sends_source_info_only_and_returns_caption_and_ai_reminder(self):
        from unittest.mock import patch
        from tiktok_studio import upload_tiktok_inbox_draft
        with tempfile.TemporaryDirectory() as tmp:
            vid = Path(tmp) / "short.mp4"
            vid.write_bytes(b"x" * 1024)
            init_resp = {"data": {"publish_id": "pub_123", "upload_url": "https://upload.tiktokapis.com/put"}}
            with patch("tiktok_studio.get_valid_tiktok_token", return_value="tok"), \
                 patch("tiktok_studio._http_json", return_value=init_resp) as mock_init, \
                 patch("tiktok_studio._put_chunk") as mock_put:
                res = upload_tiktok_inbox_draft(video_path=vid, title="Carbon Short", hashtags=["#AINews", "#Shorts"])
            sent_body = mock_init.call_args[1]["body"]
            self.assertEqual(set(sent_body.keys()), {"source_info"})
            self.assertEqual(sent_body["source_info"]["video_size"], 1024)
            self.assertEqual(res["publishId"], "pub_123")
            self.assertEqual(res["caption"], "Carbon Short\n\n#AINews")
            self.assertIn("AI-generated", res["aiLabelReminder"])
            mock_put.assert_called_once()

    def test_mcp_server_registers_and_dispatches_tiktok_tools(self):
        import json
        from unittest.mock import patch
        from mcp_server import TOOLS, _handle_tool_call
        names = {t["name"] for t in TOOLS}
        self.assertTrue({"tiktok_channel_snapshot", "tiktok_upload_draft", "cross_platform_shorts_table"}.issubset(names))
        with tempfile.TemporaryDirectory() as tmp:
            temp_cache = Path(tmp) / "tiktok_snapshot.json"
            with patch("mcp_server.TIKTOK_CACHE_FILE", temp_cache), \
                 patch("mcp_server.fetch_tiktok_snapshot", return_value={"channel": {"handle": "@mateai"}, "videos": [], "totals": {}}):
                out = _handle_tool_call("tiktok_channel_snapshot", {})
            self.assertTrue(temp_cache.exists())
        payload = json.loads(out["content"][0]["text"])
        self.assertEqual(payload["channel"]["handle"], "@mateai")

    def test_parse_caption_raises_file_not_found_for_missing_spec_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_spec = Path(tmp) / "does-not-exist.md"
            with self.assertRaises(FileNotFoundError):
                parse_tiktok_caption_from_spec(spec_path=missing_spec)

    def test_parse_caption_cleans_explicit_hashtags_with_spaces(self):
        caption = parse_tiktok_caption_from_spec(
            title="Test Title",
            hashtags=[" #AINews", "AI News", " #Shorts "],
        )
        self.assertEqual(caption, "Test Title\n\n#AINews")

    def test_upload_inbox_draft_passes_quicktime_content_type_for_mov(self):
        from unittest.mock import patch
        from tiktok_studio import upload_tiktok_inbox_draft
        with tempfile.TemporaryDirectory() as tmp:
            vid = Path(tmp) / "clip.mov"
            vid.write_bytes(b"m" * 512)
            init_resp = {"data": {"publish_id": "pub_mov", "upload_url": "https://upload.tiktokapis.com/put"}}
            with patch("tiktok_studio.get_valid_tiktok_token", return_value="tok"), \
                 patch("tiktok_studio._http_json", return_value=init_resp), \
                 patch("tiktok_studio._put_chunk") as mock_put:
                upload_tiktok_inbox_draft(video_path=vid, title="Mov Clip")
            self.assertEqual(mock_put.call_args[1].get("content_type"), "video/quicktime")

    def test_fetch_tiktok_snapshot_paginates_and_handles_missing_username(self):
        from unittest.mock import patch
        from tiktok_studio import fetch_tiktok_snapshot
        user_resp = {"data": {"user": {"display_name": "Creator Name", "username": "", "follower_count": 10, "likes_count": 20, "video_count": 2}}}
        page1 = {"data": {"videos": [{"id": "111", "title": "First", "video_description": "", "create_time": 1761696000, "duration": 15, "view_count": 100, "like_count": 5, "comment_count": 1, "share_count": 2, "share_url": ""}], "has_more": True, "cursor": 1761600000}}
        page2 = {"data": {"videos": [{"id": "222", "title": "Second", "video_description": "", "create_time": 1761600000, "duration": 20, "view_count": 50, "like_count": 3, "comment_count": 0, "share_count": 1, "share_url": "https://www.tiktok.com/@real/video/222"}], "has_more": False, "cursor": 0}}
        with patch("tiktok_studio.get_valid_tiktok_token", return_value="tok"), \
             patch("tiktok_studio._http_json", side_effect=[user_resp, page1, page2]) as mock_http:
            snap = fetch_tiktok_snapshot()
        self.assertEqual(len(snap["videos"]), 2)
        self.assertEqual(mock_http.call_args_list[2][1]["body"], {"max_count": 20, "cursor": 1761600000})
        self.assertEqual(snap["channel"]["handle"], "Creator Name")
        self.assertEqual(snap["channel"]["url"], "")
        self.assertEqual(snap["videos"][0]["url"], "")
        self.assertEqual(snap["videos"][1]["url"], "https://www.tiktok.com/@real/video/222")

    def test_cross_platform_table_escapes_pipes_and_newlines(self):
        yt = {"videos": [{"format": "short", "title": "Line 1\nLine 2 | Part A #Shorts", "publishDate": "2026-10-29", "views": 100, "likes": 5, "comments": 1, "avgViewPct": 50.0}]}
        tt = {"videos": [{"videoId": "999", "title": "", "videoDescription": "Multi\nLine | TikTok #AINews", "publishDate": "2026-10-30", "views": 200, "likes": 10, "comments": 2, "shares": 3}]}
        md = build_cross_platform_table(yt, tt)
        self.assertIn(r"Line 1 Line 2 \| Part A", md)
        self.assertIn(r"Multi Line \| TikTok", md)
        for row in md.splitlines()[2:]:
            self.assertEqual(len(re.findall(r"(?<!\\)\|", row)), 11)


if __name__ == "__main__":
    unittest.main()
