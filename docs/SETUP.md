# Setup guide

[← Back to README](../README.md)

**Contents:** [Claude Code](#claude-code) · [Antigravity](#google-antigravity) · [Claude Desktop and other clients](#claude-desktop-and-other-mcp-clients) · [Windows](#windows-1011) · [Linux](#linux-untested) · [Manual wizard](#manual-setup-wizard-any-client) · [Your own Google client](#use-your-own-google-cloud-client-optional-own-quota) · [Public mode](#public-mode-no-login-opt-in) · [Sign out / switch channel](#sign-out-or-switch-channel) · [Troubleshooting](#troubleshooting)

## Claude Code

```bash
claude plugin marketplace add mategog/mateai-youtube-mcp
claude plugin install yt-studio@mateai-youtube-mcp
```

Then type **`/yt-setup`** in Claude Code (needs Claude Code 2.1.287 or newer). You do this once.

1. **Type `/yt-setup`.** It answers "Opening your browser…" (or "Already connected." if you are done). The first time, it installs Google's Python libraries into the data folder first, which takes about a minute.
2. **Sign in (your browser opens).** Pick your YouTube account, tick **every box**, click **Allow**. Claude Code then shows **"yt-setup: connected!"** and the "YouTube: not connected" status hint disappears.

The plugin ships with the MateAI Studio sign-in client (`oauth_client.json`), which **Google reviewed and verified** in November 2026 for the YouTube permissions it asks for. So you don't create a Google Cloud project, Google's consent screen shows MateAI Studio without a "Google hasn't verified this app" warning, and your sign-in doesn't expire after 7 days. `/yt-setup` never sees your Google password.

The plugin keeps its state (`.venv`, tokens, `channel_snapshot.json`, `report.html`, and your own OAuth client if you use one) in `~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/`, which survives plugin updates.

## Google Antigravity

Clone into your Antigravity plugins folder, restart Antigravity, then run the [setup wizard](#manual-setup-wizard-any-client) from that folder:

```bash
git clone https://github.com/mategog/mateai-youtube-mcp.git \
  ~/.gemini/config/plugins/mateai-youtube
cd ~/.gemini/config/plugins/mateai-youtube && python3 yt_studio.py setup
```

## Claude Desktop and other MCP clients

Clone the repo, run `python3 yt_studio.py setup` once, then add the server to your client's config (`claude_desktop_config.json` for Claude Desktop):

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

Any MCP client that runs local (stdio) servers can use this config. Only Claude Code, Claude Desktop and Antigravity are tested.

## Windows (10/11)

The plugin runs on Windows with the same commands; only Python needs one check first.

**1. Make sure `python3` works.** Claude Code and Antigravity start the server as `python3`. Install Python 3.10 or newer from [python.org/downloads](https://www.python.org/downloads/) (the **Python install manager**) or from the Microsoft Store; both add a `python3` command. Then check it in PowerShell:

```powershell
python3 --version
```

It should print `Python 3.x`. If it opens the Microsoft Store or prints "Python was not found", you have the older python.org installer (it only adds `python` and `py`) or no Python yet: install Python with the install manager above, then open **Settings > Apps > Advanced app settings > App execution aliases** and make sure the **Python** aliases are on. Open a new PowerShell window and check again.

**2a. Claude Code.** Install from the marketplace, then run `/yt-setup` inside Claude Code, exactly as on macOS:

```powershell
claude plugin marketplace add mategog/mateai-youtube-mcp
claude plugin install yt-studio@mateai-youtube-mcp
```

`/yt-setup` opens Google's sign-in in your default browser. The plugin's data folder is `%USERPROFILE%\.claude\plugins\data\yt-studio-mateai-youtube-mcp`.

On a Claude Code older than 2.1.287 (no `/yt-setup`), run the wizard by hand:

```powershell
$env:MATEAI_YT_HOME = "$env:USERPROFILE\.claude\plugins\data\yt-studio-mateai-youtube-mcp"
$plugin = Get-ChildItem "$env:USERPROFILE\.claude\plugins\cache\mateai-youtube-mcp\yt-studio" -Directory |
  Sort-Object { [version]$_.Name } | Select-Object -Last 1
python3 "$($plugin.FullName)\yt_studio.py" setup
```

The same `$env:MATEAI_YT_HOME` line works before `python3 ...\tiktok_studio.py setup`. Restart Claude Code afterwards.

**2b. Antigravity.** Clone into your Antigravity plugins folder and restart Antigravity:

```powershell
git clone https://github.com/mategog/mateai-youtube-mcp.git "$env:USERPROFILE\.gemini\config\plugins\mateai-youtube"
```

For the private Studio analytics, run the wizard from that folder: `cd "$env:USERPROFILE\.gemini\config\plugins\mateai-youtube"; python3 yt_studio.py setup`.

**Standalone MCP config.** Use forward slashes or doubled backslashes in JSON, for example `"args": ["C:/Users/you/mateai-youtube-mcp/mcp_server.py"]`.

**What differs from macOS**
- **Login file privacy.** macOS and Linux get `0600` file permissions. Windows has no such modes (`os.chmod` only toggles read-only), so the plugin doesn't pretend: your token and client file are protected by living in your own user profile folder, which Windows by default lets only you, SYSTEM and administrators read. Anyone with an administrator account on the PC can read them, as with any file in your profile.
- **MateAI Studio login sharing** (reusing the desktop app's YouTube login) is macOS-only for now; on Windows the plugin uses its own login from `/yt-setup`.

## Linux (untested)

`/yt-setup` with the built-in client should work as on macOS, but it is untested. With [your own Google client](#use-your-own-google-cloud-client-optional-own-quota), `/yt-setup` can only open the Google Cloud pages on macOS and Windows; on Linux, use the [manual wizard](#manual-setup-wizard-any-client) (`python3 yt_studio.py setup`).

## Manual setup wizard (any client)

Not using Claude Code 2.1.287+? Run the wizard:

```bash
python3 yt_studio.py setup
```

The wizard:
1. **Creates `.venv` and installs Google's OAuth libraries** if they aren't installed yet.
2. **Starts the YouTube sign-in in your browser** with the built-in client, then opens your `report.html` dashboard.

For the Claude Code plugin on an older Claude Code, point the wizard at the plugin's data folder:

```bash
MATEAI_YT_HOME=~/.claude/plugins/data/yt-studio-mateai-youtube-mcp \
  python3 ~/.claude/plugins/cache/mateai-youtube-mcp/yt-studio/<version>/yt_studio.py setup
```

Replace `<version>` with your installed version (`ls ~/.claude/plugins/cache/mateai-youtube-mcp/yt-studio/`), or run the same command from any clone of this repo. Restart Claude Code afterwards.

## Use your own Google Cloud client (optional, own quota)

You can sign in through your own Google Cloud project instead, for example to have your own API quota. A `client_secret.json` in the plugin's data folder takes priority over the built-in client.

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable **YouTube Data API v3** and **YouTube Analytics API**.
2. Page "Audience": click **Add users** under **Test users**, enter your YouTube email, **Save**.
3. Page "Create OAuth client": **Application type = Desktop app** (not "Web application"), any name, **Create**, then **Download JSON**.
4. Save the file as `google_auth_secret/client_secret.json` in the plugin's data folder (`~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/`), then run `/yt-setup` (run `/yt-disconnect` first if you were already connected).

On Google's sign-in, "Google hasn't verified this app" then appears: click **Advanced**, then **Go to … (unsafe)**; this is your own app. With your own app in "Testing" mode Google expires the sign-in every 7 days.

If the plugin has no built-in client (a clone without `oauth_client.json`), `/yt-setup` and the wizard guide you through these steps: they open the Google pages and pick the downloaded file up from `~/Downloads`.

## Public mode (no login, opt-in)

Public stats for any channel work without API keys, but public page scraping is off by default. Opt in with `--public`, `force_public=true` or `MATEAI_YT_PUBLIC_SCRAPE=1`:

```bash
git clone https://github.com/mategog/mateai-youtube-mcp.git
cd mateai-youtube-mcp
python3 yt_studio.py snapshot --public --handle @mateai-c6m
open report.html

# Markdown table for Shorts A/B style experiments
MATEAI_YT_PUBLIC_SCRAPE=1 python3 yt_studio.py experiment-table --handle @mateai-c6m
```

For your own channel, the official APIs above are the recommended default.

## Sign out or switch channel

Your login lives in `~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/` (`.tokens/token.json`, plus `client_secret.json` if you use your own client, both mode `600`; on Windows `%USERPROFILE%\.claude\plugins\data\yt-studio-mateai-youtube-mcp\`, protected by your user profile folder).

To sign out, or to switch to another channel, type **`/yt-disconnect`**: it revokes the plugin's access at Google and deletes `.tokens/token.json` (your own `client_secret.json` and the TikTok login stay); then run `/yt-setup`: Google always shows its account chooser, so you can pick any account. If Google can't be reached, it still deletes the login and tells you so.

If you also use MateAI Studio, `/yt-disconnect` only deletes the plugin's own login and does not revoke: both use the same Google sign-in client, and Google revokes per app, so a revoke would sign Studio out too. The plugin then falls back to Studio's login until you run `/yt-setup` and pick another account. To cut access fully, disconnect YouTube in MateAI Studio, which revokes it. Manual fallback: delete `.tokens/token.json` and revoke access at <https://myaccount.google.com/permissions>.

**With the MateAI Studio app (macOS):** if you've connected YouTube in MateAI Studio and the plugin has no login of its own, the plugin uses Studio's login (read from the app's Keychain item `dev.mateai.desktop`, never changed), so one Connect covers both. The first time, macOS asks whether `security` may use that item: choose **Always Allow**. To use a different account in the plugin, run `/yt-setup` and pick it: the plugin's own login always wins over Studio's. Up to version 1.0.22 Studio's login won, so after updating, an older plugin login saved next to Studio's takes over: run `/yt-disconnect` to go back to Studio's. To never use Studio's login, set `MATEAI_DESKTOP_LOGIN=off`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| It says the file is a **"web" client** | Create a new client and choose **Desktop app**. |
| Browser shows **"Access blocked" / 403 access_denied** | Only with your own Google client: your email is not under **Test users**. Add it, then rerun `/yt-setup`. |
| **"Login did not finish"** | The tab was closed early or a box was not ticked. Rerun `/yt-setup`. |
| **"yt-studio plugin is not installed"** | Run `claude plugin install yt-studio@mateai-youtube-mcp`. |
| **"Could not install the Google libraries"** | Install Python 3 (python.org) and check your internet connection. |
| **Nothing happens** | Hooks may be off (`disableAllHooks`). `/yt-setup` is a hook-based mod. |
| Asked to log in again after about a week, or "Your YouTube login expired" | Only with your own Google client: Google expires sign-ins after 7 days for an app in "Testing" status with an external user type ([Google's OAuth docs](https://developers.google.com/identity/protocols/oauth2#expiration)). Rerun `/yt-setup`. Moving the app from "Testing" to "In production" may stop the 7-day expiry (Google's page doesn't say for sure), but sign-in then shows Google's "Google hasn't verified this app" warning. |
| Start over, or switch channel | Run `/yt-disconnect`, then `/yt-setup`. (By hand: delete `~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/.tokens/token.json` and rerun `/yt-setup`.) |

TikTok problems: see [TIKTOK.md](TIKTOK.md#troubleshooting).
