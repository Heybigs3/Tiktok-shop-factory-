# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product Vision

**TikTok Factory** is an autonomous content engine for TikTok Shop affiliate marketing. The system scrapes trending product data, analyzes what's working, generates videos that replicate winning patterns, and queues them for a VA to post. The system makes ALL decisions — niche selection, product picks, video style, music, timing. The VA just executes.

**Brand:** dailyfindsnyc — just a name, carries NO niche meaning. The data decides what we sell.

**Business model:** TikTok Shop affiliate. Promote other people's products, earn commission (~13% avg US).

**Target markets:** US + UK.

**Budget:** $100-200/month for APIs during build phase.

### The Daily Loop (target state — not yet fully built)

```
INTELLIGENCE → Scan all TikTok Shop categories. What's trending today?
ANALYSIS     → Download top videos. Extract hook style, visuals, pacing, music.
GENERATION   → Pick products. Generate videos matching analyzed patterns.
DASHBOARD    → 5 ready-to-post videos with full instructions for VA.
FEEDBACK     → Scrape our own performance. Learn what works. Repeat.
```

### What exists vs what's planned

| Component | Status | Notes |
|-----------|--------|-------|
| Apify scrapers | Built | trend_scraper, ads_scraper, hashtag_tracker |
| Kalodata scraper | Built | Playwright-based, single category — needs all-category scanning |
| Hook processor | Built | Normalizes raw Apify data into consistent schema |
| Niche Radar | Built | Scans 10 niches, scores on 4 signals, recommends top 3 accounts |
| Script generator | Built | Standard + product modes. Needs Trend Profile input |
| Video renderer | Built | Graphics-based — needs UGC-style formats (HeyGen) |
| TTS narration | Built | ElevenLabs, mood-based voices |
| Video analyzer | Built | Frames + transcripts + Claude analysis + Style Bible + comparison |
| Dashboard | Built | Needs VA posting cards with data-backed instructions |
| Multi-account | Built | CRUD, path aliasing, per-account config |
| Publisher (TikTok API) | Built | Dormant until app approved. VA posts manually. |
| **Trend Profiler** | **Not built** | Turn analyzed videos into generation instructions |
| **Dynamic music** | **Not built** | AI-generated per-video music (replace hardcoded files) |
| **Performance tracker** | **Not built** | Scrape our own metrics, correlate with style |
| **Feedback engine** | **Not built** | Self-learning loop |
| **HeyGen integration** | **Not built** | AI avatars for realistic UGC ($24/mo) |

### Known architectural problem: no per-niche data isolation

The pipeline currently shares a single `data/raw/`, `data/processed/`, and `data/scripts/` directory. When running the pipeline for multiple niches sequentially, data bleeds between runs — the script generator picks up hooks and products from the previous niche. The multi-account system (`src/dashboard/accounts.py`) provides per-account directory trees and configs, but the pipeline modules don't yet read from account-scoped paths. This is the highest-priority architectural fix.

## Setup & Running

```bash
venv\Scripts\activate                # Windows virtualenv
pip install -r requirements.txt
copy .env.example .env               # then edit .env with API keys
```

**External dependencies:**
```bash
winget install --id Gyan.FFmpeg -e                    # FFmpeg — restart terminal after
pip install playwright && playwright install chromium  # only for Kalodata scraping
pip install yt-dlp                                    # only for auto-downloading top videos
```

**Run the full pipeline or individual phases:**
```bash
python run_pipeline.py               # menu-driven orchestrator (recommended, 14 options)
```

**Run any module standalone:**
```bash
python -m src.utils.config            # verify config + API key status
python -m src.scrapers.trend_scraper  # scrape trending videos
python -m src.scrapers.ads_scraper    # scrape TikTok Ads Library
python -m src.scrapers.hashtag_tracker  # scrape hashtag stats
python -m src.scrapers.kalodata_scraper # scrape products from Kalodata
python -m src.scrapers.niche_radar    # scan & score niches (menu-driven)
python -m src.generators.script_generator  # generate scripts from hooks
python -m src.renderers.video_builder     # render videos from scripts
python -m src.renderers.image_generator   # generate scene images (Gemini)
python -m src.renderers.video_generator   # generate video clips (Muapi)
python -m src.publishers.tiktok_publisher # interactive TikTok publish
python -m src.analyzers                   # video analysis pipeline (menu-driven)
python -m src.dashboard                   # web dashboard on localhost:8420
```

All modules **must** be run with `python -m src.module.name` (not direct file paths) due to relative imports from `src.utils`.

## Architecture

### Pipeline phases

