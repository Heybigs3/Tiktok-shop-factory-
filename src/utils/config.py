"""
config.py — Loads environment variables and exposes project settings.

How it works:
  1. Reads .env file from the project root using python-dotenv
  2. Exposes API keys and paths as simple variables
  3. Any module can: from src.utils.config import APIFY_API_TOKEN

Why .env?
  API keys should NEVER be hardcoded in source files. The .env file is
  gitignored, so keys stay on your machine and never hit GitHub.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Fix Windows terminal encoding for emoji support ──
# TikTok captions are full of emojis — Rich crashes on Windows cp1252 without this.
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── Locate project root (two levels up from this file: utils/ → src/ → root) ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Load .env file into os.environ ──
# override=False means existing env vars (e.g., from your shell) take priority
load_dotenv(PROJECT_ROOT / ".env", override=False)

# ── API Keys ──
APIFY_API_TOKEN: str = os.getenv("APIFY_API_TOKEN", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
TIKTOK_CLIENT_KEY: str = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET: str = os.getenv("TIKTOK_CLIENT_SECRET", "")
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
GOOGLE_AI_API_KEY: str = os.getenv("GOOGLE_AI_API_KEY", "")
MUAPI_API_KEY: str = os.getenv("MUAPI_API_KEY", "")
HEYGEN_API_KEY: str = os.getenv("HEYGEN_API_KEY", "")
KALODATA_EMAIL: str = os.getenv("KALODATA_EMAIL", "")
KALODATA_PASSWORD: str = os.getenv("KALODATA_PASSWORD", "")

# ── Data directories ──
DATA_RAW_DIR: Path = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR: Path = PROJECT_ROOT / "data" / "processed"
DATA_SCRIPTS_DIR: Path = PROJECT_ROOT / "data" / "scripts"
DATA_TOKENS_DIR: Path = PROJECT_ROOT / "data" / "tokens"
DATA_ACCOUNTS_DIR: Path = PROJECT_ROOT / "data" / "accounts"
ACCOUNTS_FILE: Path = PROJECT_ROOT / "data" / "accounts.json"
OUTPUT_DIR: Path = PROJECT_ROOT / "output" / "videos"
OUTPUT_IMAGES_DIR: Path = PROJECT_ROOT / "output" / "images"
OUTPUT_CLIPS_DIR: Path = PROJECT_ROOT / "output" / "clips"
OUTPUT_SCREENSHOTS_DIR: Path = PROJECT_ROOT / "output" / "screenshots"

# ── Analyzer directories ──
DATA_FRAMES_DIR: Path = PROJECT_ROOT / "data" / "frames"
DATA_TRANSCRIPTS_DIR: Path = PROJECT_ROOT / "data" / "transcripts"
DATA_ANALYSIS_DIR: Path = PROJECT_ROOT / "data" / "analysis"
DATA_STYLE_BIBLES_DIR: Path = PROJECT_ROOT / "data" / "style_bibles"
VIDEOS_DIR: Path = PROJECT_ROOT / "videos"

# ── Asset paths ──
ASSETS_DIR: Path = PROJECT_ROOT / "assets"
FONT_PATH: Path = ASSETS_DIR / "fonts" / "Inter-Bold.ttf"
MUSIC_DIR: Path = ASSETS_DIR / "music"
PRODUCT_IMAGES_DIR: Path = ASSETS_DIR / "product_images"

# ── Ensure data dirs exist (creates them if missing) ──
for _dir in [DATA_RAW_DIR, DATA_PROCESSED_DIR, DATA_SCRIPTS_DIR, DATA_TOKENS_DIR,
             DATA_ACCOUNTS_DIR, OUTPUT_DIR, OUTPUT_IMAGES_DIR, OUTPUT_CLIPS_DIR,
             OUTPUT_SCREENSHOTS_DIR, PRODUCT_IMAGES_DIR,
             DATA_FRAMES_DIR, DATA_TRANSCRIPTS_DIR, DATA_ANALYSIS_DIR,
             DATA_STYLE_BIBLES_DIR, VIDEOS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)


# ── Pipeline config (niche, search terms, limits) ──
PIPELINE_CONFIG_PATH: Path = PROJECT_ROOT / "pipeline_config.json"

# Default config used when pipeline_config.json is missing
_DEFAULT_PIPELINE_CONFIG = {
    "niche": "skincare",
    "search_queries": ["skincare routine"],
    "ad_keywords": ["skincare"],
    "hashtags": ["skincare", "glowup", "beautytok"],
    "max_results_per_query": 10,
    "num_scripts": 5,
}


def load_pipeline_config() -> dict:
    """Load pipeline_config.json from project root. Returns defaults if missing."""
    if PIPELINE_CONFIG_PATH.exists():
        with open(PIPELINE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return _DEFAULT_PIPELINE_CONFIG.copy()


def check_api_keys() -> dict[str, bool]:
    """Check which API keys are configured. Returns dict of key_name: is_set."""
    return {
        "APIFY_API_TOKEN": bool(APIFY_API_TOKEN),
        "ANTHROPIC_API_KEY": bool(ANTHROPIC_API_KEY),
        "TIKTOK_CLIENT_KEY": bool(TIKTOK_CLIENT_KEY),
        "TIKTOK_CLIENT_SECRET": bool(TIKTOK_CLIENT_SECRET),
        "ELEVENLABS_API_KEY": bool(ELEVENLABS_API_KEY),
        "GOOGLE_AI_API_KEY": bool(GOOGLE_AI_API_KEY),
        "MUAPI_API_KEY": bool(MUAPI_API_KEY),
        "HEYGEN_API_KEY": bool(HEYGEN_API_KEY),
        "KALODATA_EMAIL": bool(KALODATA_EMAIL),
    }


# ── Quick test: run this file directly to verify config loads ──
if __name__ == "__main__":
    from rich import print as rprint

    rprint("[bold]Project Root:[/bold]", PROJECT_ROOT)
    rprint("[bold]API Key Status:[/bold]")
    for key, is_set in check_api_keys().items():
        status = "[green]SET[/green]" if is_set else "[red]MISSING[/red]"
        rprint(f"  {key}: {status}")
