"""
CLI entry point for the Video Analysis Pipeline.

Usage:
  python -m src.analyzers
"""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from src.analyzers.frame_extractor import extract_frames, extract_scene_frames, get_video_id, get_video_metadata
from src.analyzers.style_bible import generate_style_bible
from src.analyzers.transcriber import transcribe
from src.analyzers.video_analysis import analyze_and_save
from src.analyzers.video_downloader import download_top_videos
from src.analyzers.comparison import compare_videos
from src.utils.config import ANTHROPIC_API_KEY, VIDEOS_DIR, load_pipeline_config

console = Console()


def _find_videos() -> list[Path]:
    """Find all .mp4 files in the videos/ directory."""
    if not VIDEOS_DIR.exists():
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    videos = sorted(VIDEOS_DIR.glob("*.mp4"))
    if not videos:
        console.print(f"[yellow]No .mp4 files found in {VIDEOS_DIR}[/yellow]")
        console.print("[dim]Place TikTok videos in the videos/ directory to analyze them.[/dim]")
    return videos


def _analyze_single_video(video_path: Path) -> dict | None:
    """Run the full analysis pipeline on a single video."""
    config = load_pipeline_config()
    analyzer_config = config.get("analyzer", {})

    video_id = get_video_id(video_path)
    console.print(f"\n[bold]Analyzing:[/bold] {video_path.name} (ID: {video_id})")

    # Step 1: Get metadata
    metadata = get_video_metadata(video_path)
    if not metadata:
        console.print("[red]Could not read video metadata[/red]")
        return None
    console.print(f"[dim]  Duration: {metadata['duration']:.1f}s, {metadata['width']}x{metadata['height']}[/dim]")

    # Step 2: Extract frames
    use_scene = analyzer_config.get("scene_detection", True)
    num_frames = analyzer_config.get("num_frames", 5)

    if use_scene:
        threshold = analyzer_config.get("scene_threshold", 0.3)
        frames = extract_scene_frames(video_path, threshold=threshold)
    else:
        frames = extract_frames(video_path, num_frames=num_frames)

    if not frames:
        console.print("[red]No frames extracted[/red]")
        return None

    # Step 3: Transcribe
    transcript = transcribe(video_path)

    # Step 4: Analyze with Claude
    analysis = analyze_and_save(video_id, frames, transcript, metadata)
    return analysis


def run_download():
    """Download top-performing videos for analysis."""
    downloaded = download_top_videos()
    if downloaded:
        console.print(f"\n[bold green]Downloaded {len(downloaded)} videos[/bold green]")
    else:
        console.print("[yellow]No videos downloaded[/yellow]")


def run_full_pipeline():
    """Analyze all videos and generate a Style Bible."""
    videos = _find_videos()
    if not videos:
        console.print("[dim]No videos found — attempting to download top videos first…[/dim]")
        downloaded = download_top_videos()
        if downloaded:
            videos = _find_videos()
    if not videos:
        return

    console.print(f"\n[bold cyan]Analyzing {len(videos)} videos…[/bold cyan]")

    results = []
    for i, video_path in enumerate(videos, 1):
        console.print(f"\n{'-' * 40}")
        console.print(f"[bold]Video {i}/{len(videos)}[/bold]")
        analysis = _analyze_single_video(video_path)
        if analysis:
            results.append(analysis)

    console.print(f"\n{'=' * 40}")
    console.print(f"[bold green]Analyzed {len(results)}/{len(videos)} videos[/bold green]")

    if results:
        console.print("\n[bold cyan]Generating Style Bible…[/bold cyan]")
        generate_style_bible(results)


def run_extract_frames():
    """Extract frames only (no analysis)."""
    videos = _find_videos()
    if not videos:
        return

    config = load_pipeline_config()
    analyzer_config = config.get("analyzer", {})
    use_scene = analyzer_config.get("scene_detection", True)
    num_frames = analyzer_config.get("num_frames", 5)

    for video_path in videos:
        if use_scene:
            threshold = analyzer_config.get("scene_threshold", 0.3)
            extract_scene_frames(video_path, threshold=threshold)
        else:
            extract_frames(video_path, num_frames=num_frames)


def run_transcribe():
    """Transcribe all videos (no analysis)."""
    videos = _find_videos()
    if not videos:
        return

    for video_path in videos:
        transcribe(video_path)


def run_style_bible():
    """Generate Style Bible from existing analyses."""
    generate_style_bible()


def run_single_video():
    """Analyze a single video (interactive selection)."""
    videos = _find_videos()
    if not videos:
        return

    console.print("\n[bold]Available videos:[/bold]")
    for i, v in enumerate(videos, 1):
        console.print(f"  [bold]{i}[/bold]) {v.name}")

    console.print()
    choice = console.input("[bold cyan]Pick a video:[/bold cyan] ").strip()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(videos):
            _analyze_single_video(videos[idx])
        else:
            console.print("[red]Invalid selection[/red]")
    except ValueError:
        console.print("[red]Enter a number[/red]")


def run_comparison():
    """Compare scraped videos vs our rendered videos."""
    report = compare_videos()
    if report:
        gaps = report.get("gaps", [])
        console.print(f"\n[bold]Verdict:[/bold] {report.get('overall_verdict', 'N/A')}")
        console.print(f"[bold]{len(gaps)} gaps identified[/bold]")
        for gap in gaps:
            console.print(f"  [gold1]{gap.get('category', '')}[/gold1]: {gap.get('issue', '')}")
    else:
        console.print("[yellow]Comparison failed[/yellow]")


MENU = {
    "1": ("Analyze videos (full pipeline)", run_full_pipeline),
    "2": ("Extract frames only", run_extract_frames),
    "3": ("Transcribe only", run_transcribe),
    "4": ("Generate Style Bible from existing analyses", run_style_bible),
    "5": ("Analyze single video", run_single_video),
    "6": ("Download top videos", run_download),
    "7": ("Compare scraped vs rendered", run_comparison),
    "q": ("Back", None),
}


def main():
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]TikTok Factory[/bold cyan]  [dim]Video Analyzer[/dim]",
            border_style="cyan",
        )
    )

    if not ANTHROPIC_API_KEY:
        console.print("[yellow]  Warning: ANTHROPIC_API_KEY not set — analysis requires it[/yellow]")
    console.print()

    for key, (label, _) in MENU.items():
        style = "dim" if key == "q" else "white"
        console.print(f"  [{style}][bold]{key}[/bold]) {label}[/{style}]")

    console.print()
    choice = console.input("[bold cyan]Pick an option:[/bold cyan] ").strip()

    if choice not in MENU or choice == "q":
        console.print("[dim]Back to main menu.[/dim]")
        return

    label, action = MENU[choice]
    console.print(f"\n[bold]Running:[/bold] {label}")
    action()


if __name__ == "__main__":
    main()
