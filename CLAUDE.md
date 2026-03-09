# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated pipeline: scrape TikTok trends (Apify) → generate scripts (Claude API) → render videos (FFmpeg). Three-phase build, all phases complete.

## Setup & Running

```bash
# Activate virtualenv (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
copy .env.example .env   # then edit .env
```

Run any module standalone for testing:
```bash
python -m src.utils.config             # verify config + API key status
python -m src.utils.data_io            # test JSON save/load
python -m src.scrapers.trend_scraper   # scrape trending videos + extract hooks
python -m src.scrapers.ads_scraper     # scrape TikTok Ads Library
python -m src.scrapers.hashtag_tracker # scrape hashtag stats
python -m src.renderers.video_builder  # render videos from latest scripts
```

**External dependency:** FFmpeg must be installed and on PATH:
```bash
winget install --id Gyan.FFmpeg -e   # then restart terminal
```

## Architecture

**Three-phase pipeline**, each phase feeds the next:

1. **Scrapers** (`src/scrapers/`) — Apify actors pull TikTok data → save to `data/raw/`
2. **Generators** (`src/generators/`) — Claude API turns extracted hooks into scripts → save to `data/scripts/`
3. **Renderers** (`src/renderers/`) — FFmpeg assembles scripts into 9:16 videos → save to `output/videos/`

**Data flow uses timestamped JSON files** (not a database). `data_io.save_json()` writes files like `trending_videos_2026-03-08_143022.json`; `load_latest()` grabs the newest file by prefix. This means modules are decoupled — scrapers write files, generators read them.

**Config** (`src/utils/config.py`) loads `.env` at import time and exposes `APIFY_API_TOKEN`, `ANTHROPIC_API_KEY`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, and `Path` constants for all data directories. Any module importing from config gets auto-configured.

## Scraper Details (Phase 1 — Complete)

Each scraper follows the same pattern: `ApifyClient` → `actor.call()` → `iterate_items()` → save via `data_io`.

- **`trend_scraper.py`** — Actor: `apify/tiktok-scraper`. Scrapes organic trending videos, then `extract_hooks()` pulls the opening line (first sentence <150 chars or first 100 chars) from each video's description. Outputs: `data/raw/trending_videos_*.json`
- **`ads_scraper.py`** — Actor: `data_xplorer/tiktok-ads-library-fast`. Scrapes paid ad creatives, then `analyze_ad_hooks()` extracts both the hook and CTA (call-to-action). Outputs: `data/raw/ads_*.json`
- **`hashtag_tracker.py`** — Actor: `clockworks/tiktok-hashtag-scraper`. Two modes: `scrape_hashtags()` for specific hashtags, `find_trending_hashtags()` for discovery (sorted by view count). Outputs: `data/raw/hashtags_*.json`

Hook extraction handles multiple Apify field naming conventions (e.g., `playCount`/`plays`, `authorMeta`/`author`).

## Key Conventions

- All modules use `python -m src.module.name` execution (not direct file paths) due to relative imports from `src.utils`
- Dependencies in `requirements.txt` are grouped by phase
- Rich library is used for all terminal output (tables, colored status messages)
- Each Apify scraper has a hardcoded actor ID constant at module top (e.g., `TIKTOK_SCRAPER_ACTOR`)

## Testing

Interactive test runner (menu-driven, no commands to remember):
```bash
python run_tests.py
```

Or run pytest directly:
```bash
pytest                # all unit tests (no API key needed)
pytest -m integration # integration tests (needs ANTHROPIC_API_KEY)
pytest -m ""          # everything
```

Test structure:
- `tests/conftest.py` — shared fixtures, rich CLI banner/summary, auto-skip integration tests without API key
- `tests/test_templates.py` — prompt building (`build_user_prompt`) and constants
- `tests/test_parse_scripts.py` — JSON parsing, source types, edge cases, duration calc
- `tests/test_data_io.py` — save/load round-trips using `tmp_path`
- `tests/test_video_builder.py` — text wrapping, escaping, timing calc, FFmpeg rendering
- `tests/test_integration.py` — live API calls, auto-skipped without `ANTHROPIC_API_KEY`

**Convention:** Update `run_tests.py` menu and add test files as each new phase is built.

## Current Status

- **Phase 1 (Complete):** All utils and scrapers fully implemented
  - `utils/config.py` — env loading, path constants, API key checks
  - `utils/data_io.py` — timestamped JSON save/load/list/load_latest
  - `scrapers/trend_scraper.py` — trending videos + hook extraction + rich table display
  - `scrapers/ads_scraper.py` — ad creatives + hook/CTA extraction
  - `scrapers/hashtag_tracker.py` — hashtag stats + trending discovery
- **Phase 2 (Complete):** `generators/script_generator.py`, `generators/templates.py` — Claude API turns scraped hooks into new scripts (tested)
- **Phase 3 (Complete):** `renderers/video_builder.py` — FFmpeg renders 9:16 videos (dark bg + white text, 3 sections: hook/body/CTA). Requires FFmpeg on PATH + `assets/fonts/Inter-Bold.ttf`
- **Phase 4 (Not Started):** `publishers/tiktok_publisher.py` — TikTok Content Posting API integration. See `docs/TIKTOK_API_COMPLIANCE.md` for full rules. Must implement OAuth flow, creator_info queries, and compliant UX (user consent, privacy dropdown, interaction toggles) to pass TikTok's audit.
