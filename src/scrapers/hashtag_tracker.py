"""
hashtag_tracker.py — Monitors trending TikTok hashtags and their volume.

Uses "clockworks/tiktok-hashtag-scraper" Apify actor to track which
hashtags are gaining momentum. This helps us:
  1. Identify emerging trends before they peak
  2. Tag our generated content with high-volume hashtags
  3. Track niche-specific hashtag performance over time

Inputs:
  - list of hashtags to track, or a discovery keyword
  - max results

Outputs:
  - List of hashtag dicts with: name, view_count, video_count, trend_direction
  - Saved to data/raw/hashtags_<timestamp>.json

Usage:
  python -m src.scrapers.hashtag_tracker
"""

from apify_client import ApifyClient
from rich import print as rprint
from rich.table import Table

from src.utils.config import APIFY_API_TOKEN, DATA_RAW_DIR, load_pipeline_config
from src.utils.data_io import save_json

# ── Apify actor ID for hashtag scraping ──
HASHTAG_SCRAPER_ACTOR = "clockworks/tiktok-hashtag-scraper"


def scrape_hashtags(
    hashtags: list[str],
    max_results: int = 20,
) -> list[dict]:
    """
    Scrape stats for a list of TikTok hashtags.

    Args:
        hashtags: List of hashtag strings (without #)
        max_results: Max results per hashtag

    Returns:
        List of hashtag data dicts with view counts and trends
    """
    client = ApifyClient(APIFY_API_TOKEN)

    run_input = {
        "hashtags": hashtags,
        "resultsPerPage": max_results,
    }

    rprint(f"[blue]Scraping hashtag stats for:[/blue] {', '.join(f'#{h}' for h in hashtags)}")
    rprint("[dim]Running Apify actor… this may take a minute.[/dim]")

    try:
        run = client.actor(HASHTAG_SCRAPER_ACTOR).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    except Exception as e:
        rprint(f"[red]Apify hashtag scraper failed: {e}[/red]")
        return []

    rprint(f"[green]Got stats for {len(items)} hashtags[/green]")
    return items


def find_trending_hashtags(keyword: str) -> list[dict]:
    """
    Discover trending hashtags related to a keyword.

    Args:
        keyword: Niche or topic to find hashtags for

    Returns:
        List of trending hashtag dicts, sorted by momentum
    """
    client = ApifyClient(APIFY_API_TOKEN)

    run_input = {
        "hashtags": [keyword],
        "resultsPerPage": 30,
    }

    rprint(f"[blue]Discovering hashtags for:[/blue] '{keyword}'")
    rprint("[dim]Running Apify actor… this may take a minute.[/dim]")

    try:
        run = client.actor(HASHTAG_SCRAPER_ACTOR).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    except Exception as e:
        rprint(f"[red]Apify hashtag discovery failed: {e}[/red]")
        return []

    # Sort by view count descending (highest momentum first)
    items.sort(
        key=lambda x: x.get("viewCount", 0) or x.get("views", 0),
        reverse=True,
    )

    rprint(f"[green]Found {len(items)} related hashtags[/green]")
    return items


def _fmt_views(n: int) -> str:
    """Format large numbers for display."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# ── Run standalone ──
if __name__ == "__main__":
    rprint("[bold blue]TikTok Hashtag Tracker[/bold blue]")
    rprint("-" * 40)

    if not APIFY_API_TOKEN:
        rprint("[red]ERROR: APIFY_API_TOKEN not set in .env[/red]")
        rprint("Copy .env.example to .env and add your token.")
    else:
        config = load_pipeline_config()
        hashtag_list = config.get("hashtags", ["skincare", "glowup", "beautytok"])
        max_results = config.get("max_results_per_query", 10)

        rprint(f"[dim]Niche: {config.get('niche', 'unknown')} | Hashtags: {hashtag_list}[/dim]")

        hashtags = scrape_hashtags(hashtag_list, max_results=max_results)
        if hashtags:
            save_json(hashtags, "hashtags", DATA_RAW_DIR)

            table = Table(title="Hashtag Stats", show_lines=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Hashtag", style="cyan", max_width=25)
            table.add_column("Views", style="green", justify="right")
            table.add_column("Videos", style="blue", justify="right")

            for i, h in enumerate(hashtags[:20], 1):
                name = h.get("name", "") or h.get("hashtag", "")
                views = h.get("viewCount", 0) or h.get("views", 0)
                videos = h.get("videoCount", 0) or h.get("videos", 0)
                table.add_row(str(i), f"#{name}", _fmt_views(views), _fmt_views(videos))

            rprint(table)
