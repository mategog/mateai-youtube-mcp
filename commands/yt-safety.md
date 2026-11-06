---
name: yt-safety
description: Choose which YouTube actions Claude must ask you about before doing them
allowed-tools: AskUserQuestion, mcp__plugin_yt-studio_mateai-youtube__yt_get_safety_settings, mcp__plugin_yt-studio_mateai-youtube__yt_set_safety_settings
model: sonnet
---

Help the user choose which actions Claude must check with them before doing. The user is a content creator, not a developer: use plain words, never mention tool names, files or settings keys.

1. Call `yt_get_safety_settings` to see what asks first right now.
2. Tell the user in one or two short sentences: deleting a video always asks first and can't be turned off, and any action they pick below will also ask first (a small confirmation box pops up showing what is about to happen, and nothing happens until they click yes).
3. Ask with AskUserQuestion, `multiSelect: true`, "Which of these should Claude ask you about first?". Use exactly these options and mark in the description which ones already ask:
   - **Uploading videos** — covers `yt_upload_draft` and `tiktok_upload_draft`
   - **Changing a video's details** — covers `yt_update_video` (title, description, visibility, schedule)
   - **Posting or replying to comments** — covers `yt_post_comment` and `yt_reply_comment`
4. Call `yt_set_safety_settings` with `confirm` set to every tool covered by the options they picked (an empty list if they picked none). A confirmation box pops up for this change; tell them to tick yes there. If the result says the change was declined or not done, say so plainly and stop.
5. Confirm in plain words what now asks first, e.g. "Done. From now on I'll check with you before deleting a video and before posting or replying to comments." Mention they can run this again any time to change it.

If they say they're not sure, recommend asking about everything while they get comfortable, since the questions are quick.
