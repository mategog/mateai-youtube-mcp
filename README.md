# <img src="assets/logo.png" width="44" align="absmiddle" alt="MateAI YouTube Studio Icon"/> mateai-youtube-mcp

[![Release](https://img.shields.io/github/v/release/mategog/mateai-youtube-mcp?color=238636)](https://github.com/mategog/mateai-youtube-mcp/releases/tag/v1.0.0)
[![YouTube Channel](https://img.shields.io/badge/YouTube-@mateai--c6m-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/@mateai-c6m)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support%20MateAI-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/epuplanner)
[![License: Apache 2.0 + Commons Clause](https://img.shields.io/badge/License-Apache%202.0%20%2B%20Commons%20Clause-blue.svg)](LICENSE)

![MateAI YouTube Studio & Shorts Experiment Dashboard](assets/dashboard-preview.png)

A local, self-hosted **YouTube Studio & Analytics MCP Connector + Creator Strategy Plugin** for **Google Antigravity** and **Claude Code / Claude Desktop**, built for the [MateAI](https://www.youtube.com/@mateai-c6m) channel.

Most open-source YouTube MCP servers only scrape subtitles with `yt-dlp`. Tools that connect to your actual **YouTube Studio Analytics** (retention, Shorts swipe-away rates, subscribers gained) or **upload drafts** usually charge $19–$49/month as hosted SaaS wrappers around Google's free APIs.

This connector runs **100% locally on your machine for $0/month**:
- **Zero-Config Public Mode (works instantly, stdlib only):** Pulls live channel stats, Long-form videos, Shorts, view counts, and likes for any `@handle` and renders a local `report.html` dashboard.
- **Studio OAuth2 Mode (free Google Cloud API):** Pulls private **YouTube Analytics API v2** metrics (*Average % viewed*, *Viewed vs. swiped away*, *Engaged views*, *Watch time*, *Subscribers gained*) and uploads rendered videos + thumbnails as **Private Drafts** in YouTube Studio.

---

## Quick Start (Zero-Config Public Snapshot)

No API keys or packages needed—runs with Python 3 standard library out of the box:

```bash
git clone https://github.com/mategog/mateai-youtube-mcp.git
cd mateai-youtube-mcp

python3 yt_studio.py snapshot --handle @mateai-c6m
open report.html
```

Print a Markdown table for tracking Shorts A/B style experiments:

```bash
python3 yt_studio.py experiment-table --handle @mateai-c6m
```

---

## Install as a Plugin (Antigravity & Claude Code)

`mateai-youtube-mcp` ships as a full **Plugin** (bundling the MCP Server + the `yt-studio` AI Producer Skill + UI card & starter prompts).

### Option A: Google Antigravity
Clone directly into your Antigravity plugins directory and restart Antigravity:

```bash
git clone https://github.com/mategog/mateai-youtube-mcp.git \
  ~/.gemini/config/plugins/mateai-youtube
```

### Option B: Claude Code
Install directly from the plugin marketplace:

```bash
claude plugin marketplace add mategog/mateai-youtube-mcp
claude plugin install yt-studio@mateai-youtube-mcp
```

### Option C: Standalone MCP Config (`mcp_config.json` / `claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "mateai-youtube": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/mateai-youtube-mcp/mcp_server.py"]
    }
  }
}
```

### Exposed MCP Tools
| Tool | Description |
|---|---|
| `yt_channel_snapshot` | Fetch channel overview, Long-form uploads, Shorts stats, and update `report.html`. |
| `yt_shorts_experiment_table` | Generate a Markdown table comparing Shorts retention, swipe-away rate, and views. |
| `yt_video_details` | Inspect metadata and metrics for any 11-character YouTube `video_id`. |
| `yt_upload_draft` | Upload a local MP4/MOV + cover image + full Studio setup (`title`, `description`, `hashtags`, `tags`, `language`, `contains_synthetic_media`, `pinned_comment`, and **`publish_at` schedule**). |
| `yt_update_video` | Update title, description, tags, privacy status, schedule time, or thumbnail of an existing video. |
| `yt_post_comment` | Post a top-level comment (e.g. your `## Pinned comment` question) on a video. |

---

## Bundled YouTube Strategy & Creator Skills (Full Pipeline)

This plugin integrates the **YouTube Strategy & Creator Skill Suite** directly alongside the `mateai-youtube` MCP server, so your AI agent handles everything from niche research and hook writing to live Studio scheduling:

- **Production Pipeline Skills** (`yt-research`, `yt-ideation`, `yt-brief`, `yt-packaging`, `yt-outline`, plus `/yt-pipeline` command and `yt-scraper`, `channel-analyzer`, `idea-validator` agents) — created by **[Jeremy Longshore (`@jeremylongshore` / Intent Solutions)](https://github.com/jeremylongshore/tons-of-skills-marketplace/tree/main/plugins/productivity/youtube-strategy)** (`@intentsolutionsio/youtube-strategy`, MIT).
- **14 Creator Sub-Skills & Playbooks** (`audit`, `seo`, `script`, `hook`, `thumbnail`, `strategy`, `calendar`, `shorts`, `analyze`, `repurpose`, `monetize`, `competitor`, `metadata`, `ideate`) — created by **[Daniel Agrici (`@AgriciDaniel`)](https://github.com/AgriciDaniel/claude-youtube)** (`claude-youtube`, MIT).
- **Live YouTube Studio Execution & Analytics MCP** (`yt_channel_snapshot`, `yt_shorts_experiment_table`, `yt_upload_draft`, `yt_update_video`, `yt_post_comment`, interactive `report.html` dashboard & 1-command `setup` wizard) — built by **[MateAI (`@mateai-c6m`)](https://www.youtube.com/@mateai-c6m)**.

---

## Unlock Private YouTube Studio Analytics & Draft Uploads ($0/mo)

Google gives every developer **10,000 free quota units/day** on the YouTube Data API v3 and YouTube Analytics API v2. Because you run this locally for your own channel in "Testing" mode, **no Google app verification is required** and you keep 100% of your own private quota.

Run the **1-Command Guided Setup Wizard**:

```bash
python3 yt_studio.py setup
```

What `python3 yt_studio.py setup` does automatically:
1. **Creates `.venv` & installs Google's OAuth libraries** automatically if not yet installed.
2. **Auto-enables the YouTube APIs via `gcloud`** (if you have the `gcloud` CLI installed), or pops open the direct 1-click enablement pages.
3. **Opens the exact Test User & Create Desktop Client screens** and **watches your `~/Downloads` folder in real time**—the instant you click **"Download JSON"** in your browser, the wizard automatically grabs `client_secret_*.json` from `~/Downloads`, moves it into `google_auth_secret/client_secret.json` (`0600` permissions, `.gitignore`d), launches your YouTube channel login, and opens your live `report.html` dashboard!

---

## Support & Channel

If this saved you from paying for a monthly "Creator OS" subscription:
- **Subscribe on YouTube:** [MateAI (@mateai-c6m)](https://www.youtube.com/@mateai-c6m) — real AI build-logs, measured costs, no hype.
- **Buy Mate a Coffee:** [buymeacoffee.com/epuplanner](https://buymeacoffee.com/epuplanner)

## License & Anti-Resale Protection

Licensed under **Apache License 2.0 with Commons Clause Restriction v1.0** ([LICENSE](LICENSE)).

- **Free for creators & developers:** You may freely use, modify, and share this tool for your own YouTube channels (including monetized channels).
- **No commercial resale / paid SaaS wrapping:** You may **not** sell this software, bundle it into a paid product, or host it as a paid/managed MCP service without a commercial license from MateAI.