1. **Scrapers** (`src/scrapers/`) — Apify actors pull TikTok data → `data/raw/`
2. **Generators** (`src/generators/`) — Claude API turns hooks into scripts → `data/scripts/`
3. **Renderers** (`src/renderers/`) — FFmpeg assembles 9:16 videos → `output/videos/`
4. **Publishers** (`src/publishers/`) — Interactive CLI uploads to TikTok (needs app approval)

**Plus:**
- **Niche Radar** (`src/scrapers/niche_radar.py`) — Intelligence layer that scores niches and recommends accounts
- **Analyzers** (`src/analyzers/`) — Video analysis pipeline (frames, transcripts, Style Bible, comparison)
- **Dashboard** (`src/dashboard/`) — FastAPI + Jinja2 + HTMX + Tailwind CSS on port 8420. Multi-account with sidebar nav.

### Data flow

Modules are decoupled via **timestamped JSON files** (no database). `data_io.save_json()` writes files like `trending_videos_2026-03-08_143022.json`; `load_latest()` grabs the newest file by prefix.

```
Niche Radar   → data/raw/niche_radar_*.json (scored niches + recommendations)
       ↓
Apify Scrapers → data/raw/*.json (trending_videos, hashtags, ads, products)
       ↓
Hook Processor → data/processed/*.json (enriched, deduped, filtered)
       ↓
Claude API     → data/scripts/*.json (hook/body/CTA scripts with visual_hints)
       ↓
FFmpeg + TTS   → output/videos/*.mp4 (narrated 9:16 vertical videos)
```

### Config system

- **`src/utils/config.py`** — loads `.env` at import time, exposes all API keys and `Path` constants (`DATA_RAW_DIR`, `DATA_PROCESSED_DIR`, `DATA_SCRIPTS_DIR`, etc.). Any module importing from config gets auto-configured. Also provides `load_pipeline_config()`.
- **`pipeline_config.json`** — centralizes niche settings (search queries, ad keywords, hashtags, TTS voices, video style, product sources, analyzer settings). Can be generated per-account by `niche_radar.build_niche_config()`.

### Scraper pattern

All Apify scrapers follow the same pattern: `ApifyClient` → `actor.call()` → `iterate_items()` → save via `data_io`. Each has a hardcoded actor ID constant at module top. All read search terms from `pipeline_config.json`.

- `trend_scraper.py` — Actor: `clockworks/tiktok-scraper`. Hook extraction handles multiple Apify field naming conventions (`playCount`/`plays`, `authorMeta`/`author`). **Also returns `musicMeta`** (musicName, musicAuthor, musicId, playUrl) — not yet utilized.
- `ads_scraper.py` — Actor: `data_xplorer/tiktok-ads-library-fast`. Extracts hook + CTA from ad creatives.
- `hashtag_tracker.py` — Actor: `clockworks/tiktok-hashtag-scraper`. Two modes: specific hashtags + trending discovery.
- `kalodata_scraper.py` — **Playwright** (not Apify). Browser automation for product rankings. Requires `KALODATA_EMAIL`/`KALODATA_PASSWORD`.

### Niche Radar (`src/scrapers/niche_radar.py`)

Scans 10 predefined niches (skincare, haircare, supplements, kitchen_gadgets, fitness_gear, pet_products, phone_accessories, cleaning, baby_products, fashion_accessories) and scores each on 4 signals:

- **engagement_score** (35%) — median engagement rate of top videos
- **velocity_score** (25%) — recency-weighted engagement (recent virals score higher)
- **gap_score** (20%) — demand/supply gap (high Kalodata demand, low creator saturation)
- **momentum_score** (20%) — week-over-week hashtag view growth

`recommend_accounts()` enforces category diversity — no two recommended niches from the same `kalodata_cat`. `build_niche_config()` generates a complete `pipeline_config.json` for each niche. `setup_accounts()` creates dashboard accounts with per-account configs.

### Generator modes

- **Standard mode** (default): `build_user_prompt()` constructs prompts from scraped hooks + hashtags. Scripts include `visual_hints` (mood, overlay text, background style) and `suggested_hashtags`.
- **Product mode**: When `video_style` in config is `product_showcase`, `ugc_showcase`, or `comparison`, uses `PRODUCT_SYSTEM_PROMPT` + `build_product_prompt()` for TikTok Shop scripts. **Product mode overrides niche hooks with product data** — if only one product exists in `data/raw/products_*.json`, all scripts will be about that product regardless of niche config.

### Renderer details

