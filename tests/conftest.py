"""Shared fixtures, auto-skip logic, and rich CLI output for the test suite."""

import shutil

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.utils.config import ANTHROPIC_API_KEY, TIKTOK_CLIENT_KEY

console = Console()

# ── Check external tool availability ──
_FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
_WHISPER_AVAILABLE = shutil.which("whisper") is not None


# ── Rich session header & footer ──

def pytest_sessionstart(session):
    """Print a styled banner at the start of the test run."""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]TikTok Factory[/bold cyan]  [dim]Test Suite[/dim]",
            border_style="cyan",
        )
    )
    api_status = "[green]SET[/green]" if ANTHROPIC_API_KEY else "[yellow]NOT SET[/yellow] (integration tests will skip)"
    ffmpeg_status = "[green]INSTALLED[/green]" if _FFMPEG_AVAILABLE else "[yellow]NOT FOUND[/yellow] (ffmpeg tests will skip)"
    tiktok_status = "[green]SET[/green]" if TIKTOK_CLIENT_KEY else "[yellow]NOT SET[/yellow] (tiktok tests will skip)"
    whisper_status = "[green]INSTALLED[/green]" if _WHISPER_AVAILABLE else "[yellow]NOT FOUND[/yellow] (whisper tests will skip)"
    console.print(f"  ANTHROPIC_API_KEY:  {api_status}")
    console.print(f"  TIKTOK_CLIENT_KEY:  {tiktok_status}")
    console.print(f"  FFmpeg:             {ffmpeg_status}")
    console.print(f"  Whisper:            {whisper_status}")
    console.print()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print a rich summary table after all tests complete."""
    stats = terminalreporter.stats

    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    skipped = len(stats.get("skipped", []))
    errors = len(stats.get("error", []))
    total = passed + failed + skipped + errors

    table = Table(title="Results", show_edge=False, pad_edge=False)
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    if passed:
        table.add_row("[green]Passed[/green]", str(passed))
    if failed:
        table.add_row("[red]Failed[/red]", str(failed))
    if skipped:
        table.add_row("[yellow]Skipped[/yellow]", str(skipped))
    if errors:
        table.add_row("[red]Errors[/red]", str(errors))
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")

    console.print()
    console.print(table)

    if failed == 0 and errors == 0:
        console.print("\n  [bold green]All tests passed![/bold green]\n")
    else:
        console.print(f"\n  [bold red]{failed + errors} issue(s) found.[/bold red]\n")


# ── Auto-skip integration tests when API key is missing ──

def pytest_collection_modifyitems(config, items):
    """Skip integration-marked tests if ANTHROPIC_API_KEY is not set.
    Skip ffmpeg-marked tests if FFmpeg is not installed."""
    skip_api = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set")
    skip_ffmpeg = pytest.mark.skip(reason="FFmpeg not installed")
    skip_tiktok = pytest.mark.skip(reason="TIKTOK_CLIENT_KEY not set")
    skip_whisper = pytest.mark.skip(reason="Whisper not installed")

    for item in items:
        if "integration" in item.keywords and not ANTHROPIC_API_KEY:
            item.add_marker(skip_api)
        if "ffmpeg" in item.keywords and not _FFMPEG_AVAILABLE:
            item.add_marker(skip_ffmpeg)
        if "tiktok" in item.keywords and not TIKTOK_CLIENT_KEY:
            item.add_marker(skip_tiktok)
        if "whisper" in item.keywords and not _WHISPER_AVAILABLE:
            item.add_marker(skip_whisper)


# ── Fixtures ──

@pytest.fixture
def sample_trending_hooks():
    """3 fake trending hook dicts."""
    return [
        {
            "hook_text": "You won't believe what happened next",
            "stats": {"plays": 2_500_000},
            "author": "creator1",
        },
        {
            "hook_text": "Stop scrolling if you have acne",
            "stats": {"plays": 800_000},
            "author": "creator2",
        },
        {
            "hook_text": "POV: you finally found the hack",
            "stats": {"plays": 150},
            "author": "creator3",
        },
    ]


@pytest.fixture
def sample_ad_hooks():
    """2 fake ad hook dicts."""
    return [
        {
            "hook_text": "This changed my skin in 3 days",
            "cta": "Shop now — link in bio",
        },
        {
            "hook_text": "Dermatologists don't want you to know this",
            "cta": "Follow for part 2",
        },
    ]


@pytest.fixture
def sample_claude_response():
    """Raw JSON string as Claude would return (2 scripts)."""
    return (
        '[{"hook": "Did you know this?", "body": "Here is the secret trick '
        'that everyone misses. You just need to do this one thing every day.", '
        '"cta": "Follow for more", "style_notes": "Direct to camera, fast cuts", '
        '"suggested_hashtags": ["skincare", "beautyhack", "glowup"], '
        '"visual_hints": {"mood": "warm", "key_overlay_text": "3x results", "background_style": "solid"}}, '
        '{"hook": "Stop scrolling right now", "body": "I tested every product so '
        'you do not have to. The winner surprised me.", '
        '"cta": "Comment your guess", "style_notes": "Green screen, text overlay", '
        '"suggested_hashtags": ["productreview", "skincare"], '
        '"visual_hints": {"mood": "energetic", "key_overlay_text": "#1 pick", "background_style": "gradient"}}]'
    )


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Temporary directory for data_io tests."""
    return tmp_path


