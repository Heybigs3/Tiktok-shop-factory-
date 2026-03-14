# TikTok Factory

Autonomous content engine for TikTok Shop affiliate marketing. Scrapes trending product data across all categories, analyzes what's working, generates videos that replicate winning patterns, and queues them for a VA to post. The system makes all decisions — niche, product, style, music, timing.

## How It Works

```
INTELLIGENCE → Scrape trending products + top-performing videos across TikTok Shop
ANALYSIS     → Download winners, extract hook style, visuals, pacing, music patterns
GENERATION   → Pick affiliate products, generate matching videos (scripts + render)
DASHBOARD    → Ready-to-post videos with captions, hashtags, timing, product links
FEEDBACK     → Track our own performance, learn what works, adapt daily
```

**Target markets:** US + UK. **Business model:** TikTok Shop affiliate (~13% avg commission).

## Current Status

The core pipeline (scrape → generate → render → publish) is code-complete. The intelligence layer (dynamic niche selection, trend analysis, feedback loop) is next.

| Component | Status |
|-----------|--------|
| TikTok scrapers (Apify) | Built |
| Product scraper (Kalodata) | Built |
| Script generator (Claude API) | Built |
| Video renderer (FFmpeg) | Built |
| TTS narration (ElevenLabs) | Built |
| Video analyzer (multimodal) | Built |
| Dashboard (FastAPI + HTMX) | Built |
| Multi-account system | Built |
| TikTok publisher | Built (dormant until API approved) |
| **Niche Radar** | Planned |
| **Trend Profiler** | Planned |
| **AI music generation** | Planned |
| **Performance tracker** | Planned |
| **AI avatar videos (HeyGen)** | Planned |

## Quick Start

```bash
# 1. Clone and set up
cd tiktok-factory
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install FFmpeg (required for video rendering)
winget install --id Gyan.FFmpeg -e   # then restart terminal

# 4. Set up API keys
copy .env.example .env
# Edit .env and add your keys (see API Keys section below)

# 5. Run the pipeline
python run_pipeline.py
```

## API Keys