- **video_builder.py** — 5 color themes (warm/cool/energetic/calm/default), mood-based color grading (FFmpeg `eq` filter), text fade-in animations, mood-based xfade transitions (dissolve/wiperight/slideright/fade), vignette overlay, text outline/stroke for readability. Requires `assets/fonts/Inter-Bold.ttf`.
- **tts.py** — ElevenLabs REST API (no SDK — Windows path length issues). Mood→voice mapping from config. Audio drives video section timing. Enable via `tts.enabled: true` + `ELEVENLABS_API_KEY`.
- **Background music** — 4 royalty-free tracks from `assets/music/` (calm, warm, energetic, cool), mixed at configurable volume.
- **Product videos**: `render_product_video()` composites product media + text overlays. Ken Burns with variable speed (mood-based), or Muapi clips (premium). TikTok safe zones: top 150px, bottom 480px, right 80px kept clear. Style router in `render_all()` auto-dispatches product scripts.
- **image_generator.py** — Gemini API for styled scene images. Falls back to original product images.
- **video_generator.py** — Muapi SDK for animated clips. Async submit/poll/download. Falls back to static images.

### Video Analysis Pipeline (`src/analyzers/`)

Extracts frames + transcripts from TikTok videos, analyzes via Claude's multimodal API, and synthesizes a **Style Bible** that feeds the script generator.

- **frame_extractor.py** — FFmpeg-based frame extraction. Even spacing or scene-change detection (`select='gt(scene,0.3)'`).
- **transcriber.py** — Whisper CLI subprocess (NOT Python import — avoids 2GB torch dependency). Falls back gracefully if not installed.
- **video_analysis.py** — Per-video multimodal analysis via Claude API. Uses `claude-haiku-4-5-20251001` (~$0.01/video).
- **style_bible.py** — Aggregates analyses, synthesizes via `claude-sonnet-4-20250514`. Outputs to `data/style_bibles/`.
- **comparison.py** — Cross-video comparison analysis.
- **style_overrides.py** — Style override system.
- **video_downloader.py** — Download top videos for analysis (requires yt-dlp).

### Multi-account system (`src/dashboard/accounts.py`)

Each account gets isolated directory trees under `data/accounts/{id}/` (raw, processed, scripts, output). The "default" account maps to existing global paths for backward compatibility. Per-account `pipeline_config.json` stored via `save_account_config()`. **The pipeline modules don't yet use account-scoped paths** — this is the gap that causes data bleed between niches.

### Publisher (Phase 4)

OAuth 2.0 flow, creator_info queries, compliant UX. See `docs/TIKTOK_API_COMPLIANCE.md`. **Cannot be used until TikTok developer app is approved.** VA publishes manually via dashboard until then.

### Dashboard (`src/dashboard/`)

FastAPI + Jinja2 + HTMX + Tailwind CSS on port 8420. Services split across: `app.py` (routes), `accounts.py` (CRUD), `services.py` (utilities), `product_service.py`, `publish_service.py`, `queue_service.py`, `analyzer_service.py`.

## Key Conventions

- Rich library for all terminal output (tables, colored status)
- Dependencies in `requirements.txt` grouped by phase, all pinned with `==`
- `hook_processor.py` normalizes raw Apify data into a consistent schema — generators load from `data/processed/` first, fall back to `data/raw/`
- Everything must be data-driven. No hardcoded niche assumptions.

## Testing

```bash
python run_tests.py                    # interactive menu (recommended)
pytest                                 # all unit tests (no API keys needed)
pytest tests/test_templates.py         # single test file
pytest tests/test_templates.py::test_name  # single test function
pytest -m integration                  # live API tests (needs ANTHROPIC_API_KEY)
pytest -m ""                           # everything including integration
```

**560 tests** across 29 test files, all passing.

**Pytest markers** (auto-skipped when requirements missing — see `conftest.py`):
- `@pytest.mark.integration` — needs `ANTHROPIC_API_KEY`
- `@pytest.mark.ffmpeg` — needs FFmpeg on PATH
- `@pytest.mark.tiktok` — needs `TIKTOK_CLIENT_KEY`
- `@pytest.mark.kalodata` — needs `KALODATA_EMAIL`/`KALODATA_PASSWORD`
- `@pytest.mark.whisper` — needs Whisper CLI installed

**Shared fixtures** in `conftest.py`: `sample_trending_hooks`, `sample_ad_hooks`, `sample_claude_response`, `sample_script`, `sample_raw_apify_videos`, `sample_hashtags`, `sample_creator_info`, `tmp_data_dir`.

**Convention:** When adding a new module, add its tests and update the `run_tests.py` menu. Test files follow `tests/test_<module>.py` naming. `test_dashboard.py` requires `fastapi` installed to collect.
