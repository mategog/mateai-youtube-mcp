"""
mateai-youtube-mcp — Interactive one-command setup wizard
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import yt_auth
import yt_common
import yt_snapshot


CLIENT_SECRET_WAIT_SECONDS = 10 * 60


def _client_secret_problem(path: Path) -> str | None:
    """Why this file is not a Google OAuth Desktop client, or None when it is one."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"not readable JSON ({type(exc).__name__})"
    if not isinstance(data, dict):
        return "not a JSON object"
    installed = data.get("installed")
    if isinstance(installed, dict) and installed.get("client_id") and installed.get("client_secret"):
        return None
    if "installed" in data:
        return 'its "installed" section lacks client_id or client_secret'
    kind = next(iter(data), "")
    return f'it is a "{kind}" client, not a Desktop app client'


def find_client_secret(folders: list[tuple[Path, bool]], since: float) -> tuple[Path | None, list[tuple[Path, str]]]:
    """Newest valid Desktop client_secret*.json from the first folder that has one.

    `folders` is (folder, fresh_only) in priority order; with fresh_only a file must have been
    modified at or after `since` (epoch seconds). Returns (path or None, [(skipped file, reason)]).
    """
    skipped: list[tuple[Path, str]] = []
    for folder, fresh_only in folders:
        if not folder.exists():
            continue
        candidates: list[tuple[float, Path]] = []
        for path in folder.glob("client_secret*.json"):
            try:
                mtime = path.stat().st_mtime
            except OSError as exc:
                skipped.append((path, f"cannot stat ({type(exc).__name__})"))
                continue
            if fresh_only and mtime < since:
                skipped.append((path, "older than this setup run (not a fresh download)"))
                continue
            problem = _client_secret_problem(path)
            if problem:
                skipped.append((path, problem))
                continue
            candidates.append((mtime, path))
        if candidates:
            return max(candidates)[1], skipped
    return None, skipped


def wait_for_client_secret(
    folders: list[tuple[Path, bool]],
    since: float,
    timeout: float = CLIENT_SECRET_WAIT_SECONDS,
    sleep=None,
    monotonic=None,
) -> Path:
    """Poll once a second until find_client_secret succeeds; RuntimeError after `timeout` seconds."""
    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    deadline = monotonic() + timeout
    reported: set[tuple[Path, str]] = set()
    while True:
        found, skipped = find_client_secret(folders, since)
        for item in skipped:
            if item not in reported:
                reported.add(item)
                print(f"      Skipping {item[0]}: {item[1]}")
        if found:
            return found
        if monotonic() >= deadline:
            raise RuntimeError(
                f"No valid Desktop OAuth client file appeared within {int(timeout // 60)} minutes. "
                "In Google Cloud Console create an OAuth client with Application type = Desktop app, "
                "click Download JSON (it saves to ~/Downloads), then run the setup again. "
                f"A file downloaded before this run started is ignored; copy it into {folders[0][0]} instead."
            )
        sleep(1.0)


def run_interactive_setup_wizard() -> None:
    """Zero-friction guided setup: auto-installs .venv, enables APIs, watches ~/Downloads for JSON, and logs in."""
    import shutil
    import subprocess
    import time
    import webbrowser

    print("=" * 72)
    print("  MateAI YouTube Studio MCP — Guided 1-Command Setup Wizard")
    print("=" * 72)

    # Step 1: Ensure .venv and Google API client packages exist
    venv_py = yt_common.STATE_DIR / ".venv" / "bin" / "python"
    if not venv_py.exists():
        print("\n[1/4] Creating local Python virtualenv (.venv) and installing Google API SDK...")
        subprocess.run([sys.executable, "-m", "venv", str(yt_common.STATE_DIR / ".venv")], check=True)
        subprocess.run([str(yt_common.STATE_DIR / ".venv" / "bin" / "pip"), "install", "-q", "-r", str(yt_common.HERE / "requirements.txt")], check=True)
        yt_common.add_venv_to_path()
    else:
        print("\n[1/4] Python virtualenv (.venv) is ready.")

    # Step 2: Enable YouTube Data API v3 & YouTube Analytics API
    print("\n[2/4] Enabling YouTube Data API v3 & YouTube Analytics API...")
    gcloud_bin = shutil.which("gcloud")
    apis_enabled_via_cli = False
    if gcloud_bin:
        try:
            proj = subprocess.check_output([gcloud_bin, "config", "get-value", "project"], text=True, stderr=subprocess.DEVNULL).strip()
            if proj and proj != "(unset)":
                print(f"      Found active gcloud project '{proj}'. Enabling YouTube APIs automatically...")
                res = subprocess.run(
                    [gcloud_bin, "services", "enable", "youtube.googleapis.com", "youtubeanalytics.googleapis.com"],
                     capture_output=True, text=True
                )
                if res.returncode == 0:
                    print("      ✓ Enabled youtube.googleapis.com and youtubeanalytics.googleapis.com via gcloud!")
                    apis_enabled_via_cli = True
        except Exception:
            pass

    if not apis_enabled_via_cli:
        print("      Opening direct 1-click API enablement pages in your browser...")
        webbrowser.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com")
        webbrowser.open("https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com")

    # Step 3: Check or watch for client_secret.json
    secret_dir = yt_common.STATE_DIR / "google_auth_secret"
    secret_dir.mkdir(parents=True, exist_ok=True)
    secret_path = yt_auth._resolve_default_client_secret()

    if not secret_path.exists():
        print("\n[3/4] Waiting for your Desktop OAuth JSON file...")
        print("      1. Add your YouTube email under 'Test users': https://console.cloud.google.com/auth/audience")
        print("      2. Create a 'Desktop app' OAuth client & click 'Download JSON': https://console.cloud.google.com/auth/clients/create")
        webbrowser.open("https://console.cloud.google.com/auth/audience")
        webbrowser.open("https://console.cloud.google.com/auth/clients/create")

        downloads = Path.home() / "Downloads"
        desktop = Path.home() / "Desktop"
        print(f"\n      👀 Watching ~/Downloads and {secret_dir} for client_secret*.json (Ctrl+C to cancel)...")
        # Own folders are trusted at any age; browser download folders only for a file saved from now on.
        folders = [
            (secret_dir, False),
            (yt_common.STATE_DIR, False),
            (downloads, True),
            (desktop, True),
        ]
        found_file = wait_for_client_secret(folders, since=time.time())

        target = secret_dir / "client_secret.json"
        if found_file.resolve() != target.resolve():
            shutil.copy2(found_file, target)
        os.chmod(target, 0o600)
        secret_path = target
        print(f"      ✓ Auto-imported {found_file} -> {target} (mode 0600)")
    else:
        print(f"\n[3/4] Found existing OAuth client secret: {secret_path.name}")

    # Step 4: Launch OAuth browser login & pull live Studio snapshot
    print("\n[4/4] Launching Google account & YouTube channel selector in your browser...")
    yt_auth.get_oauth_credentials(client_secret_path=secret_path, upload_scope=True, force_reauth=True)
    snap = yt_snapshot.fetch_studio_channel_snapshot(client_secret_path=secret_path)
    yt_common.CACHE_FILE.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    if yt_common.TEMPLATE_FILE.exists():
        yt_snapshot.render_html_report(snap, yt_common.REPORT_FILE)
        webbrowser.open(yt_common.REPORT_FILE.as_uri())
    print("\n✓ Setup complete! Live Studio snapshot:")
    yt_snapshot.print_cli_summary(snap)
