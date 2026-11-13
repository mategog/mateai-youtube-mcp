<div align="center">

<img src="assets/mateai-logo.png" width="88" alt="MateAI logo"/>

# MateAI YouTube MCP

**Upload, schedule and analyze your YouTube channel just by asking Claude or Antigravity.**<br/>
Free. Runs on your computer. One sign-in, verified by Google.

[![Google OAuth: verified](https://img.shields.io/badge/Google%20OAuth-verified-2ea44f)](docs/SETUP.md#claude-code)
[![Release](https://img.shields.io/github/v/release/mategog/mateai-youtube-mcp?color=238636)](https://github.com/mategog/mateai-youtube-mcp/releases/latest)
[![mategog/mateai-youtube-mcp MCP server](https://glama.ai/mcp/servers/mategog/mateai-youtube-mcp/badges/score.svg)](https://glama.ai/mcp/servers/mategog/mateai-youtube-mcp)
[![License](https://img.shields.io/badge/license-Apache%202.0%20%2B%20Commons%20Clause-blue.svg)](LICENSE)

[**Get started**](#get-started-in-2-minutes) · [What you can ask](#what-you-can-ask) · [Setup guide](docs/SETUP.md) · [All tools](docs/REFERENCE.md)

<img src="assets/demo.gif" width="720" alt="Dry run, then schedule: an animated replay of real plugin output"/>

<sub>Replay of real plugin output: a dry run, a wrong date caught by a warning, then a real scheduled upload.</sub>

</div>

## Get started in 2 minutes

**1. Install** (in your terminal, with [Claude Code](https://claude.com/claude-code)):

```bash
claude plugin marketplace add mategog/mateai-youtube-mcp
claude plugin install yt-studio@mateai-youtube-mcp
```

**2. Connect your channel.** Type **`/yt-setup`** in Claude Code, pick your YouTube account in the browser and click **Allow**.

**3. Ask.** *"Take a snapshot of my channel and show me the report."*

That's it. No Google Cloud project, no API keys: the sign-in is verified by Google.

<details>
<summary><b>Using Antigravity, Claude Desktop, Windows or Linux?</b></summary>
<br/>

**Antigravity**

```bash
git clone https://github.com/mategog/mateai-youtube-mcp.git ~/.gemini/config/plugins/mateai-youtube
cd ~/.gemini/config/plugins/mateai-youtube && python3 yt_studio.py setup
```

**Claude Desktop or any MCP client:** clone the repo, run `python3 yt_studio.py setup`, then add this to your client's config:

```json
{ "mcpServers": { "mateai-youtube": { "command": "python3", "args": ["/ABSOLUTE/PATH/TO/mateai-youtube-mcp/mcp_server.py"] } } }
```

**Windows and Linux** work too: see the [setup guide](docs/SETUP.md#windows-1011).

</details>

## What you can ask

| | |
|---|---|
| 📤 **Upload and schedule** | *"Upload `short.mp4` with this cover, write the title and hashtags, and schedule it for Friday 18:00."* |
| 📉 **Find where viewers leave** | *"Which of my last 5 Shorts had the highest swipe-away rate, and where did viewers drop off?"* |
| ✏️ **Edit videos** | *"Change the title of my latest video and make it public."* |
| 💬 **Handle comments** | *"Show me new comments on my last video and draft replies."* |
| 📊 **See your channel at a glance** | *"Take a snapshot of my channel and show me the report."* Or type `/yt-dashboard` for a live card above the prompt. |

<img src="assets/dashboard-preview.png" width="720" alt="The channel report: views, Shorts vs long-form, and viewed-vs-swiped for every upload"/>

## Why creators use it

- **🛡️ Nothing goes live by surprise.** Every upload, edit and comment can run as a dry run first. Deleting always asks you, and the confirmation box comes from the plugin, so the AI can't click "yes" for you. Use `/yt-safety` to choose what else asks first.
- **🔒 Your data stays with you.** It runs on your machine and talks only to Google. The author gets nothing. [Privacy details](PRIVACY.md)
- **💸 $0.** It uses YouTube's free official APIs and the AI subscription you already have.
- **🎬 Made for Shorts.** Viewed vs. swiped away, average % viewed and full retention curves for every video.

> [!TIP]
> **Prefer a desktop app?** [MateAI Studio](https://mateaistudio.com/) is built on this plugin, with the same one-click sign-in. Free during early access.

## Learn more

- 📘 [**Setup guide**](docs/SETUP.md): every client and OS, your own Google client, sign out, troubleshooting
- 🧰 [**Reference**](docs/REFERENCE.md): all tools, safety limits, API quota, privacy, bundled skills and credits
- 🎵 [**TikTok** (experimental)](docs/TIKTOK.md): compare Shorts with TikTok and send drafts to your TikTok inbox

<a name="use-your-own-google-cloud-client-optional-own-quota"></a>
Want your own API quota? [Use your own Google Cloud client](docs/SETUP.md#use-your-own-google-cloud-client-optional-own-quota).

## Support

If this saves you a monthly creator-tool fee, **⭐ star the repo** so other creators can find it.

[![YouTube Channel](https://img.shields.io/badge/YouTube-@mateai--c6m-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/@mateai-c6m)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-mategog-EA4AAA?logo=github-sponsors&logoColor=white)](https://github.com/sponsors/mategog)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-MateAI-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/mateai)

## License

Free to use and modify for your own channels, including monetized ones. You may not resell it or run it as a paid service without a commercial license. Licensed under **Apache 2.0 with Commons Clause** ([LICENSE](LICENSE)): source-available, not OSI open source.
