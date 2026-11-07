"""Windows support: venv layout, secret files without POSIX modes, and UTF-8 stdio.

These run on every OS; the Windows branches are exercised by patching yt_common.IS_WINDOWS,
and for real in the windows-latest CI job.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tiktok_studio
import yt_common

REPO = Path(__file__).resolve().parent.parent


class TestVenvLayout(unittest.TestCase):
    def test_venv_python_is_scripts_python_exe_on_windows(self):
        with mock.patch.object(yt_common, "IS_WINDOWS", True):
            self.assertEqual(yt_common.venv_python(Path("v")), Path("v") / "Scripts" / "python.exe")

    def test_venv_python_is_bin_python_elsewhere(self):
        with mock.patch.object(yt_common, "IS_WINDOWS", False):
            self.assertEqual(yt_common.venv_python(Path("v")), Path("v") / "bin" / "python")

    def test_venv_python_defaults_to_the_state_dir_venv(self):
        self.assertEqual(yt_common.venv_python().parent.parent, yt_common.STATE_DIR / ".venv")

    def test_site_packages_windows_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp)
            sp = venv / "Lib" / "site-packages"
            sp.mkdir(parents=True)
            with mock.patch.object(yt_common, "IS_WINDOWS", True):
                self.assertEqual(yt_common.venv_site_packages(venv), [sp])

    def test_site_packages_windows_layout_missing_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(yt_common, "IS_WINDOWS", True):
            self.assertEqual(yt_common.venv_site_packages(Path(tmp)), [])

    def test_site_packages_posix_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp)
            sp = venv / "lib" / "python3.12" / "site-packages"
            sp.mkdir(parents=True)
            with mock.patch.object(yt_common, "IS_WINDOWS", False):
                self.assertEqual(yt_common.venv_site_packages(venv), [sp])


class TestSecretFilesOnWindows(unittest.TestCase):
    def test_write_secret_file_skips_fchmod_on_windows(self):
        # Python before 3.13 has no os.fchmod on Windows, so calling it would crash the TikTok login.
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(yt_common, "IS_WINDOWS", True), \
                mock.patch.object(os, "fchmod", side_effect=AssertionError("fchmod called"), create=True):
            p = Path(tmp) / "sub" / "tiktok_token.json"
            tiktok_studio._write_secret_file(p, '{"access_token":"árvíztűrő"}')
            self.assertEqual(p.read_text(encoding="utf-8"), '{"access_token":"árvíztűrő"}')

    def test_history_lines_end_with_a_bare_newline(self):
        snap = {"channel": {"followers": 1}, "videos": [{"videoId": "1", "views": 2}]}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "tiktok_history.jsonl"
            self.assertTrue(tiktok_studio.append_tiktok_history(snap, history_file=p))
            self.assertTrue(p.read_bytes().endswith(b"}\n"))
            self.assertNotIn(b"\r\n", p.read_bytes())


class TestUtf8Stdio(unittest.TestCase):
    def test_reconfigures_cp1252_streams_to_utf8(self):
        def cp1252():
            return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")

        fake = {"stdin": cp1252(), "stdout": cp1252(), "stderr": cp1252()}
        with mock.patch.multiple(sys, **fake):
            yt_common.use_utf8_stdio()
            sys.stdout.write("✓ árvíztűrő 👀\n")
            sys.stdout.flush()
            self.assertEqual(fake["stdout"].buffer.getvalue(), "✓ árvíztűrő 👀\n".encode("utf-8"))
            self.assertEqual(sys.stdin.encoding, "utf-8")

    def test_mcp_server_reads_utf8_even_when_python_defaults_to_cp1252(self):
        # PYTHONIOENCODING=cp1252 reproduces what Windows Python (before 3.15) does with piped stdio.
        env = {**os.environ, "PYTHONIOENCODING": "cp1252", "MATEAI_YT_HOME": tempfile.mkdtemp()}
        request = {"jsonrpc": "2.0", "id": 7, "method": "árvíztűrő/tükörfúrógép", "params": {}}
        out = subprocess.run(
            [sys.executable, str(REPO / "mcp_server.py")],
            input=(json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"),
            capture_output=True, cwd=REPO, env=env, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"\r\n", out.stdout)
        reply = json.loads(out.stdout.decode("utf-8").splitlines()[0])
        self.assertEqual(reply["error"]["message"], "Method not found: árvíztűrő/tükörfúrógép")


if __name__ == "__main__":
    unittest.main()
