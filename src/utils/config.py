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

import os
from pathlib import Path

from dotenv import load_dotenv

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

# ── Data directories ──
DATA_RAW_DIR: Path = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR: Path = PROJECT_ROOT / "data" / "processed"
DATA_SCRIPTS_DIR: Path = PROJECT_ROOT / "data" / "scripts"
OUTPUT_DIR: Path = PROJECT_ROOT / "output" / "videos"

# ── Asset paths ──
ASSETS_DIR: Path = PROJECT_ROOT / "assets"
FONT_PATH: Path = ASSETS_DIR / "fonts" / "Inter-Bold.ttf"

# ── Ensure data dirs exist (creates them if missing) ──
for _dir in [DATA_RAW_DIR, DATA_PROCESSED_DIR, DATA_SCRIPTS_DIR, OUTPUT_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)


def check_api_keys() -> dict[str, bool]:
    """Check which API keys are configured. Returns dict of key_name: is_set."""
    return {
        "APIFY_API_TOKEN": bool(APIFY_API_TOKEN),
        "ANTHROPIC_API_KEY": bool(ANTHROPIC_API_KEY),
        "TIKTOK_CLIENT_KEY": bool(TIKTOK_CLIENT_KEY),
        "TIKTOK_CLIENT_SECRET": bool(TIKTOK_CLIENT_SECRET),
    }


# ── Quick test: run this file directly to verify config loads ──
if __name__ == "__main__":
    from rich import print as rprint

    rprint("[bold]Project Root:[/bold]", PROJECT_ROOT)
    rprint("[bold]API Key Status:[/bold]")
    for key, is_set in check_api_keys().items():
        status = "[green]SET[/green]" if is_set else "[red]MISSING[/red]"
        rprint(f"  {key}: {status}")
