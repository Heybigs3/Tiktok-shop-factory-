"""
video_downloader.py — Download top-performing TikTok videos for analysis.

Uses yt-dlp as a subprocess (same isolation pattern as Whisper in transcriber.py).
Falls back gracefully if yt-dlp is not installed.

Usage:
  python -m src.analyzers  # menu option 6
"""

import shutil
import subprocess
import time
from pathlib import Path

from rich import print as rprint

from src.utils.config import DATA_RAW_DIR, VIDEOS_DIR, load_pipeline_config
from src.utils.data_io import load_latest


def _yt_dlp_available() -> bool:
    """Check if yt-dlp CLI is available on PATH."""
    return shutil.which("yt-dlp") is not None


def _get_stat(video: dict, *keys: str) -> int:
    """Get a stat value trying multiple Apify field names.

    Uses 'in' check instead of truthiness — a value of 0 is valid and should
    not fall through to the next key.
    """
    for key in keys:
        if key in video:
            return int(video[key] or 0)
    return 0


def _rank_videos(videos: list[dict]) -> list[dict]:
    """
    Sort videos by engagement rate and filter to those with downloadable URLs.

    Engagement rate = (likes + shares + comments) / plays.
    Videos without a webVideoUrl or with zero plays are excluded.
    """
    downloadable = []
    for video in videos:
        url = video.get("webVideoUrl", "") or video.get("videoUrl", "")
        if not url:
            continue

        plays = _get_stat(video, "playCount", "plays")
        if plays == 0:
            continue

        likes = _get_stat(video, "diggCount", "likes")
        shares = _get_stat(video, "shareCount", "shares")
        comments = _get_stat(video, "commentCount", "comments")

        engagement_rate = (likes + shares + comments) / plays
        video["_engagement_rate"] = engagement_rate
        video["_download_url"] = url
        downloadable.append(video)

    downloadable.sort(key=lambda v: v["_engagement_rate"], reverse=True)
    return downloadable


def _get_output_filename(video: dict) -> str:
    """
    Build a deterministic, recognizable filename: {id}_{author}.mp4

    Handles both authorMeta.name and flat author field from Apify.
    """
    video_id = video.get("id", "unknown")

    author = ""
    if isinstance(video.get("authorMeta"), dict):
        author = video["authorMeta"].get("name", "")
    if not author:
        author = video.get("author", "unknown")

    # Sanitize for filesystem safety
    safe_author = "".join(c if c.isalnum() or c in "-_" else "_" for c in author)
    return f"{video_id}_{safe_author}.mp4"


def _download_single(url: str, output_path: Path) -> bool:
    """
    Download a single video using yt-dlp.

    Returns True on success, False on failure.
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--format", "mp4", "--no-warnings", "-o", str(output_path), url],
            capture_output=True,
            timeout=120,
        )
        return result.returncode == 0 and output_path.exists()
    except subprocess.TimeoutExpired:
        rprint(f"[yellow]Download timed out: {url}[/yellow]")
        return False
    except FileNotFoundError:
        rprint("[red]yt-dlp not found[/red]")
        return False


def download_top_videos(max_videos: int = 15, min_plays: int = 0) -> list[Path]:
    """
    Download top-performing videos from the latest trending scrape.

    Loads trending_videos from data/raw/, ranks by engagement, skips
    already-downloaded files, and downloads via yt-dlp.

    Args:
        max_videos: Maximum number of videos to download.
        min_plays: Minimum play count to consider a video.

    Returns:
        List of Paths to downloaded .mp4 files.
    """
    if not _yt_dlp_available():
        rprint("[yellow]yt-dlp not installed — skipping video download[/yellow]")
        rprint("[dim]Install with: pip install yt-dlp[/dim]")
        return []

    # Load config overrides
    config = load_pipeline_config()
    analyzer_config = config.get("analyzer", {})
    max_videos = analyzer_config.get("download_top_n", max_videos)
    min_plays = analyzer_config.get("min_plays_for_download", min_plays)

    # Load latest scraped data
    videos = load_latest(DATA_RAW_DIR, "trending_videos")
    if not videos:
        rprint("[yellow]No trending_videos data found in data/raw/[/yellow]")
        rprint("[dim]Run the trend scraper first (Phase 1).[/dim]")
        return []

    if not isinstance(videos, list):
        rprint("[yellow]Unexpected data format — expected a list of videos[/yellow]")
        return []

    # Filter by min plays
    if min_plays > 0:
        videos = [
            v for v in videos
            if _get_stat(v, "playCount", "plays") >= min_plays
        ]

    # Rank by engagement
    ranked = _rank_videos(videos)
    if not ranked:
        rprint("[yellow]No downloadable videos found (missing URLs or zero plays)[/yellow]")
        return []

    # Take top N
    candidates = ranked[:max_videos]
    rprint(f"[blue]Found {len(ranked)} downloadable videos, selecting top {len(candidates)}[/blue]")

    # Download, skipping already-downloaded
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []

    for i, video in enumerate(candidates, 1):
        filename = _get_output_filename(video)
        output_path = VIDEOS_DIR / filename

        if output_path.exists():
            rprint(f"[dim]  {i}. Already downloaded: {filename}[/dim]")
            downloaded.append(output_path)
            continue

        url = video["_download_url"]
        eng = video["_engagement_rate"]
        rprint(f"[blue]  {i}. Downloading {filename} (engagement: {eng:.3f})…[/blue]")

        if _download_single(url, output_path):
            rprint(f"[green]     Saved: {output_path}[/green]")
            downloaded.append(output_path)
        else:
            rprint(f"[red]     Failed: {filename}[/red]")

        # Rate-limit between downloads
        if i < len(candidates):
            time.sleep(2)

    rprint(f"\n[bold green]Downloaded {len(downloaded)} videos to {VIDEOS_DIR}[/bold green]")
    return downloaded


# ── Run standalone for testing ──
if __name__ == "__main__":
    rprint("[bold blue]TikTok Video Downloader[/bold blue]")
    rprint("-" * 40)
    download_top_videos()
