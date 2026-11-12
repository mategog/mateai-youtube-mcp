# Privacy Policy — MateAI YouTube Studio plugin (yt-studio)

Last updated: 2026-11-03

This plugin runs entirely on your own computer. It has no server of its own, and the author (MateAI) receives no data from it.

## What it accesses

- **Public channel pages** on youtube.com, only if you opt in to public mode, to read public video titles, views and likes.
- **Your YouTube account, only if you run the OAuth setup.** It uses Google's YouTube Data API v3 and YouTube Analytics API v2 with the scopes you approve: read-only analytics, and optionally upload, metadata edits and comments.
- **Your TikTok account, only if you run the TikTok OAuth setup (`python3 tiktok_studio.py setup`).** It uses TikTok's official Login Kit, Display API v2, and Content Posting API (`open.tiktokapis.com`) with the scopes you approve: `user.info.basic`, `user.info.profile`, `user.info.stats`, `video.list`, and `video.upload` (Inbox draft upload).

## What it stores, and where

Everything is saved locally, in the plugin's data folder (`~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/`) or in `MATEAI_YT_HOME`:

- `client_secret.json`: your own Google OAuth client, only if you created one (otherwise the plugin's built-in `oauth_client.json` is used)
- `.tokens/token.json`: your YouTube OAuth token, with file mode 0600
- `channel_snapshot.json` and `report.html`: cached YouTube channel statistics
- `tiktok_auth_secret/tiktok_client.json`: the TikTok Desktop app client credentials you configured, with file mode 0600
- `.tokens/tiktok_token.json`: your TikTok OAuth token, with file mode 0600
- `tiktok_snapshot.json`: cached TikTok profile and video statistics
- `tiktok_history.jsonl`: one line of TikTok counts (followers, likes, per-video views/likes/comments/shares) appended each time `tiktok_channel_snapshot` runs, with file mode 0600

Nothing is sent anywhere except Google/YouTube (and TikTok when you use the optional TikTok tools). The statistics the tools return go into your Claude conversation, under Anthropic's own privacy terms.

## Removing your data

Delete the data folder above, revoke Google access at https://myaccount.google.com/permissions, and revoke TikTok app access in the TikTok mobile app under **Settings and privacy → Security and permissions → Apps and services permissions**.

## Contact

https://github.com/mategog/mateai-youtube-mcp/issues
