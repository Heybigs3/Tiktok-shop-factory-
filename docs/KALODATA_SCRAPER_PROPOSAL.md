# Product Video Pipeline — Proposal

## The Problem

Our pipeline currently scrapes trending **videos**, **ads**, and **hashtags** — but it doesn't know which **products** are actually selling on TikTok Shop. We're making content based on what's going viral, but we have no data on what's making money. And our videos use solid-color backgrounds instead of real product visuals.

## The Solution (Two Parts)

### Part 1: Kalodata Product Scraper
Build a Python script that automatically pulls top-performing product data from Kalodata — the same data you'd see by browsing their website, just collected by a script instead of by hand. This avoids the $200+/month Kalodata API fee by automating a regular browser session using your existing Kalodata account.

### Part 2: Google Veo Video Clips (Replaces Higgsfield)
Use Google's **Veo** video generation model to turn product images into short animated video clips. Veo is accessed through the **same Gemini API key we already use for image generation** — no new account, no new signup. This replaces Higgsfield, which **does not have a public API**.

---

## Part 1: Kalodata Scraper

### What We'd Collect

| Data Point | Why It Matters |
|------------|---------------|
| Product name | Know exactly what to feature in videos |
| Product image(s) | Use real product visuals instead of solid-color backgrounds |
| Revenue / sales volume | Prioritize products that are actually converting |
| Product category | Stay within our niche (e.g., skincare, fitness) |
| Top-performing video links | Study what's already working for that product |
| Price point | Tailor scripts to the product's market position |
| Trend direction (rising/falling) | Avoid products that have already peaked |

### How It Works (Non-Technical Summary)