| Key | Required For | Get It At |
|-----|-------------|-----------|
| `APIFY_API_TOKEN` | Scraping (Phase 1) | [console.apify.com](https://console.apify.com/account/integrations) |
| `ANTHROPIC_API_KEY` | Script generation + analysis | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `ELEVENLABS_API_KEY` | TTS narration (optional) | [elevenlabs.io](https://elevenlabs.io/app/settings/api-keys) |
| `GOOGLE_AI_API_KEY` | Scene image generation | [aistudio.google.dev](https://aistudio.google.dev/app/apikey) |
| `KALODATA_EMAIL/PASSWORD` | Product scraping | [kalodata.com](https://www.kalodata.com) |
| `TIKTOK_CLIENT_KEY` | Publishing (Phase 4) | [developers.tiktok.com](https://developers.tiktok.com) |
| `TIKTOK_CLIENT_SECRET` | Publishing (Phase 4) | [developers.tiktok.com](https://developers.tiktok.com) |

## Usage

### Pipeline Runner (recommended)

```bash
python run_pipeline.py
```

Menu-driven interface with options:
1. **Full pipeline** — scrape → generate → render (one command)
2. **Scrape only** — pull fresh TikTok data
3. **Generate only** — create scripts from existing data
4. **Render only** — render videos from existing scripts
5. **Publish** — interactive TikTok upload flow
6. **Dashboard** — web UI on localhost:8420

### Run Modules Individually

```bash
python -m src.utils.config             # verify config + API key status
python -m src.scrapers.trend_scraper   # scrape trending videos + extract hooks
python -m src.scrapers.ads_scraper     # scrape TikTok Ads Library
python -m src.scrapers.hashtag_tracker # scrape hashtag stats
python -m src.scrapers.kalodata_scraper # scrape product rankings
python -m src.generators.script_generator  # generate scripts from hooks
python -m src.renderers.video_builder      # render videos from scripts
python -m src.renderers.image_generator    # generate scene images (Gemini)
python -m src.renderers.video_generator    # generate video clips (Muapi)
python -m src.publishers.tiktok_publisher  # interactive TikTok publish
python -m src.analyzers                    # video analysis pipeline
python -m src.dashboard                    # web dashboard on localhost:8420
```

### Dashboard

Web UI on `localhost:8420`:
- **Videos** — ready-to-post cards with video preview, caption, hashtags, post history
- **Products** — product pipeline status (scraped → scripted → rendered)
- **Settings** — pipeline runner, config editor, API key status, analysis tools, account management

Multi-account support with sidebar navigation.

### Data Flow

**Timestamped JSON files** — no database. Each phase writes files, the next reads the latest.

```
Apify Scrapers → data/raw/*.json
       ↓
Hook Processor → data/processed/*.json (enriched, deduped, filtered)
       ↓
Claude API     → data/scripts/*.json (hook/body/CTA scripts)
       ↓
FFmpeg + TTS   → output/videos/*.mp4 (narrated 9:16 videos)
       ↓
Dashboard      → VA downloads + posts manually to TikTok
```

## Project Structure

```
tiktok-factory/
├── run_pipeline.py          # Pipeline orchestrator (menu-driven)
├── run_tests.py             # Test runner (menu-driven)
├── pipeline_config.json     # Niche config (will become auto-generated)
├── requirements.txt         # Pinned dependencies
├── src/
│   ├── scrapers/
│   │   ├── trend_scraper.py     # Trending videos + hook extraction
│   │   ├── ads_scraper.py       # Ads Library + hook/CTA extraction
│   │   ├── hashtag_tracker.py   # Hashtag stats + trend discovery
│   │   ├── kalodata_scraper.py  # Product rankings (Playwright)
│   │   └── hook_processor.py    # Enrich, dedup, filter raw hooks
│   ├── generators/
│   │   ├── script_generator.py  # Claude API script generation
│   │   └── templates.py         # System prompt + prompt builder
│   ├── renderers/
│   │   ├── video_builder.py     # FFmpeg video rendering + effects
│   │   ├── tts.py               # ElevenLabs TTS narration
│   │   ├── image_generator.py   # Gemini scene images
│   │   └── video_generator.py   # Muapi animated clips
│   ├── analyzers/
│   │   ├── frame_extractor.py   # FFmpeg frame extraction
│   │   ├── transcriber.py       # Whisper transcription
│   │   ├── video_analysis.py    # Claude multimodal analysis
│   │   ├── style_bible.py       # Cross-video style synthesis
│   │   └── prompts.py           # Analysis prompt templates
│   ├── publishers/
│   │   ├── tiktok_publisher.py  # Interactive publish CLI
│   │   ├── tiktok_api.py        # TikTok Content Posting API client
│   │   └── oauth_server.py      # OAuth 2.0 login flow
│   ├── dashboard/               # FastAPI + Jinja2 + HTMX + Tailwind
│   └── utils/
│       ├── config.py            # Environment + path constants
│       └── data_io.py           # Timestamped JSON save/load
├── data/
│   ├── raw/                     # Raw Apify scraper output
│   ├── processed/               # Enriched hooks (from hook_processor)
│   ├── scripts/                 # Generated scripts
│   └── style_bibles/            # Video analysis synthesis
├── output/
│   ├── videos/                  # Rendered MP4 files
│   ├── images/                  # Generated scene images
│   └── clips/                   # Muapi video clips
├── assets/
│   ├── fonts/                   # Inter-Bold.ttf
│   └── music/                   # Background music tracks
└── tests/                       # 515 pytest tests across 24 files
```

## Testing

```bash
python run_tests.py    # interactive menu (recommended)
# or
pytest                 # all unit tests
pytest -m integration  # live API tests (needs ANTHROPIC_API_KEY)
```

515 tests covering all modules. No API keys needed for unit tests.
