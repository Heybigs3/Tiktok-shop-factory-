# Video Improvement Report — TikTok Factory

## Current State

Our renderer (`video_builder.py`) produces **solid-color backgrounds with static centered text** in 3 sections (hook/body/CTA). This is the visual equivalent of a PowerPoint slide — functional but not competitive. Here's what top-performing faceless TikTok content actually looks like, and a concrete plan to get there.

---

## The Gap: Our Videos vs. What Performs

| Element | Our Current Videos | Top Faceless TikTok Videos |
|---|---|---|
| **Background** | Solid color | Stock footage clips, AI images, animated gradients, or split-screen with gameplay |
| **Text style** | Static centered text, shadow offset | Word-by-word reveal, colored keyword highlight, outline/stroke, bounce-in animations |
| **Audio** | Silent | TTS voiceover + lo-fi background music at 10-20% volume + transition sound effects |
| **Captions** | None (text IS the content) | "Hormozi style" — active word highlight, 3-5 words at a time, synced to speech |
| **Transitions** | 0.5s crossfade | Slide-up, fade-through-black, zoom, wipe — varied per section |
| **Engagement elements** | None | Progress bar at top, step counters, emoji accents |
| **Pacing** | One text block per section | Visual change every 2-3 seconds, multiple text reveals per section |

---

## Research Findings (Key Numbers)

### Audio is the #1 gap
- **TTS voiceover increases completion rate by 23%** on average
- **70-80% of TikTok users** watch with sound off at times — captions + audio covers both
- The best TTS voice achieved **65.8% completion rate**
- Background music should be **10-20% volume** — ambient texture, not the focus
- Silent text-only videos get significantly lower algorithmic distribution

### Visual motion retains attention
- Videos with **dynamic backgrounds outperform static** by a wide margin
- Visual changes should happen **every 2-3 seconds** — static screens kill retention
- Lo-fi, slightly unpolished content gets **31% higher engagement** than over-produced content
- The **split-screen format** (text top, stock footage bottom) is the #1 proven faceless format

### Text animation is expected
- Videos with captions get up to **10x more engagement**
- Captions increase completion rate by **32%** and watch time by **12-40%**
- **Word-by-word highlight** is the dominant caption style in 2025-2026
- Ideal caption chunk: **3-7 words**, displayed for **1-3 seconds** each

