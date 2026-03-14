"""
tiktok_publisher.py — Interactive CLI to publish videos to TikTok.

This is the Phase 4 entry point. It walks you through:
  1. Log in to TikTok (or use saved token)
  2. Pick a video from output/videos/
  3. Show you a preview (file info, script content)
  4. Let you set privacy, interactions, title
  5. Confirm and upload

TikTok requires ALL of these steps for audit compliance — no auto-posting.

Usage:
  python -m src.publishers.tiktok_publisher
"""

import json
import os
from datetime import date
from pathlib import Path

from rich import print as rprint
from rich.table import Table
from rich.panel import Panel

from src.utils.config import OUTPUT_DIR, DATA_SCRIPTS_DIR, DATA_TOKENS_DIR
from src.utils.data_io import load_latest
from src.publishers.oauth_server import get_valid_token, login
from src.publishers.tiktok_api import (
    query_creator_info,
    init_video_post,
    upload_video_file,
    check_post_status,
)

# ── Daily post limit (TikTok enforces 15/day per creator via API) ──
MAX_POSTS_PER_DAY = 15
POST_LOG_FILE = DATA_TOKENS_DIR / "post_log.json"


def _load_post_log() -> dict:
    """Load the posting log. Tracks posts per creator per day."""
    if POST_LOG_FILE.exists():
        try:
            return json.loads(POST_LOG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_post_log(log: dict) -> None:
    """Save the posting log."""
    POST_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    POST_LOG_FILE.write_text(json.dumps(log, indent=2))


def _get_posts_today(open_id: str) -> int:
    """Get the number of posts made today by this creator."""
    log = _load_post_log()
    today = date.today().isoformat()
    return log.get(today, {}).get(open_id, 0)


def _record_post(open_id: str) -> None:
    """Record a post in the log for today."""
    log = _load_post_log()
    today = date.today().isoformat()
    if today not in log:
        log[today] = {}
    log[today][open_id] = log[today].get(open_id, 0) + 1
    _save_post_log(log)


def _check_daily_limit(open_id: str) -> bool:
    """Check if this creator has hit the daily post limit. Returns True if OK to post."""
    posts_today = _get_posts_today(open_id)
    if posts_today >= MAX_POSTS_PER_DAY:
        rprint(f"\n[red]Daily post limit reached ({MAX_POSTS_PER_DAY} posts today).[/red]")
        rprint("[red]TikTok allows a maximum of 15 posts per day per account via the API.[/red]")
        rprint("[yellow]Try again tomorrow.[/yellow]")
        return False
    remaining = MAX_POSTS_PER_DAY - posts_today
    rprint(f"  [dim]Posts today: {posts_today}/{MAX_POSTS_PER_DAY} (remaining: {remaining})[/dim]")
    return True


def _list_videos() -> list[Path]:
    """Find all MP4 files in the output directory."""
    videos = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return videos


def _find_script_for_video(video_path: Path, scripts: list[dict]) -> dict | None:
    """Try to match a video filename to its source script."""
    # Video names look like "e0f141c6_trending.mp4" where e0f141c6 is the script_id prefix
    video_stem = video_path.stem  # e.g., "e0f141c6_trending"
    id_prefix = video_stem.split("_")[0]  # e.g., "e0f141c6"

    for script in scripts:
        script_id = script.get("script_id", "")
        if script_id.startswith(id_prefix):
            return script

    return None


def _display_video_preview(video_path: Path, script: dict | None) -> None:
    """Show what the user is about to post."""
    size_kb = video_path.stat().st_size / 1024

    rprint(Panel(
        f"[bold]File:[/bold] {video_path.name}\n"
        f"[bold]Size:[/bold] {size_kb:.0f} KB\n"
        f"[bold]Path:[/bold] {video_path}",
        title="Video Preview",
    ))

    if script:
        rprint(Panel(
            f"[bold]Hook:[/bold] {script.get('hook', 'N/A')}\n"
            f"[bold]Body:[/bold] {script.get('body', 'N/A')[:200]}...\n"
            f"[bold]CTA:[/bold] {script.get('cta', 'N/A')}",
            title="Script Content",
        ))


def _pick_video(videos: list[Path]) -> Path | None:
    """Let the user pick which video to post."""
    table = Table(title="Available Videos")
    table.add_column("#", style="bold")
    table.add_column("Filename")
    table.add_column("Size")

    for i, v in enumerate(videos, 1):
        size_kb = v.stat().st_size / 1024
        table.add_row(str(i), v.name, f"{size_kb:.0f} KB")

    rprint(table)

    while True:
        choice = input("\nPick a video number (or 'q' to quit): ").strip()
        if choice.lower() == "q":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(videos):
                return videos[idx]
        except ValueError:
            pass
        rprint("[red]Invalid choice. Try again.[/red]")


def _pick_privacy(options: list[str]) -> str | None:
    """
    Let the user pick who can see the video.
    TikTok REQUIRES that we show only the options from their API,
    and that there's NO default selection.
    """
    rprint("\n[bold]Who can see this video?[/bold]")

    # Friendly labels for TikTok's privacy levels
    labels = {
        "PUBLIC_TO_EVERYONE": "Everyone (Public)",
        "MUTUAL_FOLLOW_FRIENDS": "Friends (Mutual Followers)",
        "FOLLOWER_OF_CREATOR": "Followers Only",
        "SELF_ONLY": "Only Me (Private)",
    }

    for i, opt in enumerate(options, 1):
        label = labels.get(opt, opt)
        rprint(f"  {i}. {label}")

    while True:
        choice = input("\nSelect privacy level (required): ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                selected = options[idx]
                rprint(f"  [green]Selected: {labels.get(selected, selected)}[/green]")
                return selected
        except ValueError:
            pass
        rprint(f"[red]Please enter a number between 1 and {len(options)}.[/red]")


def _pick_interactions(creator_info: dict) -> dict:
    """
    Let the user toggle Comment, Duet, and Stitch.
    All OFF by default (TikTok requirement).
    Greyed out if the user has them disabled in their TikTok settings.
    """
    rprint("\n[bold]Interaction settings[/bold] (all off by default):")

    result = {
        "disable_comment": True,
        "disable_duet": True,
        "disable_stitch": True,
    }

    interactions = [
        ("Allow Comments", "comment_disabled", "disable_comment"),
        ("Allow Duets", "duet_disabled", "disable_duet"),
        ("Allow Stitches", "stitch_disabled", "disable_stitch"),
    ]

    for label, disabled_key, result_key in interactions:
        is_disabled_by_user = creator_info.get(disabled_key, False)

        if is_disabled_by_user:
            rprint(f"  [dim]{label}: DISABLED (turned off in your TikTok settings)[/dim]")
        else:
            choice = input(f"  {label}? (y/N): ").strip().lower()
            if choice == "y":
                result[result_key] = False
                rprint(f"    [green]Enabled[/green]")
            else:
                rprint(f"    Off")

    return result


def _get_title() -> str:
    """Let the user type a title/caption for the video."""
    rprint("\n[bold]Video title / caption[/bold] (max 2200 chars, can include #hashtags)")
    title = input("  Title: ").strip()
    return title


def _confirm_commercial_content() -> tuple[bool, bool]:
    """Ask about commercial content disclosure (off by default, TikTok requirement)."""
    rprint("\n[bold]Commercial content[/bold]")
    rprint("  Does this video promote a brand, product, or service?")

    choice = input("  Is this commercial content? (y/N): ").strip().lower()
    if choice != "y":
        return False, False

    # User said it's commercial — they must pick at least one disclosure type
    rprint("\n  [yellow]You indicated this is commercial content.[/yellow]")
    rprint("  [yellow]You must select at least one of the following:[/yellow]\n")

    brand_content = False
    brand_organic = False

    while not brand_content and not brand_organic:
        choice = input("  Paid partnership / brand deal? (y/N): ").strip().lower()
        brand_content = choice == "y"

        choice = input("  Promoting your own business? (y/N): ").strip().lower()
        brand_organic = choice == "y"

        if not brand_content and not brand_organic:
            rprint("  [red]You must select at least one option, or go back and mark this as non-commercial.[/red]")
            rprint("  [red]TikTok requires a disclosure type for commercial content.[/red]\n")
            retry = input("  Try again? (y/N): ").strip().lower()
            if retry != "y":
                rprint("  [yellow]Commercial content disabled.[/yellow]")
                return False, False

    return brand_content, brand_organic


def _confirm_post(video_path: Path, privacy: str, title: str) -> bool:
    """
    Final consent check before posting.
    TikTok REQUIRES explicit user consent — this is critical for audit.
    """
    labels = {
        "PUBLIC_TO_EVERYONE": "Everyone (Public)",
        "MUTUAL_FOLLOW_FRIENDS": "Friends Only",
        "FOLLOWER_OF_CREATOR": "Followers Only",
        "SELF_ONLY": "Only Me (Private)",
    }

    rprint(Panel(
        f"[bold]Video:[/bold] {video_path.name}\n"
        f"[bold]Title:[/bold] {title or '(no title)'}\n"
        f"[bold]Privacy:[/bold] {labels.get(privacy, privacy)}\n"
        f"\n[bold yellow]AI-Generated Content:[/bold yellow] This video will be labeled\n"
        f"as AI-generated content on TikTok.\n"
        f"\n[yellow]By posting, you confirm this is your content and you want\n"
        f"it published to your TikTok account.[/yellow]\n"
        f"\n[yellow]By posting, you agree to TikTok's Music Usage Confirmation.[/yellow]\n"
        f"\n[dim]Note: It may take a few minutes for the video to appear "
        f"on your profile after posting.[/dim]",
        title="Confirm Post",
        border_style="yellow",
    ))

    confirm = input("\nPost this video to TikTok? (yes/no): ").strip().lower()
    return confirm == "yes"


def publish_flow() -> None:
    """
    The main interactive flow. Walks the user through every step
    of posting a video to TikTok.
    """
    rprint("[bold blue]TikTok Video Publisher[/bold blue]")
    rprint("-" * 40)

    # ── Step 1: Check login ──
    rprint("\n[bold]Step 1: TikTok Login[/bold]")
    token_data = get_valid_token()

    if not token_data:
        rprint("You need to log in to TikTok first.")
        token_data = login()
        if not token_data:
            rprint("[red]Login failed. Cannot continue.[/red]")
            return

    access_token = token_data.get("access_token")
    if not access_token:
        rprint("[red]No access token found. Try logging in again.[/red]")
        return

    open_id = token_data.get("open_id", "unknown")
    rprint("[green]Logged in to TikTok[/green]")

    # ── Check daily post limit ──
    if not _check_daily_limit(open_id):
        return

    # ── Step 2: Get creator info ──
    rprint("\n[bold]Step 2: Loading your TikTok profile...[/bold]")
    creator_info = query_creator_info(access_token)

    if not creator_info:
        rprint("[red]Could not load creator info. Your token may be invalid.[/red]")
        rprint("Try deleting data/tokens/tiktok_token.json and logging in again.")
        return

    nickname = creator_info.get("creator_nickname", "Unknown")
    username = creator_info.get("creator_username", "Unknown")
    rprint(f"  Posting as: [bold]{nickname}[/bold] (@{username})")

    privacy_options = creator_info.get("privacy_level_options", [])
    if not privacy_options:
        rprint("[red]No privacy options available. This usually means the API scope isn't approved.[/red]")
        return

    # Warn about pre-audit limitations
    if privacy_options == ["SELF_ONLY"]:
        rprint("\n  [yellow]Note: Your app has not passed TikTok's audit yet.[/yellow]")
        rprint("  [yellow]All posts will be set to PRIVATE (Only Me) until approved.[/yellow]")
        rprint("  [yellow]Max 5 users can post per 24 hours in pre-audit mode.[/yellow]")

    # ── Step 3: Pick a video ──
    rprint("\n[bold]Step 3: Choose a video[/bold]")
    videos = _list_videos()

    if not videos:
        rprint("[red]No videos found in output/videos/[/red]")
        rprint("Run the pipeline first: python -m src.renderers.video_builder")
        return

    video = _pick_video(videos)
    if not video:
        rprint("[yellow]Cancelled.[/yellow]")
        return

    # Try to load script content for preview
    scripts_data = load_latest(DATA_SCRIPTS_DIR, "scripts")
    scripts_list = scripts_data if isinstance(scripts_data, list) else []
    script = _find_script_for_video(video, scripts_list) if scripts_list else None
    _display_video_preview(video, script)

    # ── Step 4: Post settings ──
    rprint("\n[bold]Step 4: Post settings[/bold]")

    privacy = _pick_privacy(privacy_options)
    if not privacy:
        return

    interactions = _pick_interactions(creator_info)
    title = _get_title()
    brand_content, brand_organic = _confirm_commercial_content()

    # ── Step 5: Confirm and post ──
    rprint("\n[bold]Step 5: Confirm[/bold]")
    if not _confirm_post(video, privacy, title):
        rprint("[yellow]Post cancelled.[/yellow]")
        return

    # ── Step 6: Upload ──
    rprint("\n[bold]Step 6: Uploading...[/bold]")

    init_result = init_video_post(
        access_token=access_token,
        video_path=video,
        title=title,
        privacy_level=privacy,
        disable_comment=interactions["disable_comment"],
        disable_duet=interactions["disable_duet"],
        disable_stitch=interactions["disable_stitch"],
        brand_content_toggle=brand_content,
        brand_organic_toggle=brand_organic,
    )

    if not init_result:
        rprint("[red]Failed to initialize post. Check the error above.[/red]")
        return

    publish_id = init_result.get("publish_id")
    upload_url = init_result.get("upload_url")

    if not upload_url:
        rprint("[red]No upload URL returned. Something went wrong.[/red]")
        return

    rprint(f"  Publish ID: {publish_id}")
    rprint("  Uploading video file...")

    success = upload_video_file(upload_url, video)
    if not success:
        rprint("[red]Video upload failed.[/red]")
        return

    # ── Record the post in the daily log ──
    _record_post(open_id)

    # ── Done! ──
    rprint("\n" + "=" * 40)
    rprint("[bold green]Video submitted to TikTok![/bold green]")
    rprint(f"  Publish ID: {publish_id}")
    rprint()
    rprint("[yellow]Important: It may take a few minutes for the video to")
    rprint("process and appear on your TikTok profile.[/yellow]")
    rprint()
    rprint(f"You can check the status by running:")
    rprint(f"  python -m src.publishers.tiktok_publisher --status {publish_id}")


# ── Run standalone ──
if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--status":
        # Quick status check mode
        token_data = get_valid_token()
        if token_data:
            status = check_post_status(token_data["access_token"], sys.argv[2])
            if status:
                rprint(f"[bold]Post status:[/bold] {status}")
            else:
                rprint("[red]Could not get status.[/red]")
        else:
            rprint("[red]Not logged in.[/red]")
    else:
        publish_flow()