1. The script opens a browser window automatically (you won't see it — it runs in the background)
2. It logs into Kalodata using your account credentials
3. It navigates to the top products page and reads the data off the screen — the same way you would
4. It downloads product images into a local folder
5. It saves everything as a structured data file that the rest of our pipeline can read

The whole process takes roughly 30–60 seconds per run.

### Cost

| Item | Cost |
|------|------|
| Kalodata API (what we're avoiding) | $200+/month |
| Kalodata basic account (what we'd use) | Cheapest tier that shows product rankings |
| Playwright (Python library) | Free |

### Risks

- **Site redesigns** — If Kalodata changes their page layout, the script needs updating. Normal maintenance, ~15–30 min fix.
- **Anti-bot measures** — Playwright uses a real browser, so detection is unlikely but possible.
- **Login session expiry** — The script handles re-login automatically.

These are manageable. We're automating our own account access on a service we're paying for.

---

## Part 2: Google Veo — Animated Product Clips

### Why Not Higgsfield?

**Higgsfield does not have a public API.** No endpoints, no SDK, no programmatic access. It's a UI-only web tool. We confirmed this through research — it's not coming soon, it simply doesn't exist.

### Why Veo?

Google's Veo is a video generation model available through the **Gemini API** — the same API we already use for image generation. One API key, one account, one SDK.

| Feature | What It Means |
|---------|---------------|
| **Image-to-video** | Feed it a product image, get back an animated clip |
| **9:16 aspect ratio** | Native vertical TikTok format — no cropping needed |
| **Text prompts** | Describe the motion you want ("slow zoom on product, soft lighting") |
| **Reference images** | Use up to 3 images to guide the style (Veo 3.1) |
| **8-second clips** | Perfect length for TikTok product sections |
| **Same API key** | Uses `GOOGLE_AI_API_KEY` — already in our `.env` |

### How It Works

```
1. Gemini generates a styled product scene image (already built)
2. Veo takes that image + a motion prompt → generates a video clip
3. FFmpeg composites the clip with text overlays → final TikTok video
```

The code submits a request, waits for it to finish (11 seconds to 6 minutes), then downloads the clip. Same submit-and-poll pattern used by many APIs.

### Python Example (What the Code Would Look Like)

```python
from google import genai

client = genai.Client(api_key="YOUR_GOOGLE_AI_API_KEY")

# Turn a product image into a video clip
operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt="Slow cinematic zoom on skincare product, soft warm lighting, clean background",
    image=product_scene_image,
    config={
        "aspect_ratio": "9:16",       # vertical TikTok format
        "duration": "8s",             # 8-second clip
        "resolution": "720p",         # fast + cheap
    }
)

# Wait for it to finish
while not operation.done:
    time.sleep(10)
    operation = client.operations.get(operation)

# Save the clip
video = operation.response.generated_videos[0]
video.video.save("product_clip.mp4")
```

### Veo Pricing

| Model | Speed | Cost per Second | 5-sec Clip | 8-sec Clip |
|-------|-------|-----------------|------------|------------|
| **Veo 3.1 Fast** | Fastest | $0.15 | $0.75 | $1.20 |
| **Veo 3.1 Standard** | Best quality | $0.40 | $2.00 | $3.20 |
| **Veo 2** | Good quality | $0.35 | $1.75 | $2.80 |

**Recommendation:** Use **Veo 3.1 Fast** at $0.15/sec. An 8-second product clip costs $1.20. If we generate 5 product videos per pipeline run, that's about **$6 per batch** — far cheaper than any monthly subscription.

### Fallback Behavior

If the Veo call fails or the API key isn't on a paid tier, the pipeline falls back to using **static product images** (from Gemini) as video backgrounds. Everything still works — you just don't get the animated motion.

---

## Full Pipeline With Both Parts

```
CURRENT PIPELINE:
  Trend Scraper ──→ trending videos
  Ads Scraper   ──→ ad creatives
  Hashtag Tracker → hashtag stats
        ↓
  Script Generator → Video Renderer (solid backgrounds) → Publisher

UPGRADED PIPELINE:
  Trend Scraper ────→ trending videos
  Ads Scraper   ────→ ad creatives
  Hashtag Tracker ──→ hashtag stats
  Kalodata Scraper → top-selling products + images       ← NEW
        ↓
  Script Generator → writes scripts about real products   ← UPGRADED
        ↓
  Gemini → styled product scene images                    ← EXISTING
        ↓
  Veo → animated product video clips (9:16)               ← NEW (replaces Higgsfield)
        ↓
  FFmpeg → composites clips + text overlays → final video ← EXISTING
        ↓
  Publisher → TikTok
```

## Total Cost Summary

| Component | Cost | Type |
|-----------|------|------|
| Kalodata account | ~$46/month (Starter) | Subscription |
| Google AI (Gemini images) | Free tier: 50/day | Free |
| Google AI (Veo clips) | ~$0.75–$1.20 per clip | Pay-per-use |
| Playwright | Free | Free |
| FFmpeg | Free | Free |
| **Total per batch (5 videos)** | **~$4–$6** | Per run |
| **Higgsfield (what we're NOT using)** | N/A — no API exists | Dead end |
| **Kalodata API (what we're avoiding)** | $200+/month | Saved |

## What Changes in the Codebase

| File | Change |
|------|--------|
| `video_generator.py` | Rewrite: Higgsfield SDK → Google Veo API |
| `config.py` | Remove `HIGGSFIELD_API_KEY`, Veo uses existing `GOOGLE_AI_API_KEY` |
| `pipeline_config.json` | Remove Higgsfield settings, add Veo model/speed preferences |
| `test_video_generator.py` | Update mocks from Higgsfield → Veo |
| `requirements.txt` | Remove `higgsfield` dependency (if any) |

## Recommendation

Build both parts. Kalodata gives us the **what** (which products to feature), and Veo gives us the **wow** (animated product clips instead of static images). Both integrate cleanly into the existing pipeline, and the total cost is under $50/month + a few dollars per batch — a fraction of the $200+/month Kalodata API alone.

## Next Steps (If Approved)

1. Confirm Kalodata plan and set up account credentials
2. Get `GOOGLE_AI_API_KEY` on a paid tier (for Veo access)
3. Install Playwright: `pip install playwright && playwright install chromium`
4. Rewrite `video_generator.py` from Higgsfield → Veo
5. Test product pipeline end-to-end
6. Update `run_pipeline.py` menu and dashboard
