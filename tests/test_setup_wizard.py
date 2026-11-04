import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yt_setup

GOOD = {"installed": {"client_id": "id.apps.googleusercontent.com", "client_secret": "s3cret"}}


def _write(folder: Path, name: str, data, age: float = 0.0) -> Path:
    path = folder / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    if age:
        old = path.stat().st_mtime - age
        os.utime(path, (old, old))
    return path


class FindClientSecretTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.own = self.root / "own"
        self.downloads = self.root / "Downloads"
        self.own.mkdir()
        self.downloads.mkdir()
        self.since = _write(self.root, "marker", "x").stat().st_mtime - 1
        self.folders = [(self.own, False), (self.downloads, True)]

    def test_picks_fresh_valid_desktop_file(self):
        good = _write(self.downloads, "client_secret_1.json", GOOD)
        found, skipped = yt_setup.find_client_secret(self.folders, self.since)
        self.assertEqual(found, good)
        self.assertEqual(skipped, [])

    def test_ignores_non_json_web_client_and_stale_file(self):
        _write(self.downloads, "client_secret_a.json", "not json {")
        _write(self.downloads, "client_secret_b.json", {"web": GOOD["installed"]})
        _write(self.downloads, "client_secret_c.json", GOOD, age=3600)
        found, skipped = yt_setup.find_client_secret(self.folders, self.since)
        self.assertIsNone(found)
        reasons = {p.name: r for p, r in skipped}
        self.assertEqual(set(reasons), {"client_secret_a.json", "client_secret_b.json", "client_secret_c.json"})
        self.assertIn("JSON", reasons["client_secret_a.json"])
        self.assertIn('"web"', reasons["client_secret_b.json"])
        self.assertIn("fresh", reasons["client_secret_c.json"])

    def test_rejects_installed_without_secret(self):
        _write(self.downloads, "client_secret_d.json", {"installed": {"client_id": "x"}})
        found, skipped = yt_setup.find_client_secret(self.folders, self.since)
        self.assertIsNone(found)
        self.assertEqual(len(skipped), 1)

    def test_accepts_old_file_in_own_folder(self):
        old = _write(self.own, "client_secret.json", GOOD, age=86400 * 30)
        found, _ = yt_setup.find_client_secret(self.folders, self.since)
        self.assertEqual(found, old)

    def test_newest_valid_wins_and_missing_folder_is_skipped(self):
        _write(self.downloads, "client_secret_old.json", GOOD)
        newest = _write(self.downloads, "client_secret_new.json", GOOD)
        os.utime(newest, (newest.stat().st_mtime + 5,) * 2)
        _write(self.downloads, "client_secret_bad.json", "nope")
        found, _ = yt_setup.find_client_secret([(self.root / "missing", True)] + self.folders, self.since)
        self.assertEqual(found, newest)


class WaitForClientSecretTests(unittest.TestCase):
    def test_raises_on_deadline_without_real_sleep(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 0.0}
            sleeps = []

            def fake_sleep(seconds):
                sleeps.append(seconds)
                clock["now"] += seconds

            with self.assertRaises(RuntimeError) as ctx:
                yt_setup.wait_for_client_secret(
                    [(Path(tmp), False)], since=0.0, timeout=5,
                    sleep=fake_sleep, monotonic=lambda: clock["now"],
                )
            self.assertEqual(sleeps, [1.0] * 5)
            self.assertIn("Desktop app", str(ctx.exception))

    def test_returns_file_that_appears_while_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            calls = []

            def fake_sleep(_):
                calls.append(1)
                if len(calls) == 2:
                    _write(folder, "client_secret_x.json", GOOD)

            with mock.patch("builtins.print"):
                found = yt_setup.wait_for_client_secret(
                    [(folder, False)], since=0.0, timeout=60,
                    sleep=fake_sleep, monotonic=lambda: 0.0,
                )
            self.assertEqual(found.name, "client_secret_x.json")
            self.assertEqual(len(calls), 2)

    def test_skipped_file_is_logged_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _write(folder, "client_secret_bad.json", "nope")
            clock = {"now": 0.0}

            def fake_sleep(s):
                clock["now"] += s

            with mock.patch("builtins.print") as fake_print, self.assertRaises(RuntimeError):
                yt_setup.wait_for_client_secret(
                    [(folder, False)], since=0.0, timeout=3,
                    sleep=fake_sleep, monotonic=lambda: clock["now"],
                )
            self.assertEqual(fake_print.call_count, 1)


if __name__ == "__main__":
    unittest.main()
