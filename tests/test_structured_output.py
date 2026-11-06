"""Tools that declare an outputSchema must return structuredContent that matches it (MCP spec;
Claude Desktop rejects the result otherwise). Covers the dry-run paths, whose shapes differ."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mcp_server
import yt_common

TYPES = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}


def problems(value, schema, path="$"):
    """The subset of JSON Schema these tools use: type, properties, required, items, enum."""
    out = []
    types = schema.get("type")
    if types:
        types = [types] if isinstance(types, str) else types
        if not any(isinstance(value, TYPES[t]) and not (t == "integer" and isinstance(value, bool)) for t in types):
            return [f"{path}: {type(value).__name__} is not {types}"]
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, dict):
        out += [f"{path}: missing {k}" for k in schema.get("required", []) if k not in value]
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                out += problems(value[k], sub, f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            out += problems(item, schema["items"], f"{path}[{i}]")
    return out


SCHEMAS = {t["name"]: t["outputSchema"] for t in mcp_server.TOOLS if "outputSchema" in t}
VID = "abcdefghijk"


class StructuredOutputTests(unittest.TestCase):
    def check(self, name, args):
        result = mcp_server._HANDLERS[name](args)
        self.assertNotIn("isError", result)
        self.assertEqual(result["structuredContent"], json.loads(result["content"][0]["text"]))
        self.assertEqual(problems(result["structuredContent"], SCHEMAS[name]), [])
        return result["structuredContent"]

    def test_every_schema_tool_is_covered(self):
        self.assertEqual(set(SCHEMAS), {
            "yt_channel_snapshot", "yt_video_details", "yt_upload_draft", "yt_update_video", "yt_post_comment"})

    def test_channel_snapshot(self):
        snap = yt_common.snapshot_envelope("studio_oauth", {"title": "C"}, [], youtube_counts=True)
        with mock.patch.object(mcp_server, "get_best_snapshot", return_value=snap), \
             mock.patch.object(mcp_server, "render_html_report"):
            self.check("yt_channel_snapshot", {})

    def test_video_details_includes_description_and_tags(self):
        text = {"title": "T", "description": "D", "tags": ["a"], "privacyStatus": "private", "publishAt": "2026-11-06T17:00:00Z"}
        with mock.patch.object(mcp_server, "fetch_video_text", return_value=text), \
             mock.patch.object(mcp_server, "fetch_video_retention_diagnosis", return_value={"hasRetentionCurve": False}):
            out = self.check("yt_video_details", {"video_id": VID})
        self.assertEqual((out["description"], out["tags"]), ("D", ["a"]))

    def test_video_details_survives_a_failed_text_fetch(self):
        with mock.patch.object(mcp_server, "fetch_video_text", side_effect=ValueError("not found")), \
             mock.patch.object(mcp_server, "fetch_video_retention_diagnosis", return_value={}):
            out = self.check("yt_video_details", {"video_id": VID})
        self.assertEqual(out["videoTextError"], "not found")

    def test_upload_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "v.mp4"
            video.write_bytes(b"0")
            self.check("yt_upload_draft", {"video_path": str(video), "title": "T", "dry_run": True})

    def test_update_dry_run(self):
        self.check("yt_update_video", {"video_id": VID, "title": "T", "dry_run": True})

    def test_comment_dry_run(self):
        self.check("yt_post_comment", {"video_id": VID, "text": "hi", "dry_run": True})


if __name__ == "__main__":
    unittest.main()
