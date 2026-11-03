# Privacy Policy — MateAI YouTube Studio plugin (yt-studio)

Last updated: 2026-11-03

This plugin runs entirely on your own computer. It has no server of its own, and the author (MateAI) receives no data from it.

## What it accesses

- **Public channel pages** on youtube.com, to read public video titles, views and likes.
- **Your YouTube account, only if you run the OAuth setup.** It uses Google's YouTube Data API v3 and YouTube Analytics API v2 with the scopes you approve: read-only analytics, and optionally upload, metadata edits and comments.

## What it stores, and where

Everything is saved locally, in the plugin's data folder (`~/.claude/plugins/data/yt-studio-mateai-youtube-mcp/`) or in `MATEAI_YT_HOME`:

- `client_secret.json`: the Google OAuth client you created
- `.tokens/token.json`: your OAuth token, with file mode 0600
- `channel_snapshot.json` and `report.html`: cached channel statistics

Nothing is sent anywhere except Google/YouTube. The statistics the tools return go into your Claude conversation, under Anthropic's own privacy terms.

## Removing your data

Delete the data folder above, and revoke the app's access at https://myaccount.google.com/permissions.

## Contact

https://github.com/mategog/mateai-youtube-mcp/issues
