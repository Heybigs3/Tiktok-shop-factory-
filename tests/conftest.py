"""Shared fixtures, auto-skip logic, and rich CLI output for the test suite."""

import shutil

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.utils.config import ANTHROPIC_API_KEY

console = Console()

# ── Check if FFmpeg is available ──
_FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


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
    console.print(f"  ANTHROPIC_API_KEY: {api_status}")
    console.print(f"  FFmpeg:            {ffmpeg_status}")
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

    for item in items:
        if "integration" in item.keywords and not ANTHROPIC_API_KEY:
            item.add_marker(skip_api)
        if "ffmpeg" in item.keywords and not _FFMPEG_AVAILABLE:
            item.add_marker(skip_ffmpeg)


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
        '"cta": "Follow for more", "style_notes": "Direct to camera, fast cuts"}, '
        '{"hook": "Stop scrolling right now", "body": "I tested every product so '
        'you do not have to. The winner surprised me.", '
        '"cta": "Comment your guess", "style_notes": "Green screen, text overlay"}]'
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
        "script_id": "a1b2c3d4-5678-9012-3456-789012345678",
        "source_type": "trending",
        "estimated_duration_sec": 15,
    }
