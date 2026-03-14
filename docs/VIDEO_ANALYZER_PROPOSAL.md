# Video Analysis Pipeline — Full Proposal

## What This Is

A system that gives Claude the ability to "watch" TikTok videos by extracting frames and transcripts, then analyzing them through Claude's multimodal API. The output is a **Style Bible** — a structured reference document of what works on TikTok — plus a **QA feedback loop** that compares our rendered videos against winning patterns.

This is the bridge between "we can make videos" and "we can make videos that work."

## Why This Matters

Our pipeline can now generate product videos for ~$0.10-0.15 each (Gemini images + Ken Burns + TTS). The bottleneck is no longer cost or speed — it's **quality**. We're making creative decisions (text placement, pacing, color, composition) based on research and assumptions. The Video Analysis Pipeline replaces assumptions with data from real winners.

---

## Architecture Overview

```
                    ┌──────────────────┐
                    │  TikTok Videos   │
                    │  (50+ .mp4s)     │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  STEP 1: Collect  │  Apify scraper or local .mp4 files
                    │  + metadata       │  Views, likes, shares, hashtags
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐  ┌──▼──────────┐  │
     │ STEP 2: Frames  │  │ STEP 3:     │  │
     │ FFmpeg extracts │  │ Whisper     │  │
     │ key frames      │  │ transcribes │  │
     └────────┬───────┘  └──┬──────────┘  │
              │              │              │
              └──────┬───────┘              │
                     │                      │
            ┌────────▼─────────┐            │
            │  STEP 4: Claude   │  Frames + transcript + metadata
            │  Vision Analysis  │  → structured JSON per video
            └────────┬─────────┘
                     │
            ┌────────▼─────────┐
            │  STEP 5: Style   │  All analyses → pattern synthesis
            │  Bible Synthesis │  → Style Bible (.md + .json)
            └────────┬─────────┘
                     │
         ┌───────────┼───────────────────┐
         │           │                   │
    ┌────▼────┐ ┌────▼──────┐  ┌────────▼────────┐
    │ Script  │ │ Image     │  │ QA Feedback     │
    │ Gen     │ │ Prompts   │  │ Loop            │
    │ Context │ │ Context   │  │ (our videos     │
    │         │ │           │  │  vs winners)    │
    └─────────┘ └───────────┘  └─────────────────┘
```

---

## All Use Cases (12 Identified)

### USE CASE 1: Style Bible for Script Generation (Primary)
**What:** Analyze 50+ winning TikTok Shop videos → produce a Style Bible → feed it as system context to the script generator.

**How it helps:** Instead of generic prompt instructions like "write a hook that stops the scroll," the generator gets concrete examples: "74% of top performers use price anchoring in the first 2 seconds, the median hook is 6 words, questions outperform statements 2.3:1."

**Integration point:** Style Bible markdown appended to CLAUDE.md or loaded dynamically by `script_generator.py` when building prompts.

**Cost:** ~$3-8 per 50-video analysis run (one-time, then refresh monthly).

---

### USE CASE 2: QA Feedback Loop (Highest Impact)
**What:** After rendering a video, extract its frames → send to Claude alongside frames from a winning reference video → get a structured comparison critique.

**How it helps:** Before publishing, we know: "Your text is 120px too low and will be covered by the product card. The hook frame lacks visual contrast compared to the reference. Your cut pace is 5s average vs the winner's 2.3s."

**Integration point:** New `analyze_own_video()` function that runs after `render_product_video()`. Returns a quality score and specific improvement suggestions. Could gate publishing — only publish videos scoring above a threshold.

**Cost:** ~$0.03-0.05 per video analysis (5 frames + text to Claude).

---

### USE CASE 3: Competitor Intelligence
**What:** Scrape 50 videos from each of 3-5 top TikTok Shop sellers in your niche → analyze separately → compare Style Bibles.

**How it helps:** Reveals competitor-specific strategies. "Seller A always uses before/after comparisons. Seller B leads with price. Seller C uses rapid cuts (1.2s average) while Seller D uses slow pans (4s average)." Lets you pick which strategies to adopt or differentiate from.

**Integration point:** Multiple Style Bibles stored in `data/style_bibles/`. Pipeline config selects which one(s) to reference.

**Cost:** ~$10-25 per competitor (one-time analysis).

---

### USE CASE 4: Niche-Specific Style Guides
**What:** Build separate Style Bibles for different product categories — skincare, tech gadgets, fashion, supplements, home goods.

**How it helps:** What works in skincare (soft lighting, warm tones, close-up textures) is completely wrong for tech (sharp angles, dark backgrounds, feature callouts). Niche-specific guides prevent the pipeline from applying wrong patterns to wrong products.

**Integration point:** `pipeline_config.json` has a `"niche"` field. Style Bible auto-selected based on niche. Falls back to general if no niche-specific guide exists.

