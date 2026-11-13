# Reference

[← Back to README](../README.md)

**Contents:** [Tools](#tools) · [Dashboard](#dashboard-yt-dashboard) · [Safety](#safety-dry-runs-confirmations-and-limits) · [Quota](#youtube-api-quota) · [Privacy](#privacy-what-it-runs-sends-and-fetches) · [What it doesn't do](#what-it-doesnt-do) · [Bundled skills and credits](#bundled-skills-and-credits)

## Tools

| Tool | What it does |
|---|---|
| `yt_channel_snapshot` | Fetch channel overview, long-form uploads and Shorts stats, and update `report.html`. |
| `yt_shorts_experiment_table` | Markdown table comparing Shorts retention, swipe-away rate and views. |
| `yt_video_details` | Metadata, 100-point retention curve, drop-off points and traffic sources for an 11-character `video_id`. |
| `yt_upload_draft` | Upload a local MP4/MOV + cover image with full Studio setup (`title`, `description`, `hashtags`, `tags`, `language`, `contains_synthetic_media`, `pinned_comment` and a **`publish_at` schedule**). |
| `yt_update_video` | Update title, description, tags, privacy status, schedule time, thumbnail or the `contains_synthetic_media` disclosure of an existing video; parts you don't change are not re-sent. |
| `yt_post_comment` | Post a top-level comment on a video. |
| `yt_list_videos` | List/search your uploads (private and unlisted included) to find video IDs. |
| `yt_list_comments` | Read top-level comment threads (with replies) on a video. |
| `yt_reply_comment` | Reply publicly to a top-level comment. |
| `yt_delete_video` | Permanently delete a video; refuses unless you pass its exact title. |
| `yt_get_safety_settings` / `yt_set_safety_settings` | Show / choose which actions ask you first. Used by `/yt-safety`. |

TikTok tools are listed in [TIKTOK.md](TIKTOK.md#tools).

## Dashboard: `/yt-dashboard`

Needs Claude Code 2.1.287+. Shows or hides a channel card above the prompt: total views, subscribers, video count, and your latest five videos with a viewed-vs-swiped bar. Desktop, VS Code and mobile draw it as a card; the terminal shows a text version. It redraws whenever `yt_channel_snapshot` runs, so the standalone `report.html` is optional.

## Safety: dry runs, confirmations and limits

**Preview before anything goes live.** `yt_upload_draft`, `yt_update_video` and `yt_post_comment` accept `dry_run: true`. They then upload, change and post nothing, need no sign-in, and return exactly what would be sent, with the schedule in your local time and a warning if `publish_at` is in the past or has no timezone. Ask your AI: "Do a dry run of this upload first."

**Choose what asks first: `/yt-safety`.** Claude always asks before **deleting a video**. Type `/yt-safety` to also be asked before uploading videos, changing a video's details, or posting and replying to comments. No files to edit, and you can run it again any time.

When an action asks first, the plugin itself shows a confirmation box with exactly what's about to happen, and nothing happens until you click yes. Claude can't answer that box for you, so text hidden in a viewer's comment can't approve a delete. This needs a client that shows MCP confirmation dialogs (Claude Code 2.1.76 or later). In a client that can't, deleting a video and changing these settings are refused (delete in YouTube Studio instead), and the other actions fall back to Claude asking you in chat, which the plugin can't check.

**Built-in limits (always on, not adjustable).** These back up the MateAI Terms of Service ban on spam-like commenting and protect the daily YouTube quota that all MateAI users share.
- At most **20 comments and replies per hour** and **100 per 24 hours** (an upload's auto-posted comment counts too). The same text (ignoring case and spacing) can be posted at most **twice in 24 hours**, across all videos. When a limit is hit, nothing is posted and Claude is told when posting is allowed again. The count is kept in `comment_log.json` next to `safety.json` (timestamps and a hash of the text, not the text itself).
- When YouTube reports the quota or rate limit is used up (`quotaExceeded` / `rateLimitExceeded`), the plugin stops immediately with a clear message instead of retrying.

## YouTube API quota

A Google Cloud project gets **10,000 free YouTube Data API units per day**, reset at midnight Pacific time. With the built-in client that daily budget is shared by everyone using it; with [your own client](SETUP.md#use-your-own-google-cloud-client-optional-own-quota) it is yours alone. What each action costs, per [Google's quota table](https://developers.google.com/youtube/v3/determine_quota_cost) (checked 2026-11-08):

| Action | Data API calls | Units |
|---|---|---|
| Snapshot, list videos, video details, list comments | `*.list` | 1 per call |
| Upload a video (`yt_upload_draft`) | `videos.insert` | Own bucket of 100 uploads/day, not the 10,000 units |
| + custom cover | `videos.list` (waits for processing) + `thumbnails.set` | 50, plus 1 per processing check (at most 60) |
| + pinned comment | `commentThreads.insert` | 50 |
| Edit a video (`yt_update_video`) | `videos.list` + `videos.update` (+ `thumbnails.set`) | 51 (101 with a new cover) |
| Post a comment / reply | `commentThreads.insert` / `comments.insert` | 50 |
| Delete a video | `videos.list` + `videos.delete` | 51 |

Retention, swipe-away and other analytics come from the YouTube Analytics API, which isn't part of these 10,000 units.

## Privacy: what it runs, sends and fetches

Everything runs on your own computer. The author receives no data. Nothing is sent anywhere except to Google/YouTube (and to TikTok, only if you set up the optional TikTok connection), and to your Claude conversation, which is under Anthropic's own privacy terms (see [PRIVACY.md](../PRIVACY.md)).

With the built-in client, your API calls run under the author's Google Cloud project, so Google shows the author aggregate usage numbers for that project (such as request and error counts). It does not show your channel data, videos or login. With [your own client](SETUP.md#use-your-own-google-cloud-client-optional-own-quota) even those numbers stay in your project.

**The MCP server** (`mcp_server.py`, started by Claude Code as `python3 ${CLAUDE_PLUGIN_ROOT}/mcp_server.py`):
- Calls Google's **YouTube Data API v3** and **YouTube Analytics API v2** with the scopes you approve at sign-in: read-only analytics, and optionally upload, edit metadata and post comments.
- **Public mode (off by default):** fetches public `youtube.com` channel and video pages only when you opt in with `--public`, `force_public=true` or `MATEAI_YT_PUBLIC_SCRAPE=1`.
- `yt_upload_draft` reads the video and cover files whose paths you give it and uploads them to your channel. `yt_update_video` and `yt_post_comment` change your video or post a comment, only when called.
- Writes `channel_snapshot.json` and `report.html` (cached statistics for your own channel) to the plugin data folder.

**The `/yt-setup` command** (a Claude Code mod in `hooks/`):
- Only when the plugin has no built-in client: looks for a `client_secret*.json` in the plugin data folder, your current project and `~/Downloads` (up to 5 folders deep), copies a Desktop-app client into the data folder with `600` permissions, and opens two Google Cloud pages (macOS `open`, Windows `rundll32 url.dll,FileProtocolHandler`). It never prints the file.
- Creates a Python virtual environment in the data folder and runs `pip install -r requirements.txt` (from PyPI: `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`).
- Starts Google's sign-in in your browser, always with Google's account chooser, even when MateAI Studio is connected (the plugin's own login then wins over Studio's). Your Google password is typed on Google's own page and never reaches this plugin.
- Reads your saved token only to check which permissions it holds.
- `/yt-setup switch` starts the same sign-in while you are connected. The new login overwrites `.tokens/token.json` only when the sign-in succeeds; the previous one is not revoked (Google revokes per account and app, so that could end the new login or MateAI Studio's).
- `/yt-disconnect` sends the saved token to Google's revoke endpoint (`https://oauth2.googleapis.com/revoke`, in the request body), then deletes it. When a MateAI Studio login exists it skips the revoke (it would end Studio's login too) and only deletes the plugin's file. Either way it leaves an empty `.tokens/signed_out` file, so the plugin stays signed out, does not use Studio's login and starts no sign-in from a tool call; the next `/yt-setup` sign-in removes the file. Studio's Keychain item is never changed.

Where your login lives and how to remove it: [SETUP.md → Sign out or switch channel](SETUP.md#sign-out-or-switch-channel).

## What it doesn't do

- Transcripts of **other people's** videos: use a transcript MCP server.
- Playlists, bulk Reporting API exports, revenue or demographics: other YouTube MCP servers cover more of the API.

## Bundled skills and credits

The plugin ships the MCP server together with a YouTube strategy and creator skill suite, so your AI can go from niche research and hook writing to live Studio scheduling:

- **Live YouTube Studio execution and analytics** (the MCP tools above, `report.html` dashboard and `setup` wizard): built by **[MateAI (`@mateai-c6m`)](https://www.youtube.com/@mateai-c6m)**.
- **Production pipeline skills** (`yt-research`, `yt-ideation`, `yt-brief`, `yt-packaging`, `yt-outline`, plus the `/yt-pipeline` command and `yt-scraper`, `channel-analyzer`, `idea-validator` agents): created by **[Jeremy Longshore (`@jeremylongshore` / Intent Solutions)](https://github.com/jeremylongshore/tons-of-skills-marketplace/tree/main/plugins/productivity/youtube-strategy)** (`@intentsolutionsio/youtube-strategy`, MIT).
- **14 creator sub-skills and playbooks** (`audit`, `seo`, `script`, `hook`, `thumbnail`, `strategy`, `calendar`, `shorts`, `analyze`, `repurpose`, `monetize`, `competitor`, `metadata`, `ideate`): created by **[Daniel Agrici (`@AgriciDaniel`)](https://github.com/AgriciDaniel/claude-youtube)** (`claude-youtube`, MIT).
- **Chapters, comment replies and title lint** (`yt-chapters`, `yt-comment`, `yt-title-lint`): from **[Jake Schincariol (`@Jakeschincariol`)](https://github.com/Jakeschincariol/youtube-agent-skill)** (`youtube-agent-skill`, MIT). `yt-chapters` builds YouTube-valid chapters from an `.srt`/`.vtt`/Whisper transcript, `yt-comment` triages comments and drafts replies, and `yt-title-lint` checks a title and thumbnail as one pairing (renamed from `yt-package`). All three only write drafts; publishing stays with you or the MCP tools. They read an optional voice profile at `~/.claude/youtube/voice.md`.
