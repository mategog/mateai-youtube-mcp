---
name: yt-studio
description: Connect to YouTube channels and YouTube Studio (MateAI @mateai-c6m or any handle) to fetch live video & Shorts views, retention, swipe-away rates, experiment tables, HTML dashboards, schedule uploads, update video metadata/thumbnails, and post comments.
---

# MateAI YouTube Studio & Strategy Suite (`yt-studio`)

Built by [MateAI (@mateai-c6m)](https://www.youtube.com/@mateai-c6m) · [GitHub Repo](https://github.com/mategog/mateai-youtube-mcp).

> **Shoutout & Credits:** This plugin combines MateAI's local **YouTube Studio & Analytics MCP Server** with the open-source YouTube strategy & creator workflows by **[Jeremy Longshore (`@jeremylongshore` / `youtube-strategy`)](https://github.com/jeremylongshore/tons-of-skills-marketplace/tree/main/plugins/productivity/youtube-strategy)** and **[Daniel Agrici (`@AgriciDaniel` / `claude-youtube`)](https://github.com/AgriciDaniel/claude-youtube)**.

## End-to-End AI YouTube Workflow (Strategy Skills + Live MCP Execution)

Whenever planning, scripting, packaging, uploading, or analyzing a YouTube video or Short, combine the bundled strategy skills with the live `mateai-youtube` MCP tools:

| Stage | Bundled Strategy Skill | Live `mateai-youtube` MCP Tool Used |
|---|---|---|
| **1. Surgical Analytics & Retention Autopsy** | `skills/yt-analytics/SKILL.md`, `sub-skills/audit.md` & `analyze.md` | `yt_channel_snapshot`, `yt_shorts_experiment_table`, `yt_video_details` (100-pt retention curve + spoken-word cliff mapping) |
| **2. Niche & Competitor Research** | `skills/yt-research/SKILL.md` & `sub-skills/competitor.md` | `yt_channel_snapshot(handle="@competitor", force_public=true)` |
| **3. Ideation & Validation** | `skills/yt-ideation/SKILL.md` & `sub-skills/ideate.md` | `yt_channel_snapshot` (checks outlier videos & gaps) |
| **4. Production Brief & Script** | `skills/yt-brief/SKILL.md`, `yt-outline/SKILL.md`, `sub-skills/script.md`, `sub-skills/hook.md`, `sub-skills/shorts.md` | — |
| **5. Packaging, SEO & Thumbnails** | `skills/yt-packaging/SKILL.md`, `sub-skills/seo.md`, `sub-skills/thumbnail.md`, `sub-skills/metadata.md` | `yt_update_video` (for A/B title/thumbnail swaps) |
| **6. Upload, Full Setup & Schedule** | `skills/yt-studio/SKILL.md` | `yt_upload_draft` + `yt_post_comment` |
| **7. Chapters, Title Check & Comment Replies** | `skills/yt-chapters/SKILL.md`, `skills/yt-title-lint/SKILL.md`, `skills/yt-comment/SKILL.md` | `yt_update_video` (chapters go in the description), `yt_list_comments`, `yt_reply_comment` |

## When to Use This Skill
Use this skill whenever the user asks to:
- Check YouTube channel views, subscriber growth, or video performance (for `@mateai-c6m` or any public `@handle`).
- Analyze YouTube Studio retention (`Avg % Viewed`), Shorts hook performance (`Viewed vs. Swiped Away %`), `Engaged Views`, or `Subscribers Gained`.
- Update the Shorts A/B/C visual style experiment table in `pipeline/explainer-short/README.md`.
- Upload a new video or Short (`MP4`/`MOV`), attach a custom cover (`PNG`/`JPG`), schedule a publish date/time (`publish_at` in ISO 8601), or post a pinned comment.
- Edit an existing video's title, description, tags, privacy status, or thumbnail.

## Available MCP Tools (`mateai-youtube`)
1. `yt_channel_snapshot(handle="@mateai-c6m", force_public=false)`: Pulls live Studio OAuth2 metrics (without OAuth it returns setup instructions; pass `force_public=true` only if the user asks for public-page scraping) and writes `report.html`.
2. `yt_shorts_experiment_table(handle="@mateai-c6m")`: Returns a formatted Markdown table comparing Shorts performance.
3. `yt_video_details(video_id)`: Returns metadata and stats for a single 11-char video ID.
4. `yt_upload_draft(video_path, spec_path, thumbnail_path, privacy_status="private", publish_at=None, auto_post_comment=false)`: Uploads a rendered video + Markdown spec (`## Title`, `## Description`, `## Tags`, `## Pinned comment`) to YouTube Studio as a draft or scheduled upload.
5. `yt_update_video(video_id, title, description, tags, privacy_status, publish_at, thumbnail_path, contains_synthetic_media)`: Updates packaging or schedule of an existing video. When changing `privacy_status` or `publish_at`, also pass `contains_synthetic_media` (true or false); ask the user if you don't know it.
6. `yt_post_comment(video_id, text)`: Posts a top-level comment on a video.

### TikTok tools (same server)
7. `tiktok_channel_snapshot()`: Official TikTok Display API stats for the connected account (public videos only).
8. `tiktok_upload_draft(video_path, spec_path, title, hashtags)`: Sends a Short to the TikTok inbox as a draft; the owner finishes the post in the app.
9. `tiktok_draft_status(publish_id)`: Read-only. Where an earlier TikTok upload stands (inbox, processing, posted, or failed with TikTok's reason).
10. `cross_platform_shorts_table(yt_handle, yt_force_public)`: YouTube Shorts vs TikTok comparison table.

For rules, limits and what is not built yet, read `skills/tiktok-studio/SKILL.md`.

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
