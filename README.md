# mateai-youtube-mcp

[![YouTube Channel](https://img.shields.io/badge/YouTube-@mateai--c6m-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/@mateai-c6m)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support%20MateAI-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/epuplanner)
[![License: Apache 2.0 + Commons Clause](https://img.shields.io/badge/License-Apache%202.0%20%2B%20Commons%20Clause-blue.svg)](LICENSE)

A local, self-hosted **YouTube Studio & Analytics MCP Connector + CLI** for **Google Antigravity** and **Claude Code / Claude Desktop**, built for the [MateAI](https://www.youtube.com/@mateai-c6m) channel.

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

## Connect to Antigravity or Claude Code (MCP Server)

Add `mateai-youtube-mcp` to your MCP configuration (`mcp_config.json` in Antigravity or `claude_desktop_config.json` / `.mcp.json` in Claude Code):

```json
{
  "mcpServers": {
    "youtube-studio": {
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
| `yt_upload_draft` | Upload a local MP4/MOV + cover image + Markdown spec (`Title`, `Description`, `Tags`) as a Private draft in YouTube Studio. |

---

## Unlock Private YouTube Studio Analytics & Draft Uploads ($0/mo)

Google gives every developer **10,000 free quota units/day** on the YouTube Data API v3 and YouTube Analytics API v2. Because you run this locally for your own channel in "Testing" mode, **no Google app verification is required**.

1. Install the official Google OAuth libraries in a local virtualenv:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Go to the [Google Cloud Console](https://console.cloud.google.com/):
   - Enable **YouTube Data API v3** and **YouTube Analytics API**.
   - Under **Google Auth Platform / Credentials**, create an **OAuth 2.0 Client ID** of type **Desktop App**.
   - Add your own Google/YouTube email under **Audience → Test users**.
   - Download the JSON file and save it as `client_secret.json` in this directory (it is `.gitignore`d so it can never be committed).
3. Run the one-time browser login:
   ```bash
   .venv/bin/python yt_studio.py auth
   ```
4. From now on, `yt_studio.py snapshot` and the MCP server automatically include private Studio metrics (`Avg % viewed`, `Viewed vs swiped`, `Engaged views`, `Subs gained`) and unlock `upload-draft`!

---

## Support & Channel

If this saved you from paying for a monthly "Creator OS" subscription:
- **Subscribe on YouTube:** [MateAI (@mateai-c6m)](https://www.youtube.com/@mateai-c6m) — real AI build-logs, measured costs, no hype.
- **Buy Mate a Coffee:** [buymeacoffee.com/epuplanner](https://buymeacoffee.com/epuplanner)

## License & Anti-Resale Protection

Licensed under **Apache License 2.0 with Commons Clause Restriction v1.0** ([LICENSE](LICENSE)).

- **Free for creators & developers:** You may freely use, modify, and share this tool for your own YouTube channels (including monetized channels).
- **No commercial resale / paid SaaS wrapping:** You may **not** sell this software, bundle it into a paid product, or host it as a paid/managed MCP service without a commercial license from MateAI.
