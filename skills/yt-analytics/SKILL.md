---
name: yt-analytics
description: Surgical YouTube Studio analytics & retention diagnosis skill. Pulls live Studio OAuth telemetry (Viewed vs Swiped, Avg % Viewed, 100-point retention curves, exact MM:SS drop-off cliffs, YouTube peer percentiles, and traffic sources), maps drop-offs onto the exact spoken script/words.js lines, and prescribes concrete changes for the next video. Trigger on 'analytics', 'retention', 'why did views stop', 'diagnose my video', 'swipe rate', 'how are my videos doing', or 'yt-analytics'.
---

# YouTube Surgical Analytics & Retention Autopsy (`yt-analytics`)

Built by [MateAI (@mateai-c6m)](https://www.youtube.com/@mateai-c6m) · Powered by the `mateai-youtube` MCP Server.

> **Core Rule:** Never dump a raw table of view counts and call it "analytics". Your job is to isolate **where in the distribution funnel a video leaked**, identify **the exact second and spoken sentence where viewers left**, and prescribe **concrete script/packaging changes** for the creator's next upload.

---

## Step 1: Gather Live Studio Telemetry via MCP

Always fetch the real numbers first before offering any opinion:

1. **Channel-wide overview & Shorts style comparison:**
   - Call `yt_channel_snapshot` and `yt_shorts_experiment_table`.
2. **Per-video 100-point Retention Curve & Script Mapping:**
   - For the video(s) being analyzed, check if a local Whisper word-timing file (`pipeline/explainer-short/<slug>/words.js` or `out/*.json`) or script (`scripts/<slug>.md`) exists in the workspace.
   - Call `yt_video_details(video_id="<ID>", words_or_script_path="<optional_path>")`.
   - This returns:
     - `trafficSources`: Breakdown across `SHORTS`, `YT_SEARCH`, `SUBSCRIBER`/`BROWSE`, `RELATED_VIDEO`.
     - `retentionCheckpoints`: Exact `% watching` and **`youtubePeerPercentile`** (`0–100%` vs YouTube videos of similar length) at `3%` (hook), `10%`, `25%`, `50%`, `75%`, and `100%`.
     - `steepestDropOffCliffs`: Top 5 steepest drop-off moments with `timestampFmt` (`MM:SS`), `beforeWatchingPct -> afterWatchingPct`, `dropPctPoints`, and `spokenWordsAtCliff`.

*(Note on Day-1 Uploads: Google's YouTube Analytics API v2 updates daily 24–48h after upload. For videos published today, compare the Data API's verified `viewCount` against YouTube Studio's realtime feed starts to estimate day-1 swipe-through rate.)*

---

## Step 2: The 4-Layer Diagnostic Framework

Run every video or channel audit through these 4 diagnostic layers in order:

### Layer 1: Distribution Funnel Gate Diagnosis (Where is the bottleneck?)

#### A. For YouTube Shorts (`duration <= 180s`)
The Shorts algorithm promotes in two sequential gates:
1. **Gate 1 — The Hook / Swipe Gate (`Viewed vs. Swiped Away %`)**:
   - **`< 55%` Viewed**: **First-2-Second Hook Failure.** The opening visual card or first spoken clause failed to stop the scroll. Fix the opening frame and first 5 words; do not blame the topic.
   - **`55% – 70%` Viewed**: **Seed-Pool Average.** Gets a 200–1,000 view test push, then plateaus unless completion rate is exceptional (`>90%`).
   - **`> 70%` Viewed**: **Algorithmic Expansion Zone.** The hook works; total reach is now governed by Gate 2.
2. **Gate 2 — The Completion / Pacing Gate (`Avg % Viewed` & `50%` Checkpoint)**:
   - Compare `Avg % Viewed` against video length:
     - Under 60s Short: target **`> 85–100%+`**.
     - 60s–120s Explainer Short: target **`> 65–75%`**.
   - **High Viewed-vs-Swiped (`>70%`) + Low Avg % Viewed (`<50%`)**: **Mid-Script Cliff / Over-Length.** The hook stopped the scroll, but a mid-video tangent or slow scene killed completion before the payoff.

#### B. For Long-Form Videos (`duration > 180s`)
1. **First-30-Second Survival (`hook_3pct` & `10pct` checkpoints + Peer Percentile)**:
   - If `watchingPct` drops below `45%` inside the first 20–30 seconds (or `youtubePeerPercentile < 20%` at `10pct`), **the intro has throat-clearing or fails to match the title/thumbnail promise immediately**.
2. **Body Stability (`10pct` → `50pct` → `100pct` Peer Percentile trajectory)**:
   - **Rising Peer Percentile** (e.g., `10pct` is at the `8th percentile`, but `50pct`–`100pct` climbs to the **`50th+ percentile`**):
     - **Diagnosis:** **Good Core Video Trapped Behind a Leaky First 20 Seconds.** The demo/build-log satisfies viewers who stay, so cutting the first 20 seconds of setup on the next video is the highest-leverage fix.
   - **Falling Peer Percentile** (starts `>50th percentile`, sinks `<15th percentile` by midpoint):
     - **Diagnosis:** **Bait-and-Switch or Pacing Drag.** The intro hooked them, but the middle dragged before showing the real result.
3. **Traffic Source Mix (`trafficSources`)**:
   - **Heavy `YT_SEARCH` (`>50%`), low `BROWSE` / `RELATED_VIDEO`**: Title matches search keywords well, but the thumbnail/title curiosity gap isn't triggering homepage Browse clicks.

---

### Layer 2: Second-by-Second Script & Visual Autopsy

Never say *"retention dropped in the middle."* Pinpoint the **exact timestamp (`MM:SS`)** from `steepestDropOffCliffs` and quote the **exact words spoken at that second**:

Classify each cliff into one of the **4 Classic Retention Killers**:
1. **The "Promise Broken / Tangent" Cliff**: The script pivots away from the title's core tension into secondary filler (e.g., saying *"Beyond [main topic], it also does X, though there are no numbers for those"*). Viewers immediately feel the main story is over and swipe.
2. **The "Throat-Clearing Intro" Cliff (`0:00–0:25`)**: Explaining background context, channel history, or setup before showing the stakes or the working artifact.
3. **The "Stat Fatigue" Cliff**: Reading more than 3 numbers in a row without a visual contrast shift or human verdict ("here's why that number is misleading").
4. **The "False Ending" Cliff**: Summarizing or dropping vocal energy before the final takeaway, signaling to the viewer that they can leave early.

---

### Layer 3: Visual Style & Length Experiment Grader

When evaluating Shorts across visual styles (e.g., `Grid` vs `Poster Cuts` vs `Red Pen` vs `Bench Drawing`):
- Always control for **duration (`durationSec`)**! A 120-second Short with `45%` Avg % Viewed (`54s` watched) held viewers for almost as many raw seconds as a 65-second Short with `85%` Avg % Viewed (`55s` watched), even though YouTube's algorithm heavily rewards the **percentage completion (`85%`)**.
- Highlight both **Average Seconds Watched (`avgViewDurationSec`)** and **Average % Viewed (`avgViewPct`)** so the creator sees whether a lower `%` is caused by the visual style or simply by the script being 2x longer.

---

### Layer 4: Concrete Next-Action Prescription

End every analytics report with **3 concrete, falsifiable actions**:
1. **One Script/Hook Rule for the Next Video** (quoting the exact timestamp/line that proved why).
2. **One Length or Structure Target** (e.g., cutting a specific scene type to keep Shorts at `65–75s` instead of `120s`).
3. **One Live Packaging Action (if applicable)** that can be executed immediately via `yt_update_video` (e.g., sharpening a title or swapping a thumbnail on a video whose body retention beats the 50th percentile).
