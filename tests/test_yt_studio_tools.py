import json
import unittest
from unittest.mock import MagicMock, patch

from yt_studio import (
    delete_video,
    list_channel_videos,
    list_video_comments,
    reply_to_comment,
)


def _video(vid, title, privacy="public", views="10", description=""):
    return {
        "id": vid,
        "snippet": {"title": title, "description": description, "publishedAt": "2026-10-01T00:00:00Z"},
        "status": {"privacyStatus": privacy},
        "statistics": {"viewCount": views},
    }


def _fake_yt(pages, videos):
    """pages: list of (videoIds, nextPageToken); videos: dict id -> video resource."""
    yt = MagicMock()
    yt.channels().list().execute.return_value = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU123"}}}]
    }
    yt.playlistItems().list().execute.side_effect = [
        {
            "items": [{"contentDetails": {"videoId": v}} for v in ids],
            **({"nextPageToken": tok} if tok else {}),
        }
        for ids, tok in pages
    ]
    yt.videos().list().execute.side_effect = lambda: None  # replaced below
    yt.videos().list.side_effect = lambda **kw: MagicMock(
        execute=lambda: {"items": [videos[i] for i in kw["id"].split(",") if i in videos]}
    )
    return yt


class TestListChannelVideos(unittest.TestCase):
    def test_lists_across_pages_and_includes_private(self):
        videos = {"a" * 11: _video("a" * 11, "One"), "b" * 11: _video("b" * 11, "Two", privacy="unlisted")}
        yt = _fake_yt([(["a" * 11], "tok"), (["b" * 11], None)], videos)
        out = list_channel_videos(yt=yt)
        self.assertEqual([v["title"] for v in out["videos"]], ["One", "Two"])
        self.assertEqual(out["videos"][1]["privacyStatus"], "unlisted")
        self.assertEqual(out["videos"][0]["views"], 10)

    def test_query_filters_title_and_description_case_insensitively(self):
        videos = {
            "a" * 11: _video("a" * 11, "Jev vs Laya"),
            "b" * 11: _video("b" * 11, "Cost meter", description="Built with JEV"),
            "c" * 11: _video("c" * 11, "Unrelated"),
        }
        yt = _fake_yt([(["a" * 11, "b" * 11, "c" * 11], None)], videos)
        out = list_channel_videos(query="jev", yt=yt)
        self.assertEqual([v["title"] for v in out["videos"]], ["Jev vs Laya", "Cost meter"])

    def test_limit_stops_paging(self):
        videos = {"a" * 11: _video("a" * 11, "One"), "b" * 11: _video("b" * 11, "Two")}
        yt = _fake_yt([(["a" * 11], "tok"), (["b" * 11], None)], videos)
        out = list_channel_videos(limit=1, yt=yt)
        self.assertEqual(len(out["videos"]), 1)
        self.assertEqual(yt.playlistItems().list().execute.call_count, 1)


class TestComments(unittest.TestCase):
    def test_list_comments_flattens_threads_and_replies(self):
        yt = MagicMock()
        yt.commentThreads().list().execute.return_value = {
            "items": [
                {
                    "id": "T1",
                    "snippet": {
                        "totalReplyCount": 2,
                        "topLevelComment": {
                            "id": "T1",
                            "snippet": {
                                "authorDisplayName": "Ann",
                                "textDisplay": "Great video",
                                "likeCount": 3,
                                "publishedAt": "2026-10-02T00:00:00Z",
                            },
                        },
                    },
                    "replies": {
                        "comments": [
                            {
                                "id": "T1.R1",
                                "snippet": {
                                    "authorDisplayName": "MateAI",
                                    "textDisplay": "Thanks",
                                    "publishedAt": "2026-10-02T01:00:00Z",
                                },
                            }
                        ]
                    },
                }
            ]
        }
        out = list_video_comments("v" * 11, yt=yt)
        c = out["comments"][0]
        self.assertEqual((c["commentId"], c["author"], c["text"], c["likes"], c["replyCount"]), ("T1", "Ann", "Great video", 3, 2))
        self.assertEqual(c["replies"][0]["commentId"], "T1.R1")
        kwargs = yt.commentThreads().list.call_args.kwargs
        self.assertEqual(kwargs["videoId"], "v" * 11)
        self.assertEqual(kwargs["textFormat"], "plainText")

    def test_list_comments_rejects_bad_order(self):
        with self.assertRaises(ValueError):
            list_video_comments("v" * 11, order="newest", yt=MagicMock())

    def test_reply_inserts_under_parent(self):
        yt = MagicMock()
        yt.comments().insert().execute.return_value = {"id": "T1.R9"}
        out = reply_to_comment("T1", "Thanks!", yt=yt)
        body = yt.comments().insert.call_args.kwargs["body"]
        self.assertEqual(body, {"snippet": {"parentId": "T1", "textOriginal": "Thanks!"}})
        self.assertEqual(out, {"commentId": "T1.R9", "parentId": "T1", "text": "Thanks!"})


class TestDeleteVideo(unittest.TestCase):
    def _yt(self, title="Real Title"):
        yt = MagicMock()
        yt.videos().list().execute.return_value = {"items": [_video("v" * 11, title)]}
        return yt

    def test_deletes_only_when_title_matches(self):
        yt = self._yt()
        out = delete_video("v" * 11, confirm_title="Real Title", yt=yt)
        yt.videos().delete.assert_called_with(id="v" * 11)
        self.assertEqual(out, {"videoId": "v" * 11, "deletedTitle": "Real Title"})

    def test_refuses_on_title_mismatch(self):
        yt = self._yt()
        with self.assertRaises(ValueError):
            delete_video("v" * 11, confirm_title="Wrong", yt=yt)
        yt.videos().delete.assert_not_called()

    def test_missing_video_raises(self):
        yt = MagicMock()
        yt.videos().list().execute.return_value = {"items": []}
        with self.assertRaises(ValueError):
            delete_video("v" * 11, confirm_title="x", yt=yt)
        yt.videos().delete.assert_not_called()


class TestMcpRegistration(unittest.TestCase):
    def test_tools_registered_and_dispatched(self):
        from mcp_server import TOOLS, _handle_tool_call

        by_name = {t["name"]: t for t in TOOLS}
        for n in ("yt_list_videos", "yt_list_comments", "yt_reply_comment", "yt_delete_video"):
            self.assertIn(n, by_name)
        self.assertTrue(by_name["yt_list_videos"]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name["yt_delete_video"]["annotations"]["destructiveHint"])
        self.assertIn("confirm_title", by_name["yt_delete_video"]["inputSchema"]["required"])

        with patch("mcp_server.list_channel_videos", return_value={"videos": []}) as m:
            out = _handle_tool_call("yt_list_videos", {"query": "jev", "limit": 5})
        m.assert_called_once_with(query="jev", limit=5)
        self.assertEqual(json.loads(out["content"][0]["text"]), {"videos": []})

        with patch("mcp_server.delete_video", return_value={"videoId": "x"}) as m:
            _handle_tool_call("yt_delete_video", {"video_id": "v" * 11, "confirm_title": "T"})
        m.assert_called_once_with(video_id="v" * 11, confirm_title="T")


if __name__ == "__main__":
    unittest.main()