**Cost:** ~$5-10 per niche (one-time per niche).

---

### USE CASE 5: Publish-Then-Learn Loop
**What:** After publishing videos and collecting 48-72 hours of performance data (views, completion rate, shop clicks, conversions), feed the top performers and the flops back through the analyzer. Claude compares: "What did the winners do differently?"

**How it helps:** Closes the learning loop with OUR OWN data. Over time, the Style Bible evolves from "what works on TikTok generally" to "what works for OUR account, OUR products, OUR audience."

**Integration point:** Publisher module already tracks posted videos. Add a `collect_performance()` step that pulls stats 72 hours later via Apify, then triggers re-analysis.

**Cost:** ~$0.10-0.20 per cycle (re-analyze top 5 + bottom 5 from each batch).

---

### USE CASE 6: Trend Drift Detection
**What:** Run the analyzer monthly on fresh top-performing videos in your niche. Diff this month's Style Bible against last month's.

**How it helps:** TikTok trends shift fast. Hook patterns that worked in January may be stale by March. Automated trend drift detection tells you: "Price anchoring hooks dropped 30% in effectiveness this month. POV-style hooks are up 45%. Rapid cuts are getting even faster — median cut pace moved from 2.5s to 1.8s."

**Integration point:** Style Bible versioned with dates. `detect_drift()` function compares two versions and outputs a change report.

**Cost:** ~$5-10 per monthly refresh.

---

### USE CASE 7: Thumbnail / First-Frame Optimization
**What:** Analyze just the first frame (the scroll-stopping moment) across all 50 videos. Correlate visual properties with view counts.

**How it helps:** The first frame IS the thumbnail that determines if someone stops scrolling. Analysis reveals: "High performers have 73% more color contrast in frame 1. 80% show the product within 200px of center. Text overlays appear in 65% of top performers' thumbnails but only 30% of underperformers'."

**Integration point:** Feeds directly into Gemini image generation prompts for scene_00 (the hook image). Also influences Ken Burns — should the first image zoom in (draw attention to center) or start wide?

**Cost:** Included in the main analysis run (no additional cost).

---

### USE CASE 8: Script-to-Video Alignment Scoring
**What:** Send Claude both the generated script AND the rendered video frames. Ask: "Does this video visually deliver what the script promises?"

**How it helps:** Catches drift between intent and execution. The script says "show the texture close-up" but the Ken Burns effect is zoomed too far out. The script says "price badge in corner" but the badge is positioned in a dead zone. Automated alignment scoring catches these before publishing.

**Integration point:** Post-render QA step. Returns alignment score (0-100) and specific mismatches.

**Cost:** ~$0.03-0.05 per video.

---

### USE CASE 9: Audio/Pacing Strategy Optimization
**What:** Beyond Whisper transcription, analyze audio energy curves (loudness over time) and correlate with engagement. Map when energy spikes, when there's silence, where the hook-to-body transition happens acoustically.

**How it helps:** Reveals audio patterns: "Top performers spike audio energy at 0.5s (the hook), drop slightly at 3s (transition), maintain steady energy through body, and spike again at CTA. There's a 0.3s silence right before the CTA that creates anticipation."

**Integration point:** Feeds TTS configuration — voice pacing, emphasis points, pause timing. Also informs background music mixing — energy curve of music should complement voice energy.

**Cost:** Free (FFmpeg loudness analysis is local computation).

---

### USE CASE 10: Color Palette Intelligence
**What:** Programmatically extract dominant colors from each frame across all 50 videos. Build color profiles correlated with engagement.

**How it helps:** Our 5 hardcoded color themes (warm/cool/energetic/calm/default) are based on assumptions. Real data might show: "Skincare winners use warm beige (#F5E6D3) backgrounds 3x more than any other color. Text is almost always white (#FFFFFF) on warm backgrounds, never yellow. Accent colors cluster around coral (#FF6B6B) not gold (#FFD700)."

**Integration point:** Auto-generate color themes from winning videos. Replace hardcoded COLOR_THEMES with data-driven palettes per niche.

**Cost:** Free (PIL/OpenCV color extraction is local computation).

---

### USE CASE 11: Smart Frame Selection via Scene Detection
**What:** Instead of extracting 5 evenly-spaced frames, use FFmpeg's scene change detection to capture frames at actual visual transitions.

**How it helps:** Evenly-spaced frames might miss the actual cuts and catch mid-transition blur. Scene detection captures the real structure — exactly where the creator chose to cut. This gives accurate cut frequency data (cuts per second) that can be correlated with engagement.

**How:**
```bash
ffmpeg -i video.mp4 -vf "select='gt(scene,0.3)',showinfo" -vsync vfn frame_%03d.jpg
```

