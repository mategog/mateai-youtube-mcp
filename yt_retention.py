"""
mateai-youtube-mcp — Audience retention curve, traffic sources and drop-off diagnosis
Copyright (c) 2026 MateAI (https://www.youtube.com/@mateai-c6m | https://github.com/mategog)
Licensed under Apache 2.0 with Commons Clause Restriction v1.0 (Free to use, no commercial resale/SaaS).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import yt_auth
from yt_auth import DEFAULT_CLIENT_SECRET
from yt_common import _parse_iso_duration


def fetch_video_retention_diagnosis(
    video_id: str,
    words_or_script_path: Path | None = None,
    days: int = 365,
    client_secret_path: Path = DEFAULT_CLIENT_SECRET,
) -> dict[str, Any]:
    """
    Pull the 100-point audience retention curve (audienceWatchRatio + relativeRetentionPerformance),
    traffic sources, and cross-reference steepest drop-off timestamps against spoken words if available.
    """
    yt, yta = yt_auth._youtube_and_analytics_clients(client_secret_path)

    v_resp = yt.videos().list(part="snippet,contentDetails,statistics", id=video_id).execute()
    if not v_resp.get("items"):
        raise ValueError(f"Video not found: {video_id}")
    v_item = v_resp["items"][0]
    title = v_item["snippet"]["title"]
    dur_sec = _parse_iso_duration(v_item["contentDetails"].get("duration", "PT0S"))

    end_date = dt.date.today().isoformat()
    start_date = (dt.date.today() - dt.timedelta(days=days)).isoformat()

    # A failed call is reported in `errors`, so "Google refused" never looks like "no data".
    errors: list[str] = []

    # 1. Traffic sources for this video
    traffic_sources: list[dict[str, Any]] = []
    try:
        ts_rep = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched",
            dimensions="insightTrafficSourceType",
            filters=f"video=={video_id}",
            sort="-views",
        ).execute()
        for r in ts_rep.get("rows", []):
            traffic_sources.append({
                "sourceType": r[0],
                "views": int(r[1]),
                "watchTimeMin": round(float(r[2]), 1),
            })
    except Exception as exc:
        errors.append(f"trafficSources: {exc}")

    # 2. 100-point Audience Retention curve
    curve_rows: list[list[float]] = []
    try:
        rc_rep = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
        ).execute()
        curve_rows = rc_rep.get("rows", [])
    except Exception as exc:
        errors.append(f"retentionCurve: {exc}")

    # Optional: load word timings from words.js / json if provided
    timed_words: list[dict[str, Any]] = []
    if words_or_script_path and words_or_script_path.exists():
        raw_txt = words_or_script_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\[.*\]", raw_txt, flags=re.DOTALL)
        if m:
            try:
                timed_words = json.loads(m.group(0))
            except ValueError as exc:
                errors.append(f"wordTimings: could not parse {words_or_script_path.name}: {exc}")

    def _spoken_around(sec: float, window: float = 5.0) -> str:
        if not timed_words:
            return ""
        tokens = [
            str(w.get("w", ""))
            for w in timed_words
            if isinstance(w, dict) and (sec - 2.0) <= float(w.get("s", -999)) <= (sec + window)
        ]
        return " ".join(tokens).strip()

    checkpoints: dict[str, Any] = {}
    steepest_drops: list[dict[str, Any]] = []

    if curve_rows and dur_sec > 0:
        for pct_target, label in [(0.03, "hook_3pct"), (0.10, "10pct"), (0.25, "25pct"), (0.50, "50pct"), (0.75, "75pct"), (1.00, "100pct")]:
            closest = min(curve_rows, key=lambda r: abs(float(r[0]) - pct_target))
            sec = int(round(float(closest[0]) * dur_sec))
            checkpoints[label] = {
                "timestampSec": sec,
                "timestampFmt": f"{sec // 60}:{sec % 60:02d}",
                "watchingPct": round(float(closest[1]) * 100, 1),
                "youtubePeerPercentile": round(float(closest[2]) * 100, 1),
            }

        diffs = []
        for i in range(1, len(curve_rows)):
            prev_r = float(curve_rows[i - 1][1])
            curr_r = float(curve_rows[i][1])
            delta = curr_r - prev_r
            ratio_pt = float(curve_rows[i][0])
            sec = int(round(ratio_pt * dur_sec))
            diffs.append({
                "timestampSec": sec,
                "timestampFmt": f"{sec // 60}:{sec % 60:02d}",
                "videoProgressPct": int(round(ratio_pt * 100)),
                "beforeWatchingPct": round(prev_r * 100, 1),
                "afterWatchingPct": round(curr_r * 100, 1),
                "dropPctPoints": round(delta * 100, 1),
                "youtubePeerPercentile": round(float(curve_rows[i][2]) * 100, 1),
                "spokenWordsAtCliff": _spoken_around(sec),
            })
        diffs.sort(key=lambda x: x["dropPctPoints"])
        steepest_drops = diffs[:5]

    return {
        "videoId": video_id,
        "title": title,
        "durationSec": dur_sec,
        "durationFmt": f"{dur_sec // 60}:{dur_sec % 60:02d}",
        "trafficSources": traffic_sources,
        "retentionCheckpoints": checkpoints,
        "steepestDropOffCliffs": steepest_drops,
        "hasRetentionCurve": bool(curve_rows),
        **({"errors": errors} if errors else {}),
    }
