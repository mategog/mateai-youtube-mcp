# TikTok (optional, experimental)

[← Back to README](../README.md)

Cross-post your Shorts and see how they do on both platforms. This uses TikTok's official, free developer API only: no cookies, no scraping. It never publishes for you; a video lands in your TikTok app inbox and you tap Post yourself. The YouTube tools work the same whether or not you set this up.

**Experimental: you need your own TikTok developer app, in sandbox mode.** Unlike the YouTube side, the plugin has no shared app: you create one at developers.tiktok.com. Without TikTok's app review, an app only works in its **sandbox**, and only for the TikTok accounts you add there as **target users** (your own account). Status today: stats (`tiktok_channel_snapshot`) are tested through a sandbox app; sending a draft to the inbox through a sandbox app is **not tested yet**.

> "Send `exports/short.mp4` to my TikTok inbox with the caption from `planning/my-short-upload.md`."
>
> "Show my YouTube Shorts next to the same videos on TikTok."

## Connect TikTok (once)

1. Create an app at [developers.tiktok.com](https://developers.tiktok.com/) and choose the **Desktop** platform.
2. Open the app's **Sandbox** (create one if there is none). Do the next steps in the sandbox.
3. Add the redirect URI `http://127.0.0.1:8765/callback/` (exactly, with the trailing slash).
4. Enable these scopes: `user.info.basic`, `user.info.profile`, `user.info.stats`, `video.list`, `video.upload`.
5. Under **Target users**, add the TikTok account you'll use. Only target users can sign in; any other account gets a `non_sandbox_target` error.
6. Click **Apply changes**. Edits in the sandbox don't take effect until you do.
7. Run the wizard. It asks for the sandbox's Client Key and Client Secret, opens TikTok's sign-in in your browser, and saves the token locally. Keep the wizard running until the sign-in finishes:

```bash
python3 tiktok_studio.py setup
```

If you installed the plugin, point it at the plugin's data folder first, the same way as for the YouTube wizard: `MATEAI_YT_HOME=~/.claude/plugins/data/yt-studio-mateai-youtube-mcp python3 tiktok_studio.py setup`.

## Tools

| Tool | What it does |
|---|---|
| `tiktok_channel_snapshot` | Fetch your TikTok profile stats and recent videos (views, likes, comments, shares) through TikTok's official API. |
| `tiktok_draft_status` | Check where a video sent with `tiktok_upload_draft` stands (waiting in the inbox, processing, posted, or failed with TikTok's reason). Read-only. |
| `tiktok_upload_draft` | Send a local MP4/MOV to your TikTok app inbox and return the caption to paste, plus a reminder to switch on TikTok's AI-generated label. It does not publish for you. |
| `cross_platform_shorts_table` | Markdown table that pairs each YouTube Short with the same video on TikTok (views, likes, comments, YouTube avg % viewed, TikTok shares). Videos that exist on only one platform get their own row. |

## Command line

```bash
python3 tiktok_studio.py snapshot                                   # profile and recent videos
python3 tiktok_studio.py upload-draft --video exports/short.mp4 \
  --spec planning/my-short-upload.md                                # send to your TikTok inbox
python3 tiktok_studio.py cross-table                                # YouTube Shorts vs TikTok
```

## Good to know

- **Drafts only, never public posts.** Posting directly needs the `video.publish` scope and TikTok's audit, and TikTok forces posts from unaudited apps to private. The plugin only sends drafts to your inbox (`video.upload`).
- **Captions are pasted by hand.** TikTok's inbox upload cannot take a caption. `tiktok_upload_draft` builds one from your upload spec (title plus the `#hashtags` in the description, `#Shorts` removed) and returns it for you to paste in the app.
- **Switch on the AI-generated label yourself.** If your video uses a synthetic voice or AI visuals, turn on TikTok's AI-generated content toggle in the app before posting. The API cannot set it.
- **Matching is by title.** The comparison table pairs a Short with a TikTok when the title (hashtags ignored) matches the TikTok title or description. Anything else shows up as its own row, with "—" for the missing platform.
- **Only official numbers.** TikTok's API gives views, likes, comments and shares. Retention-style metrics exist for YouTube only.
- **Your data.** The client file is `tiktok_auth_secret/tiktok_client.json` and the login token is `.tokens/tiktok_token.json`, both owner-only (`0600`) and `.gitignore`d. The cache is `tiktok_snapshot.json`, and every `tiktok_channel_snapshot` call also appends a counts row to `tiktok_history.jsonl` so growth can be measured later. Details in [PRIVACY.md](../PRIVACY.md).

## Troubleshooting

| Problem | Fix |
| --- | --- |
| "No TikTok OAuth token found" | Run `python3 tiktok_studio.py setup`. |
| "TikTok refresh token expired" | Run `python3 tiktok_studio.py setup` again to sign in. |
| Setup waits, then times out | The browser tab was closed. Rerun setup; it waits 5 minutes for the sign-in. |
| Sign-in page rejects the redirect | The redirect URI in your TikTok sandbox must be exactly `http://127.0.0.1:8765/callback/`. |
| `non_sandbox_target` or a scope error | Add your account under **Target users**, check the scopes, then click **Apply changes** in the sandbox and rerun setup. |
| The wrong TikTok account got connected | The browser was already signed in to another TikTok account and used it without asking. Sign out of TikTok in the browser, then rerun setup. |
| Channel handle is empty | The `user.info.profile` scope is missing. Enable it in your TikTok app and run setup again. |
