---
name: yt-studio
description: Connect to YouTube channels and YouTube Studio (MateAI @mateai-c6m or any handle) to fetch live video & Shorts views, retention, swipe-away rates, experiment tables, HTML dashboards, schedule uploads, update video metadata/thumbnails, and post comments.
---

# MateAI YouTube Studio & Analytics Skill (`yt-studio`)

Built by [MateAI (@mateai-c6m)](https://www.youtube.com/@mateai-c6m) · [GitHub Repo](https://github.com/mategog/mateai-youtube-mcp).

## When to Use This Skill
Use this skill whenever the user asks to:
- Check YouTube channel views, subscriber growth, or video performance (for `@mateai-c6m` or any public `@handle`).
- Analyze YouTube Studio retention (`Avg % Viewed`), Shorts hook performance (`Viewed vs. Swiped Away %`), `Engaged Views`, or `Subscribers Gained`.
- Update the Shorts A/B/C visual style experiment table in `pipeline/explainer-short/README.md`.
- Upload a new video or Short (`MP4`/`MOV`), attach a custom cover (`PNG`/`JPG`), schedule a publish date/time (`publish_at` in ISO 8601), or post a pinned comment.
- Edit an existing video's title, description, tags, privacy status, or thumbnail.

## Available MCP Tools (`mateai-youtube`)
1. `yt_channel_snapshot(handle="@mateai-c6m", force_public=false)`: Pulls live Studio OAuth2 metrics (or falls back to zero-config Public Mode if no token exists) and writes `report.html`.
2. `yt_shorts_experiment_table(handle="@mateai-c6m")`: Returns a formatted Markdown table comparing Shorts performance.
3. `yt_video_details(video_id)`: Returns metadata and stats for a single 11-char video ID.
4. `yt_upload_draft(video_path, spec_path, thumbnail_path, privacy_status="private", publish_at=None, auto_post_comment=false)`: Uploads a rendered video + Markdown spec (`## Title`, `## Description`, `## Tags`, `## Pinned comment`) to YouTube Studio as a draft or scheduled upload.
5. `yt_update_video(video_id, title, description, tags, privacy_status, publish_at, thumbnail_path)`: Updates packaging or schedule of an existing video.
6. `yt_post_comment(video_id, text)`: Posts a top-level comment on a video.

## CLI Fallback Commands
If running via terminal from `/Users/mategog/Documents/Yt/MateAI/builds/03-yt-studio-mcp`:

```bash
# 1. Fetch live Studio OAuth snapshot & render report.html
python3 yt_studio.py snapshot

# 2. Generate Shorts Style Experiment Markdown Table
python3 yt_studio.py experiment-table

# 3. Re-authenticate or switch YouTube Brand Channel
python3 yt_studio.py auth

# 4. Upload a rendered Short/Video + upload spec as a Private Draft in Studio
python3 yt_studio.py upload-draft \
  --video ../../exports/gemini-4-carbon-poster.mp4 \
  --spec ../../planning/gemini-4-carbon-upload.md \
  --thumbnail ../../assets/thumbnails/gemini-4-carbon-poster.png
```
