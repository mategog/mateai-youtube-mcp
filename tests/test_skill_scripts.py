import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(rel):
    spec = importlib.util.spec_from_file_location(Path(rel).stem, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chapters = _load("skills/yt-chapters/chapters.py")
title = _load("skills/yt-title-lint/title.py")

VTT = """WEBVTT

00:00:00.000 --> 00:00:04.000
hello <c>welcome</c> to the channel

00:00:04.000 --> 00:00:08.000
hello <c>welcome</c> to the channel

00:00:09.000 --> 00:00:12.000
second line
"""


class ChaptersTests(unittest.TestCase):
    def _load_vtt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.vtt"
            p.write_text(VTT)
            return chapters.load(str(p))

    def test_vtt_strips_tags_and_repeats(self):
        cues = self._load_vtt()
        self.assertEqual([c[2] for c in cues], ["hello welcome to the channel", "second line"])

    def test_parse_ts(self):
        self.assertEqual(chapters.parse_ts("00:01:02,500"), 62.5)
        self.assertEqual(chapters.parse_ts("01:02.5"), 62.5)


class TitleLintTests(unittest.TestCase):
    def test_long_title_without_digit(self):
        r = title.check("I Built a Live Cost Meter for Claude Code and Measured a Real Task")
        kinds = {k for k, _ in r["issues"]}
        self.assertTrue({"length", "no-number"} <= kinds)

    def test_thumbnail_repeating_title_is_flagged(self):
        r = title.check("I spent 30 days on Jev", "30 DAYS")
        self.assertIn("duplicate", {k for k, _ in r["issues"]})


if __name__ == "__main__":
    unittest.main()
