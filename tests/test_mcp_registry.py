import io
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
        self.assertEqual(len(names), 15)

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


if __name__ == "__main__":
    unittest.main()