**Integration point:** Cut frequency becomes a numeric metric in the analysis JSON. Feeds our `_calculate_image_timing()` function — instead of a linear weight falloff, use the actual pacing pattern from winners.

**Cost:** Free (local FFmpeg computation).

---

### USE CASE 12: On-Screen Text / OCR Analysis
**What:** Extract and analyze text overlays that appear in winning videos — what text, where positioned, what size, when it appears/disappears.

**How it helps:** TikTok Shop videos are text-heavy. Analysis reveals: "Hook text appears in the top 20% of the frame in 85% of winners. Price badges are always upper-right with dark background boxes. CTA text is centered at 70% height, never at dead center. Font sizes cluster around 60-80px for hooks, 36-48px for body."

**Integration point:** Directly validates and tunes our safe zone constants (HOOK_TEXT_Y, BODY_TEXT_Y, CTA_TEXT_Y, PRICE_BADGE_X/Y) and font sizes (HOOK_FONT_SIZE, BODY_FONT_SIZE, etc.). Data replaces assumptions.

**Cost:** ~$0.01 per video (Claude vision reads text from frames — no additional API needed beyond the main analysis).

---

## Implementation Plan

### Phase 1: Core Pipeline (MVP)
Build the 5-step pipeline as described in the user's spec document.

**Files to create:**
- `src/analyzers/video_analyzer.py` — Main pipeline orchestrator
- `src/analyzers/frame_extractor.py` — FFmpeg frame extraction + scene detection
- `src/analyzers/transcriber.py` — Whisper audio transcription
- `src/analyzers/video_analysis.py` — Claude multimodal per-video analysis
- `src/analyzers/style_bible.py` — Synthesis across all analyses
- `src/analyzers/__init__.py` — Package init
- `src/analyzers/__main__.py` — CLI entry point

**New directories:**
- `videos/` — Input TikTok videos
- `data/frames/` — Extracted key frames
- `data/transcripts/` — Whisper transcriptions
- `data/analysis/` — Per-video Claude analysis JSON
- `data/style_bibles/` — Generated Style Bibles

**Dependencies to add:**
- `openai-whisper` or `openai` (for Whisper API) — transcription
- `Pillow` — color palette extraction
- No new dependencies for frame extraction (FFmpeg already installed)
- No new dependencies for Claude analysis (anthropic SDK already installed)

**Estimated effort:** ~800-1000 lines of code + tests.

### Phase 2: QA Feedback Loop
Build the self-analysis capability — analyze our own rendered videos.

**Files to create/modify:**
- `src/analyzers/qa_analyzer.py` — Compare our output to Style Bible
- `src/renderers/video_builder.py` — Optional post-render QA hook

### Phase 3: Advanced Analysis
Add the enhancement use cases incrementally.

- Scene detection for smart frame selection (Use Case 11)
- Audio energy curve analysis (Use Case 9)
- Color palette extraction (Use Case 10)
- On-screen text analysis (Use Case 12)

### Phase 4: Continuous Learning
- Performance data collection post-publish (Use Case 5)
- Trend drift detection (Use Case 6)
- Style Bible versioning and comparison

---

## Cost Summary

| Activity | Frequency | Cost |
|----------|-----------|------|
| Initial Style Bible (50 videos) | One-time | $3-8 |
| Monthly Style Bible refresh | Monthly | $5-10 |
| QA on own videos | Per video | $0.03-0.05 |
| Competitor analysis (per seller) | One-time | $10-25 |
| Niche-specific guide | Per niche | $5-10 |
| Publish-then-learn cycle | Per batch | $0.10-0.20 |
| Local analysis (frames, audio, color) | Always | Free |

At 500 videos/month production, QA analysis adds ~$15-25/month. Total analysis budget: **~$25-50/month** comfortably within the $100 total budget alongside video production costs.

---

## The Flywheel

This is the end state — a self-improving content machine:

```
  Analyze winners ──→ Build Style Bible ──→ Generate scripts
        ↑                                        │
        │                                        ▼
        │                              Generate images (Gemini)
        │                                        │
        │                                        ▼
        │                              Render video (Ken Burns)
        │                                        │
        │                                        ▼
        │                              QA analysis (compare to Bible)
        │                                        │
        │                              ┌─────────┴─────────┐
        │                              │                   │
        │                          Score < 70          Score ≥ 70
        │                              │                   │
        │                          Re-render           Publish
        │                          with fixes              │
        │                                                  ▼
        │                                        Collect performance
        │                                        data (72hr)
        │                                                  │
        └──────────── Learn from results ◄─────────────────┘
```

Every loop makes the Style Bible smarter, the scripts better targeted, the visual choices more data-driven. The $100/month budget produces increasingly better content without any additional human effort.

---

## Source Document
User's original spec: `C:\Users\Jonathan\Downloads\tiktok_pipeline_documentation.docx` (March 12, 2026)
