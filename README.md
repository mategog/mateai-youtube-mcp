# <img src="assets/logo.png" width="44" align="absmiddle" alt="MateAI YouTube Studio Icon"/> mateai-youtube-mcp

[![Release](https://img.shields.io/github/v/release/mategog/mateai-youtube-mcp?color=238636)](https://github.com/mategog/mateai-youtube-mcp/releases/latest)
[![mategog/mateai-youtube-mcp MCP server](https://glama.ai/mcp/servers/mategog/mateai-youtube-mcp/badges/score.svg)](https://glama.ai/mcp/servers/mategog/mateai-youtube-mcp)
[![YouTube Channel](https://img.shields.io/badge/YouTube-@mateai--c6m-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/@mateai-c6m)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor%20on%20GitHub-mategog-EA4AAA?logo=github-sponsors&logoColor=white)](https://github.com/sponsors/mategog)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support%20MateAI-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/epuplanner)
[![License: Apache 2.0 + Commons Clause](https://img.shields.io/badge/License-Apache%202.0%20%2B%20Commons%20Clause-blue.svg)](LICENSE)

![MateAI YouTube Studio & Shorts Experiment Dashboard](assets/dashboard-preview.png)

**Tell your AI to upload, title, schedule and analyze your YouTube videos. Use the Claude or Antigravity subscription you already pay for, with no extra tool and no monthly fee.**

> "Upload `exports/short.mp4` with this cover, write the title, description and hashtags, and schedule it for tomorrow 20:00 CET."
>
> "Which of my Shorts lost viewers in the first two seconds?"

That is what this plugin does. It connects **Claude Code / Claude Desktop** or **Google Antigravity** to your own YouTube channel through Google's official, free YouTube APIs, so the assistant you already use can do the work you'd otherwise do by hand in YouTube Studio:

- **Upload and schedule:** video, custom cover, title, description, hashtags, tags, language, synthetic-media disclosure and a future publish time.
- **Edit and engage:** update metadata on existing videos and post comments.
- **Analyze:** retention, Viewed vs. swiped away, engaged views, watch time and subscribers gained, per video, with a local `report.html` dashboard.
- **Compare with TikTok (optional):** connect your TikTok account through TikTok's official API to pull its stats, send a Short to your TikTok app inbox with a ready-to-paste caption, and see your YouTube Shorts and TikToks side by side. See [TikTok](#tiktok-optional).

Hosted "creator OS" tools charge $19-$49 a month to wrap those same free Google APIs. Here nothing sits between your AI and YouTube: it runs **100% on your machine**, your login stays in a local file only you can read, and the plugin costs **$0**. Connecting takes one command, **`/yt-setup`** (see [Easy Setup](#easy-setup-yt-setup-claude-code)).

Public stats (no login) are available as an opt-in mode: `--public`, `force_public=true` or `MATEAI_YT_PUBLIC_SCRAPE=1`. Built for the [MateAI](https://www.youtube.com/@mateai-c6m) channel.

---

## Quick Start (Public Snapshot, opt-in)

No API keys or packages needed, but public page scraping is opt-in, so pass `--public`. For your own channel, the OAuth2 setup below (official YouTube APIs) is the recommended default:

```bash
git clone https://github.com/mategog/mateai-youtube-mcp.git
cd mateai-youtube-mcp

python3 yt_studio.py snapshot --public --handle @mateai-c6m
open report.html
```

Print a Markdown table for tracking Shorts A/B style experiments:

```bash
MATEAI_YT_PUBLIC_SCRAPE=1 python3 yt_studio.py experiment-table --handle @mateai-c6m
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

The plugin keeps its state (`.venv`, OAuth secret, tokens, `channel_snapshot.json`, `report.html`) in `~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/`, which survives plugin updates. Public snapshots work once you opt in (see above). To unlock private Studio analytics and uploads, run **`/yt-setup`** (needs Claude Code 2.1.287 or newer; see [Easy Setup](#easy-setup-yt-setup-claude-code) below).

On an older Claude Code, run the setup wizard by hand with `MATEAI_YT_HOME` pointing at that folder:

```bash
MATEAI_YT_HOME=~/.claude/plugins/data/yt-studio-mateai-youtube-mcp \
  python3 ~/.claude/plugins/cache/mateai-youtube-mcp/yt-studio/<version>/yt_studio.py setup
```

Replace `<version>` with your installed version (`ls ~/.claude/plugins/cache/mateai-youtube-mcp/yt-studio/`), or run the same command from any clone of this repo. Restart Claude Code afterwards.

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

**YouTube**

| Tool | Description |
|---|---|
| `yt_channel_snapshot` | Fetch channel overview, Long-form uploads, Shorts stats, and update `report.html`. |
| `yt_shorts_experiment_table` | Generate a Markdown table comparing Shorts retention, swipe-away rate, and views. |
| `yt_video_details` | Inspect metadata and metrics for any 11-character YouTube `video_id`. |
| `yt_upload_draft` | Upload a local MP4/MOV + cover image + full Studio setup (`title`, `description`, `hashtags`, `tags`, `language`, `contains_synthetic_media`, `pinned_comment`, and **`publish_at` schedule**). |
| `yt_update_video` | Update title, description, tags, privacy status, schedule time, or thumbnail of an existing video. |
| `yt_post_comment` | Post a top-level comment (e.g. your `## Pinned comment` question) on a video. |
| `yt_list_videos` | List/search your uploads (private and unlisted included) to find video IDs. |
| `yt_list_comments` | Read top-level comment threads (with replies) on a video. |
| `yt_reply_comment` | Reply publicly to a top-level comment. |
| `yt_delete_video` | Permanently delete a video; refuses unless you pass its exact title. |

**TikTok (optional, needs the [TikTok setup](#tiktok-optional))**

| Tool | Description |
|---|---|
| `tiktok_channel_snapshot` | Fetch your TikTok profile stats and recent videos (views, likes, comments, shares) through TikTok's official API. |
| `tiktok_upload_draft` | Send a local MP4/MOV to your TikTok app inbox and return the caption to paste, plus a reminder to switch on TikTok's AI-generated label. It does not publish for you. |
| `cross_platform_shorts_table` | Markdown table that pairs each YouTube Short with the same video on TikTok (views, likes, comments, YouTube avg % viewed, TikTok shares). Videos that exist on only one platform get their own row. |

---

## Bundled YouTube Strategy & Creator Skills (Full Pipeline)

This plugin integrates the **YouTube Strategy & Creator Skill Suite** directly alongside the `mateai-youtube` MCP server, so your AI agent handles everything from niche research and hook writing to live Studio scheduling:

- **Production Pipeline Skills** (`yt-research`, `yt-ideation`, `yt-brief`, `yt-packaging`, `yt-outline`, plus `/yt-pipeline` command and `yt-scraper`, `channel-analyzer`, `idea-validator` agents) — created by **[Jeremy Longshore (`@jeremylongshore` / Intent Solutions)](https://github.com/jeremylongshore/tons-of-skills-marketplace/tree/main/plugins/productivity/youtube-strategy)** (`@intentsolutionsio/youtube-strategy`, MIT).
- **14 Creator Sub-Skills & Playbooks** (`audit`, `seo`, `script`, `hook`, `thumbnail`, `strategy`, `calendar`, `shorts`, `analyze`, `repurpose`, `monetize`, `competitor`, `metadata`, `ideate`) — created by **[Daniel Agrici (`@AgriciDaniel`)](https://github.com/AgriciDaniel/claude-youtube)** (`claude-youtube`, MIT).
- **Live YouTube Studio Execution & Analytics MCP** (`yt_channel_snapshot`, `yt_shorts_experiment_table`, `yt_upload_draft`, `yt_update_video`, `yt_post_comment`, optional TikTok tools, interactive `report.html` dashboard & 1-command `setup` wizard) — built by **[MateAI (`@mateai-c6m`)](https://www.youtube.com/@mateai-c6m)**.

---

## Dashboard: `/yt-dashboard` (Claude Code 2.1.287+)

Type **`/yt-dashboard`** to show or hide a channel card above the prompt: total views, subscribers, video count, and your latest five videos with a viewed-vs-swiped bar and its percentage. Desktop, VS Code and mobile draw it as a card; the terminal shows a text version. It reads the last `channel_snapshot.json`, and redraws whenever Claude runs `yt_channel_snapshot`, so the standalone `report.html` is optional.

## Easy Setup: `/yt-setup` (Claude Code)

Type **`/yt-setup`** in Claude Code and it connects the plugin to your YouTube account. You do this once. Everything stays on your computer; only Google sees your sign-in.

**You need:** Claude Code 2.1.287 or newer, this plugin installed, and the Google account that owns your channel.

**1. Type `/yt-setup` and read the answer.**

| It says | Meaning | You |
| --- | --- | --- |
| "Already connected." | Done. | Nothing |
| "Found your Google client file. Opening your browser…" | It has the file it needs. | Go to step 3 |
| "One manual step first… I opened two Google pages." | No client file yet. Google makes everyone create one. | Go to step 2 |

**2. Make the Google client file (only if asked, about 3 minutes).** No program can do this for you.
- Page "Audience": click **Add users** under **Test users**, enter your YouTube email, **Save**.
- Page "Create OAuth client": **Application type = Desktop app** (not "Web application"), any name, **Create**, then **Download JSON**.
- Leave the file in `~/Downloads` and run `/yt-setup` again.

**3. Sign in (your browser opens).** Pick your YouTube account. On "Google hasn't verified this app" click **Advanced**, then **Go to … (unsafe)**; this is your own app. Tick **every box**, click **Allow**. Claude Code then shows **"yt-setup: connected!"** and the "YouTube: not connected" status hint disappears.

`/yt-setup` copies your client file into the plugin's data folder with `600` permissions, never prints it, and never sees your Google password.

| Problem | Fix |
| --- | --- |
| It says the file is a **"web" client** | Create a new client and choose **Desktop app**. |
| Browser shows **"Access blocked" / 403 access_denied** | Your email is not under **Test users**. Add it, then rerun `/yt-setup`. |
| **"Login did not finish"** | The tab was closed early or a box was not ticked. Rerun `/yt-setup`. |
| **"yt-studio plugin is not installed"** | Run `claude plugin install yt-studio@mateai-youtube-mcp`. |
| **"Could not install the Google libraries"** | Install Python 3 (python.org) and check your internet connection. |
| **Nothing happens** | Hooks may be off (`disableAllHooks`). `/yt-setup` is a hook-based mod. |
| Asked to log in again after about a week | Apps in "Testing" mode can have sign-ins that expire after about 7 days. Publishing the app on the Audience page may avoid that. **[unconfirmed]** |
| Start over | Delete `~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/.tokens`, then rerun `/yt-setup`. |

Not using Claude Code, or on an older version? Use the wizard below.

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

## TikTok (optional)

Cross-post your Shorts and see how they do on both platforms. This uses TikTok's official, free developer API only: no cookies, no scraping. It never publishes for you; a video lands in your TikTok app inbox and you tap Post yourself. Everything stays on your machine, and the YouTube tools work the same whether or not you set this up.

**What you can ask your AI**

> "Send `exports/short.mp4` to my TikTok inbox with the caption from `planning/my-short-upload.md`."
>
> "Show my YouTube Shorts next to the same videos on TikTok."

**Connect TikTok (once)**

1. Create an app at [developers.tiktok.com](https://developers.tiktok.com/) and choose the **Desktop** platform.
2. Add the redirect URI `http://127.0.0.1:8765/callback/` (exactly, with the trailing slash).
3. Enable these scopes: `user.info.basic`, `user.info.profile`, `user.info.stats`, `video.list`, `video.upload`.
4. Run the wizard. It asks for your app's Client Key and Client Secret, opens TikTok's sign-in in your browser, and saves the token locally:

```bash
python3 tiktok_studio.py setup
```

If you installed the plugin, point it at the plugin's data folder first, the same way as for the YouTube wizard: `MATEAI_YT_HOME=~/.claude/plugins/data/yt-studio-mateai-youtube-mcp python3 tiktok_studio.py setup`.

**Command line**

```bash
python3 tiktok_studio.py snapshot                                   # profile and recent videos
python3 tiktok_studio.py upload-draft --video exports/short.mp4 \
  --spec planning/my-short-upload.md                                # send to your TikTok inbox
python3 tiktok_studio.py cross-table                                # YouTube Shorts vs TikTok
```

**Good to know**

- **Captions are pasted by hand.** TikTok's inbox upload cannot take a caption. `tiktok_upload_draft` builds one from your upload spec (title plus the `#hashtags` in the description, `#Shorts` removed) and returns it for you to paste in the app.
- **Switch on the AI-generated label yourself.** If your video uses a synthetic voice or AI visuals, turn on TikTok's AI-generated content toggle in the app before posting. The API cannot set it.
- **Matching is by title.** The comparison table pairs a Short with a TikTok when the title (hashtags ignored) matches the TikTok title or description. Anything else shows up as its own row, with "—" for the missing platform.
- **Only official numbers.** TikTok's API gives views, likes, comments and shares. Retention-style metrics exist for YouTube only.
- **Your data.** The client file is `tiktok_auth_secret/tiktok_client.json` and the login token is `.tokens/tiktok_token.json`, both owner-only (`0600`) and `.gitignore`d. The cache is `tiktok_snapshot.json`. Details in [PRIVACY.md](PRIVACY.md).

| Problem | Fix |
| --- | --- |
| "No TikTok OAuth token found" | Run `python3 tiktok_studio.py setup`. |
| "TikTok refresh token expired" | Run `python3 tiktok_studio.py setup` again to sign in. |
| Setup waits, then times out | The browser tab was closed. Rerun setup; it waits 5 minutes for the sign-in. |
| Sign-in page rejects the redirect | The redirect URI in your TikTok app must be exactly `http://127.0.0.1:8765/callback/`. |
| Channel handle is empty | The `user.info.profile` scope is missing. Enable it in your TikTok app and run setup again. |
---

## What this plugin runs, sends and fetches

Everything runs on your own computer. The author receives no data. Nothing is sent anywhere except to Google/YouTube (and to TikTok, only if you set up the optional TikTok connection), and to your Claude conversation, which is under Anthropic's own privacy terms (see [PRIVACY.md](PRIVACY.md)).

**The MCP server** (`mcp_server.py`, started by Claude Code as `python3 ${CLAUDE_PLUGIN_ROOT}/mcp_server.py`):
- Calls Google's **YouTube Data API v3** and **YouTube Analytics API v2** with the scopes you approve at sign-in: read-only analytics, and optionally upload, edit metadata and post comments.
- **Public mode (off by default):** fetches public `youtube.com` channel and video pages only when you opt in with `--public`, `force_public=true` or `MATEAI_YT_PUBLIC_SCRAPE=1`.
- `yt_upload_draft` reads the video and cover files whose paths you give it and uploads them to your channel. `yt_update_video` and `yt_post_comment` change your video or post a comment, only when called.
- Writes `channel_snapshot.json` and `report.html` (cached statistics for your own channel) to the plugin data folder.

**The `/yt-setup` command** (a Claude Code mod in `hooks/`):
- Looks for a `client_secret*.json` in the plugin data folder, your current project and `~/Downloads` (up to 5 folders deep), and copies a Desktop-app client into the data folder with `600` permissions. It never prints the file.
- Creates a Python virtual environment in the data folder and runs `pip install -r requirements.txt` (from PyPI: `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`).
- Opens two Google Cloud pages (macOS `open`) and starts Google's sign-in in your browser. Your Google password is typed on Google's own page and never reaches this plugin.
- Reads your saved token only to check which permissions it holds.
- Works with macOS paths; on Windows use the manual wizard below.

**Where your login lives:** `~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/` (`client_secret.json` and `.tokens/token.json`, both mode `600`). Delete that folder to remove it, and revoke access at <https://myaccount.google.com/permissions>.

---

## Support & Channel

If this saved you from paying for a monthly "Creator OS" subscription:
- **Sponsor on GitHub:** [github.com/sponsors/mategog](https://github.com/sponsors/mategog)
- **Subscribe on YouTube:** [MateAI (@mateai-c6m)](https://www.youtube.com/@mateai-c6m) — real AI build-logs, measured costs, no hype.
- **Buy Mate a Coffee:** [buymeacoffee.com/epuplanner](https://buymeacoffee.com/epuplanner)

## License & Anti-Resale Protection

Licensed under **Apache License 2.0 with Commons Clause Restriction v1.0** ([LICENSE](LICENSE)). This is a *source-available* license, not an OSI open-source one; GitHub may label the repository "Apache-2.0" because of the base text.

- **Free for creators & developers:** You may freely use, modify, and share this tool for your own YouTube channels (including monetized channels).
- **No commercial resale / paid SaaS wrapping:** You may **not** sell this software, bundle it into a paid product, or host it as a paid/managed MCP service without a commercial license from MateAI.
