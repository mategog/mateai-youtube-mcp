---
name: yt-studio
description: Connect to YouTube channels and YouTube Studio (MateAI @mateai-c6m or any handle) to fetch live video & Shorts views, retention, swipe-away rates, experiment tables, HTML dashboards, and upload private drafts.
---

# YouTube Studio & Analytics Skill (`mateai-youtube-mcp`)

Built by [MateAI (@mateai-c6m)](https://www.youtube.com/@mateai-c6m).

## Quick Commands

Run from `/Users/mategog/Documents/Yt/MateAI/builds/03-yt-studio-mcp`:

```bash
# 1. Fetch live channel snapshot (Public mode or OAuth Studio mode) & render report.html
python3 yt_studio.py snapshot --handle @mateai-c6m

# 2. Generate the Shorts Style Experiment Markdown Table
python3 yt_studio.py experiment-table --handle @mateai-c6m

# 3. Authenticate with Google Cloud OAuth2 (once client_secret.json is placed in folder)
.venv/bin/python yt_studio.py auth

# 4. Upload a rendered Short/Video + upload spec as a Private Draft in Studio
.venv/bin/python yt_studio.py upload-draft \
  --video ../../exports/gemini-4-carbon-poster.mp4 \
  --spec ../../planning/gemini-4-carbon-upload.md \
  --thumbnail ../../assets/thumbnails/gemini-4-carbon-poster.png
```