### Algorithm priorities (ranked)
1. Watch time and completion rate (the #1 factor)
2. Saves and shares (outweigh likes)
3. Comments (especially from question CTAs)
4. Replays/loops
5. On-screen text keywords (TikTok indexes all text for search)
6. Video quality (1080p, clear audio)
7. Originality (TikTok down-ranks mass-produced AI content)

---

## Implementation Plan: 4 Tiers

### Tier 1 — Quick Wins (FFmpeg only, no new dependencies)

These are achievable with our existing FFmpeg setup, mostly filter parameter changes:

**1a. Text outline instead of shadow hack**
Replace the current shadow (black text offset 3px) with proper `borderw`:
```
drawtext=borderw=3:bordercolor=black:fontcolor=white
```
Cleaner, more readable, standard TikTok look. One parameter change per drawtext call.

**1b. Text fade-in per section**
Add alpha animation to drawtext so text fades in over 0.3s instead of appearing instantly:
```
drawtext=alpha='min(t/0.3,1)'
```

**1c. Progress bar at video top**
A thin colored bar that grows left-to-right showing video progress:
```
drawbox=x=0:y=0:w='t/TOTAL*W':h=4:color=accent:t=fill
```
~5 lines of code. Strong retention signal — viewers see how much is left.

**1d. Better transitions**
Rotate through `slideup`, `fadeblack`, `dissolve`, `wipeup` based on theme instead of always using `fade`. One string change per render.

**1e. Background box behind text**
Semi-transparent dark box behind text for readability over any background:
```
drawtext=box=1:boxcolor=black@0.6:boxborderw=15
```

**1f. Safe zone compliance**
Move text out of TikTok's UI overlap zones. Keep text in the middle 60-70% of the frame vertically (avoid top 10% for status bar, bottom 20% for TikTok buttons).

---

### Tier 2 — Audio Layer (New: TTS + Music)

**2a. TTS Voiceover (HIGHEST IMPACT SINGLE IMPROVEMENT)**

Add text-to-speech narration of the hook/body/CTA text. This is the single biggest engagement lift available to us.

**Service options:**
| Service | Quality | Cost | Speed | Notes |
|---|---|---|---|---|
| **OpenAI TTS** (`tts-1`) | Good | $0.015/1K chars | Fast | 6 voices, simple API, already have API patterns |
| **OpenAI TTS HD** (`tts-1-hd`) | Great | $0.030/1K chars | Slower | Same API, better quality |
| **ElevenLabs** | Best | $0.30/1K chars | Fast | Most natural, expensive, 29 languages |
| **Edge TTS** (`edge-tts`) | Decent | Free | Fast | Microsoft Edge voices, no API key needed |
| **Google Cloud TTS** | Great | $0.004/1K chars | Fast | Cheapest paid option, good quality |

**Recommendation:** Start with **Edge TTS** (free, decent quality, `pip install edge-tts`) for development and testing. Upgrade to **OpenAI TTS** for production (we already have the API key, good quality, low cost at ~$0.015/1K chars = ~$0.002 per video script).

**Architecture:**
```
script text → TTS API → audio file (MP3/WAV)
audio file → FFmpeg amix with background music → final video
```

Video section timing would be driven by TTS audio duration instead of word-count estimates, making pacing natural.

**2b. Background Music**

Add `assets/music/` directory with 3-5 royalty-free lo-fi tracks. Sources:
- Fesliyan Studios — has a "dialogue/voiceover" category specifically for under-speech
- Chosic — free TikTok-safe tracks
- Bensound — lo-fi/ambient category

FFmpeg mixing:
```
amovie=music.mp3:loop=0,volume=0.15,afade=t=in:d=1,afade=t=out:st=END-1:d=1
```
Music loops, ducked to 15% volume, with 1s fade in/out.

---

### Tier 3 — Visual Backgrounds (New: Image/Video sourcing)

Replace solid colors with actual visual content behind the text.

**3a. Stock footage backgrounds**

Source free stock video clips from Pexels API (free, no key needed for limited use) or bundle a small library of looping clips in `assets/backgrounds/`:
- Nature scenes (calming niches)
- City timelapses (business/hustle niches)
- Satisfying/abstract loops (general purpose)
- Skincare close-ups (our current niche)

FFmpeg compositing:
```
ffmpeg -i background_clip.mp4 -vf "scale=1080:1920,zoompan=z='1+0.001*t'" ...
```

**3b. AI-generated image backgrounds**

Use an image generation API to create niche-relevant backgrounds per script. The script's `visual_hints.mood` and topic can drive the prompt. Apply Ken Burns (slow zoom/pan) for motion:
```
zoompan=z='1.0+0.002*t':d=duration*fps:s=1080x1920
```

**3c. Split-screen format**

The #1 proven faceless format: text/captions on top half, visual footage on bottom half. FFmpeg can do this with `split` + `crop` + `vstack`.

---

### Tier 4 — Advanced Text Animation

**4a. Word-by-word caption reveal**

Instead of showing the full body text at once, reveal words one at a time synced to TTS timing. This is the "Hormozi style" that dominates TikTok.

Implementation: Generate one drawtext filter per word with staggered `enable` times. Python computes timing from TTS audio duration.

```python
# Pseudocode
words = body_text.split()
time_per_word = audio_duration / len(words)
for i, word in enumerate(words):
    start = i * time_per_word
    filters.append(f"drawtext=text='{word}':enable='gte(t,{start})':fontcolor=yellow")
```

**4b. Active word highlight**

Show all caption words, but the current word changes color (yellow or green). Requires rendering each word at a computed x-offset with conditional color:
```
fontcolor='if(between(t,word_start,word_end),0xFFFF00,0xFFFFFF)'
```

**4c. Word bounce/pop-in**

Animate fontsize per word: scale from 0 to target size with overshoot easing when each word appears.

---

## Recommended Build Order

Based on impact-per-effort:

| Priority | Feature | Impact | Effort | Dependency |
|---|---|---|---|---|
| **P0** | TTS voiceover | Huge (+23% completion) | Medium | New: TTS library |
| **P0** | Background music mixing | High | Low | New: music files + FFmpeg audio filters |
| **P1** | Text outline + fade-in | Medium | Very low | None (FFmpeg params) |
| **P1** | Progress bar | Medium | Low | None (FFmpeg drawbox) |
| **P1** | Safe zone text positioning | Medium | Very low | None (y-offset change) |
| **P2** | Better transitions (varied) | Low-Medium | Very low | None (string change) |
| **P2** | Stock footage backgrounds | High | Medium | New: Pexels API or bundled clips |
| **P3** | Word-by-word captions | High | High | Depends on TTS timing data |
| **P3** | Split-screen format | High | Medium | Depends on background footage |
| **P4** | AI image backgrounds | Medium | Medium | New: image generation API |
| **P4** | Active word highlight | Medium | High | Depends on word-by-word system |

---

## Cost Estimates (Per Video)

| Component | Service | Cost |
|---|---|---|
| Script generation | Claude Haiku | ~$0.003 |
| TTS voiceover (OpenAI) | tts-1 | ~$0.002 |
| TTS voiceover (Edge TTS) | Free | $0.00 |
| Background music | Bundled royalty-free | $0.00 |
| Stock footage (Pexels) | Free tier | $0.00 |
| AI images (if used) | Varies | ~$0.01-0.05 |
| **Total per video** | | **~$0.005 - $0.06** |

---

## What Competitors Do (Tools to Match)

CapCut, Zebracat, AutoShorts.ai, and FacelessClip all provide:
1. Auto-captions with word-by-word color highlighting
2. Stock footage or AI image sourcing per scene
3. TTS voiceover with natural-sounding voices
4. Background music ducked under voiceover
5. Multiple visual style presets
6. 9:16 vertical format with safe zones

Our pipeline already handles script generation better than most of these (real trend data → Claude-generated scripts). The gap is entirely in the rendering stage.

---

## Summary

The single sentence version: **Add TTS voiceover + background music + text animations, and our videos go from "PowerPoint slides" to "competitive faceless TikTok content."**

The rendering pipeline needs to evolve from "text on colored rectangles" to "narrated, animated captions over visual backgrounds with music." All of this is achievable with FFmpeg + one TTS API. No new video editing tools needed.
