import io
import itertools
import json
import unittest
from unittest import mock

import mcp_server


def _run_main(*messages: dict) -> list[dict]:
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    stdout = io.StringIO()
    with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout):
        mcp_server.main()
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


class RegistryTests(unittest.TestCase):
    def test_every_schema_has_a_handler_and_vice_versa(self):
        names = [t["name"] for t in mcp_server.TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(mcp_server._HANDLERS))
        self.assertEqual(len(names), 16)

    def test_tools_list_matches_listed_tools(self):
        (resp,) = _run_main({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(resp["result"]["tools"], mcp_server.listed_tools())

    def test_unknown_tool_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "Unknown tool: nope"):
            mcp_server._handle_tool_call("nope", {})

    def test_tools_call_round_trip_and_error_wrapping(self):
        with mock.patch.object(mcp_server, "list_channel_videos", return_value=[{"videoId": "x"}]) as m:
            ok, bad, unknown = _run_main(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "yt_list_videos", "arguments": {"query": "q", "limit": 3}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "yt_list_comments", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}},
            )
        m.assert_called_once_with(query="q", limit=3)
        self.assertEqual(ok["result"]["content"][0]["text"], json.dumps([{"videoId": "x"}], indent=2))
        self.assertTrue(bad["result"]["isError"])
        self.assertEqual(unknown["result"], {"isError": True, "content": [{"type": "text", "text": "Error: Unknown tool: nope"}]})

    def test_list_comments_marks_viewer_text_as_untrusted(self):
        with mock.patch.object(mcp_server, "list_video_comments", return_value={"videoId": "v" * 11, "comments": []}):
            out = mcp_server._handle_tool_call("yt_list_comments", {"video_id": "v" * 11})
        data = json.loads(out["content"][0]["text"])
        self.assertEqual(data["untrustedContent"], mcp_server.UNTRUSTED_COMMENTS_NOTE)
        self.assertEqual(data["comments"], [])


class ConfirmationDialogTests(unittest.TestCase):
    """The delete gate over the real stdio loop: the client, not the model, answers elicitation/create."""

    DELETE = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "yt_delete_video",
                         "arguments": {"video_id": "v" * 11, "confirm_title": "T", "user_confirmed": True}}}

    def setUp(self):
        patcher = mock.patch.object(mcp_server, "_ELICIT_IDS", itertools.count(1))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _answer(self, **kwargs):
        return {"jsonrpc": "2.0", "id": "mateai-confirm-1", **kwargs}

    def test_accept_runs_and_messages_sent_meanwhile_are_still_handled(self):
        with mock.patch.object(mcp_server, "delete_video", return_value={"videoId": "v" * 11}) as delete:
            asked, pong, done, listed = _run_main(
                self.DELETE,
                {"jsonrpc": "2.0", "id": 9, "method": "ping"},
                {"jsonrpc": "2.0", "id": 10, "method": "tools/list"},
                self._answer(result={"action": "accept", "content": {"confirm": True}}),
            )
        self.assertEqual(asked["method"], "elicitation/create")
        self.assertIn("Delete a video", asked["params"]["message"])
        self.assertEqual(pong, {"jsonrpc": "2.0", "id": 9, "result": {}})
        delete.assert_called_once_with(video_id="v" * 11, confirm_title="T")
        self.assertEqual(done["id"], 1)
        self.assertNotIn("isError", done["result"])
        self.assertEqual(listed["id"], 10)

    def test_decline_or_unchecked_box_does_nothing(self):
        for answer in ({"action": "decline"}, {"action": "cancel"}, {"action": "accept", "content": {"confirm": False}}):
            with mock.patch.object(mcp_server, "_ELICIT_IDS", itertools.count(1)), \
                    mock.patch.object(mcp_server, "delete_video") as delete:
                _, done = _run_main(self.DELETE, self._answer(result=answer))
            delete.assert_not_called()
            self.assertIn("DECLINED", done["result"]["content"][0]["text"])

    def test_client_without_elicitation_cannot_delete_even_with_the_flag(self):
        with mock.patch.object(mcp_server, "delete_video") as delete:
            _, done = _run_main(self.DELETE, self._answer(error={"code": -32601, "message": "Method not found"}))
        delete.assert_not_called()
        self.assertIn("NOT DONE", done["result"]["content"][0]["text"])

    def test_stdin_closing_mid_dialog_does_nothing(self):
        with mock.patch.object(mcp_server, "delete_video") as delete:
            (_, done) = _run_main(self.DELETE)
        delete.assert_not_called()
        self.assertTrue(done["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
