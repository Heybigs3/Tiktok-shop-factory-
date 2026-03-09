"""
video_builder.py — FFmpeg-powered video rendering pipeline. (Phase 3)

Takes generated scripts and produces TikTok-ready 9:16 vertical videos with
white text on a dark background. Three sections per video: Hook → Body → CTA.

Requires FFmpeg installed and on PATH:
    winget install --id Gyan.FFmpeg -e

Usage:
    python -m src.renderers.video_builder
"""

import shutil
import textwrap
from pathlib import Path

import ffmpeg
from rich import print as rprint
from rich.table import Table

from src.utils.config import DATA_SCRIPTS_DIR, FONT_PATH, OUTPUT_DIR
from src.utils.data_io import load_latest

# ── Video constants ──
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
BG_COLOR = "0x1a1a2e"

# ── Typography ──
HOOK_FONT_SIZE = 72
BODY_FONT_SIZE = 48
CTA_FONT_SIZE = 64

# ── Timing ──
HOOK_DURATION = 3
CTA_DURATION = 3
MIN_BODY_DURATION = 4

# ── Text wrapping (characters per line) ──
HOOK_WRAP_WIDTH = 20
BODY_WRAP_WIDTH = 30
CTA_WRAP_WIDTH = 25


def check_ffmpeg() -> bool:
    """Check if FFmpeg is installed and on PATH."""
    if shutil.which("ffmpeg"):
        return True
    rprint("[red]FFmpeg not found on PATH.[/red]")
    rprint("[yellow]Install with:[/yellow]  winget install --id Gyan.FFmpeg -e")
    rprint("[yellow]Then restart your terminal.[/yellow]")
    return False


def escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg's drawtext filter."""
    # Order matters: backslash first, then others
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\u2019")  # Replace apostrophe with right single quote
    return text


def wrap_text(text: str, wrap_width: int) -> str:
    """Word-wrap text and join with newlines for drawtext."""
    if not text:
        return ""
    lines = textwrap.wrap(text, width=wrap_width)
    return "\n".join(lines)


def calculate_timing(script: dict) -> dict:
    """Calculate section durations from a script's estimated_duration_sec.

    Returns dict with hook_duration, body_duration, cta_duration, total_duration.
    """
    total = script.get("estimated_duration_sec", HOOK_DURATION + MIN_BODY_DURATION + CTA_DURATION)

    hook_dur = HOOK_DURATION
    cta_dur = CTA_DURATION
    body_dur = max(total - hook_dur - cta_dur, MIN_BODY_DURATION)
    actual_total = hook_dur + body_dur + cta_dur

    return {
        "hook_duration": hook_dur,
        "body_duration": body_dur,
        "cta_duration": cta_dur,
        "total_duration": actual_total,
    }


def build_section(
    text: str,
    font_size: int,
    wrap_width: int,
    duration: float,
    font_path: str,
) -> ffmpeg.Stream:
    """Generate a single video section: color background + centered drawtext."""
    wrapped = wrap_text(text, wrap_width)
    escaped = escape_drawtext(wrapped)

    stream = ffmpeg.input(
        f"color=c={BG_COLOR}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration}:r={FPS}",
        f="lavfi",
    )
    stream = stream.drawtext(
        fontfile=font_path,
        text=escaped,
        fontsize=font_size,
        fontcolor="white",
        x="(w-text_w)/2",
        y="(h-text_h)/2",
    )
    return stream


def render_video(script: dict, output_path: Path, font_path: Path) -> Path:
    """Render a single script to an MP4 video file.

    Builds 3 sections (hook, body, CTA), concatenates them, and encodes to H.264.
    """
    timing = calculate_timing(script)
    font_str = font_path.as_posix()  # Forward slashes for FFmpeg on Windows

    hook_stream = build_section(
        script.get("hook", ""),
        HOOK_FONT_SIZE, HOOK_WRAP_WIDTH,
        timing["hook_duration"], font_str,
    )
    body_stream = build_section(
        script.get("body", ""),
        BODY_FONT_SIZE, BODY_WRAP_WIDTH,
        timing["body_duration"], font_str,
    )
    cta_stream = build_section(
        script.get("cta", ""),
        CTA_FONT_SIZE, CTA_WRAP_WIDTH,
        timing["cta_duration"], font_str,
    )

    joined = ffmpeg.concat(hook_stream, body_stream, cta_stream, v=1, a=0)
    out = ffmpeg.output(joined, str(output_path), vcodec="libx264", pix_fmt="yuv420p")
    out = out.overwrite_output()
    out.run(quiet=True)

    return output_path


def render_all(scripts: list[dict], font_path: Path | None = None) -> list[Path]:
    """Render all scripts to MP4 videos. Returns list of output paths."""
    if font_path is None:
        font_path = FONT_PATH

    paths = []
    for i, script in enumerate(scripts, 1):
        script_id = script.get("script_id", f"unknown_{i}")
        source_type = script.get("source_type", "mixed")
        filename = f"{script_id[:8]}_{source_type}.mp4"
        output_path = OUTPUT_DIR / filename

        rprint(f"  [{i}/{len(scripts)}] Rendering [cyan]{filename}[/cyan]...")
        try:
            render_video(script, output_path, font_path)
            paths.append(output_path)
            rprint(f"    [green]Done[/green]")
        except ffmpeg.Error as e:
            rprint(f"    [red]FFmpeg error: {e}[/red]")

    return paths


def display_results(paths: list[Path]) -> None:
    """Display a rich table of rendered video files."""
    if not paths:
        rprint("[yellow]No videos rendered.[/yellow]")
        return

    table = Table(title="Rendered Videos", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Filename", style="cyan")
    table.add_column("Size", style="yellow", justify="right")

    for i, path in enumerate(paths, 1):
        size_kb = path.stat().st_size / 1024
        if size_kb > 1024:
            size_str = f"{size_kb / 1024:.1f} MB"
        else:
            size_str = f"{size_kb:.0f} KB"
        table.add_row(str(i), path.name, size_str)

    rprint(table)


def run() -> list[Path]:
    """Full pipeline: check FFmpeg → check font → load scripts → render → display."""
    # Check FFmpeg
    if not check_ffmpeg():
        return []

    # Check font
    if not FONT_PATH.exists():
        rprint(f"[red]Font not found:[/red] {FONT_PATH}")
        rprint("[yellow]Download Inter-Bold.ttf from Google Fonts into assets/fonts/[/yellow]")
        return []

    # Load latest scripts
    rprint("[bold]Loading latest generated scripts...[/bold]")
    scripts = load_latest(DATA_SCRIPTS_DIR, "scripts")
    if not scripts:
        rprint("[yellow]No scripts found. Run the generator first:[/yellow]")
        rprint("  python -m src.generators.script_generator")
        return []

    rprint(f"[green]Found {len(scripts)} scripts[/green]")

    # Render
    rprint("\n[bold]Rendering videos...[/bold]")
    paths = render_all(scripts)

    # Display results
    rprint()
    display_results(paths)
    rprint(f"\n[bold green]Output directory:[/bold green] {OUTPUT_DIR}")

    return paths


if __name__ == "__main__":
    run()
