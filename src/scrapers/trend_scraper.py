"""
trend_scraper.py — Scrapes top-performing TikTok videos using Apify.

This is the primary data source for the Content Factory. It uses the
"apify/tiktok-scraper" actor to pull trending videos, then extracts the
"hook" (first 3 seconds / opening line) from each video.

Why hooks matter:
  63% of successful TikTok ads deliver their message in the first 3 seconds.
  By scraping hooks from winning videos, we can reverse-engineer what grabs
  attention and use those patterns in our own scripts.

Inputs:
  - search term or hashtag (e.g., "skincare routine")
  - max number of results
  - Apify API token (from .env)

Outputs:
  - List of video dicts with: id, description, author, stats, hook text
  - Saved to data/raw/trending_videos_<timestamp>.json

Usage:
  python -m src.scrapers.trend_scraper
"""

from apify_client import ApifyClient
from rich import print as rprint
from rich.table import Table

from src.utils.config import APIFY_API_TOKEN, DATA_RAW_DIR
from src.utils.data_io import save_json

# ── Apify actor ID for TikTok video scraping ──
TIKTOK_SCRAPER_ACTOR = "apify/tiktok-scraper"


def scrape_trending_videos(
    search_term: str,
    max_results: int = 20,
) -> list[dict]:
    """
    Scrape trending TikTok videos for a given search term.

    Args:
        search_term: What to search for (hashtag or keyword)
        max_results: Maximum number of videos to return

    Returns:
        List of video data dicts from Apify

    How it works:
        1. Creates an Apify client with our API token
        2. Runs the TikTok Scraper actor with our search params
        3. Waits for the actor to finish
        4. Returns the scraped dataset items
    """
    client = ApifyClient(APIFY_API_TOKEN)

    run_input = {
        "searchQueries": [search_term],
        "resultsPerPage": max_results,
        "shouldDownloadVideos": False,
    }

    rprint(f"[blue]Scraping TikTok for:[/blue] '{search_term}' (max {max_results} results)")
    rprint("[dim]Running Apify actor… this may take a minute.[/dim]")

    run = client.actor(TIKTOK_SCRAPER_ACTOR).call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    rprint(f"[green]Got {len(items)} videos from TikTok[/green]")
    return items


def extract_hooks(videos: list[dict]) -> list[dict]:
    """
    Extract the "hook" (opening line) from each video's description/transcript.

    The hook is the first sentence or first 100 characters of the video text —
    this is what grabs viewers in the first 3 seconds.

    Args:
        videos: List of video dicts from scrape_trending_videos()

    Returns:
        List of dicts with: video_id, author, hook_text, stats
    """
    hooks = []
    for video in videos:
        text = video.get("text", "") or video.get("description", "") or ""
        # Extract hook: first sentence, or first 100 chars if no sentence boundary
        hook_text = ""
        if text:
            # Split on sentence-ending punctuation
            for end_char in [".", "!", "?"]:
                idx = text.find(end_char)
                if idx != -1 and idx < 150:
                    hook_text = text[: idx + 1].strip()
                    break
            if not hook_text:
                hook_text = text[:100].strip()

        hooks.append({
            "video_id": video.get("id", ""),
            "author": video.get("authorMeta", {}).get("name", "")
                      if isinstance(video.get("authorMeta"), dict)
                      else video.get("author", ""),
            "hook_text": hook_text,
            "stats": {
                "plays": video.get("playCount", 0) or video.get("plays", 0),
                "likes": video.get("diggCount", 0) or video.get("likes", 0),
                "shares": video.get("shareCount", 0) or video.get("shares", 0),
                "comments": video.get("commentCount", 0) or video.get("comments", 0),
            },
        })

    rprint(f"[green]Extracted hooks from {len(hooks)} videos[/green]")
    return hooks


def display_results(videos: list[dict]) -> None:
    """Pretty-print scraped videos as a rich table."""
    if not videos:
        rprint("[yellow]No videos to display.[/yellow]")
        return

    table = Table(title="Trending TikTok Videos", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Author", style="cyan", max_width=15)
    table.add_column("Hook / Opening", style="white", max_width=50)
    table.add_column("Plays", style="green", justify="right")
    table.add_column("Likes", style="red", justify="right")

    for i, video in enumerate(videos[:20], 1):
        text = video.get("text", "") or video.get("description", "") or ""
        hook = text[:80] + "…" if len(text) > 80 else text

        author = ""
        if isinstance(video.get("authorMeta"), dict):
            author = video["authorMeta"].get("name", "")
        else:
            author = video.get("author", "unknown")

        plays = video.get("playCount", 0) or video.get("plays", 0)
        likes = video.get("diggCount", 0) or video.get("likes", 0)

        def _fmt(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.1f}K"
            return str(n)

        table.add_row(str(i), author, hook, _fmt(plays), _fmt(likes))

    rprint(table)


# ── Run standalone for testing ──
if __name__ == "__main__":
    rprint("[bold blue]TikTok Trend Scraper[/bold blue]")
    rprint("─" * 40)

    # Quick config check
    if not APIFY_API_TOKEN:
        rprint("[red]ERROR: APIFY_API_TOKEN not set in .env[/red]")
        rprint("Copy .env.example to .env and add your token.")
    else:
        videos = scrape_trending_videos("skincare routine", max_results=10)
        if videos:
            hooks = extract_hooks(videos)
            save_json(videos, "trending_videos", DATA_RAW_DIR)
            display_results(videos)
