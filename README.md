# TikTok Content Factory

Automated pipeline that scrapes TikTok trends, generates scripts from winning hooks, and batch renders TikTok-format videos.

## Setup

```bash
# 1. Clone and enter the project
cd tiktok-factory

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up API keys
copy .env.example .env
# Edit .env and add your Apify + Anthropic keys
```

## Usage

Run any module standalone:

```bash
# Verify config and API keys
python -m src.utils.config

# Scrape trending videos and extract hooks
python -m src.scrapers.trend_scraper

# Scrape high-spend ad creatives
python -m src.scrapers.ads_scraper

# Track hashtag volume and discover trending tags
python -m src.scrapers.hashtag_tracker
```

Scraped data saves to `data/raw/` as timestamped JSON files (e.g., `trending_videos_2026-03-09_143022.json`). Each run creates a new file so previous scrapes are never overwritten.

## Project Structure

```
src/
├── scrapers/         # Phase 1 — Apify-powered TikTok data collection
│   ├── trend_scraper.py     # Trending videos + hook extraction
│   ├── ads_scraper.py       # Ads Library + hook/CTA extraction
│   └── hashtag_tracker.py   # Hashtag stats + trend discovery
├── generators/       # Phase 2 — Script generation
│   ├── script_generator.py  # Claude API script gen
│   └── templates.py         # Script format templates
├── renderers/        # Phase 3 — Video rendering
│   └── video_builder.py     # FFmpeg orchestration
└── utils/            # Shared helpers
    ├── config.py            # Environment + path constants
    └── data_io.py           # Timestamped JSON save/load
```

## How It Works

**Data flows through timestamped JSON files** — no database needed. Each phase writes files, the next phase reads the latest one via `load_latest()`. Modules stay decoupled.

### Phase 1: Trend Scraping (Complete)

Three Apify-powered scrapers collect different types of TikTok data:

| Scraper | Apify Actor | What it collects | Why it matters |
|---------|-------------|------------------|----------------|
| `trend_scraper` | `apify/tiktok-scraper` | Viral videos + opening hooks | Shows what grabs attention organically |
| `ads_scraper` | `data_xplorer/tiktok-ads-library-fast` | Paid ad creatives + CTAs | Ads spending real money = proven hooks |
| `hashtag_tracker` | `clockworks/tiktok-hashtag-scraper` | Hashtag volume + momentum | Identifies trends + tags for content |

Each scraper extracts **hooks** — the opening line that grabs viewers in the first 3 seconds (first sentence under 150 chars, or first 100 chars as fallback).

### Phase 2: Script Generation (Up Next)

Claude API will read scraped hooks and generate new video scripts with hook/body/CTA structure.

### Phase 3: Video Rendering

FFmpeg will assemble generated scripts into 9:16 TikTok-format videos.

### Phase 4: Analytics

Track CPA, pause underperformers, optimize the pipeline.