@pytest.fixture
def sample_script():
    """Single script dict matching Phase 2 output format."""
    return {
        "hook": "Did you know this one trick?",
        "body": "Here is the secret that nobody talks about. You just need to do this simple thing every single day and the results will blow your mind.",
        "cta": "Follow for more tips",
        "style_notes": "Direct to camera, fast cuts",
        "suggested_hashtags": ["skincare", "beautytok", "glowup"],
        "visual_hints": {
            "mood": "warm",
            "key_overlay_text": "10x more effective",
            "background_style": "solid",
        },
        "script_id": "a1b2c3d4-5678-9012-3456-789012345678",
        "source_type": "trending",
        "estimated_duration_sec": 15,
    }


@pytest.fixture
def sample_raw_apify_videos():
    """3 raw Apify video dicts (as returned by the TikTok scraper actor)."""
    return [
        {
            "id": "vid001",
            "text": "Stop scrolling if you have acne. This routine changed everything.",
            "authorMeta": {"name": "skincarequeen", "fans": 500000, "verified": True},
            "playCount": 2500000,
            "diggCount": 125000,
            "shareCount": 8000,
            "commentCount": 3200,
            "videoMeta": {"duration": 22},
            "webVideoUrl": "https://tiktok.com/@skincarequeen/vid001",
        },
        {
            "id": "vid002",
            "text": "POV: you found the perfect moisturizer for dry skin",
            "author": "glowgirl",
            "plays": 800000,
            "likes": 40000,
            "shares": 2000,
            "comments": 1500,
            "duration": 15,
        },
        {
            "id": "vid003",
            "text": "This $5 serum beats the $80 one. Here is why it works so well.",
            "authorMeta": {"name": "budgetbeauty", "fans": 120000, "verified": False},
            "playCount": 450000,
            "diggCount": 22500,
            "shareCount": 5000,
            "commentCount": 800,
        },
    ]


@pytest.fixture
def sample_hashtags():
    """Fake hashtag data matching scraper output."""
    return [
        {"name": "skincare", "viewCount": 45_000_000_000, "videoCount": 12_000_000},
        {"name": "glowup", "viewCount": 28_000_000_000, "videoCount": 8_000_000},
        {"name": "beautytok", "viewCount": 15_000_000_000, "videoCount": 5_000_000},
    ]


@pytest.fixture
def sample_account():
    """Fake account dict matching accounts.py output format."""
    return {
        "id": "abc123def456",
        "name": "Test Skincare",
        "niche": "skincare",
        "created_at": "2026-03-12T00:00:00+00:00",
        "is_default": False,
    }


@pytest.fixture
def sample_queue_entry():
    """Fake queue entry dict matching queue_service.py output format."""
    return {
        "queue_id": "q1a2b3c4d5e6",
        "script_id": "a1b2c3d4",
        "video_path": "output/videos/a1b2c3d4_trending.mp4",
        "hook_preview": "You won't believe this trick",
        "scheduled_date": "2026-03-15",
        "scheduled_time": "14:00",
        "status": "scheduled",
        "created_at": "2026-03-12T00:00:00+00:00",
    }


@pytest.fixture
def sample_creator_info():
    """Fake TikTok creator info response matching query_creator_info() output."""
    return {
        "creator_nickname": "TestCreator",
        "creator_username": "testcreator",
        "creator_avatar_url": "https://example.com/avatar.jpg",
        "privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
        "comment_disabled": False,
        "duet_disabled": False,
        "stitch_disabled": False,
        "max_video_post_duration_sec": 600,
    }
