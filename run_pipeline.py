"""Pipeline orchestrator — run the full content factory or individual phases."""

import subprocess
import sys

from rich.console import Console
from rich.panel import Panel

from src.utils.config import (
    APIFY_API_TOKEN,
    ANTHROPIC_API_KEY,
    GOOGLE_AI_API_KEY,
    MUAPI_API_KEY,
    KALODATA_EMAIL,
    OUTPUT_IMAGES_DIR,
    OUTPUT_CLIPS_DIR,
    PRODUCT_IMAGES_DIR,
    DATA_STYLE_BIBLES_DIR,
    load_pipeline_config,
)

console = Console()


def _run_module(module: str) -> bool:
    """Run a python module and return True if it succeeded."""
    result = subprocess.run([sys.executable, "-m", module])
    return result.returncode == 0


def run_scrape() -> bool:
    """Phase 1: Scrape trending videos and process hooks."""
    console.print("\n[bold cyan]Phase 1: Scraping TikTok trends[/bold cyan]")
    console.print("─" * 40)

    if not APIFY_API_TOKEN:
        console.print("[red]APIFY_API_TOKEN not set in .env — skipping scrape[/red]")
        return False

    success = _run_module("src.scrapers.trend_scraper")
    if not success:
        console.print("[red]Trend scraper failed[/red]")
    return success


def run_generate() -> bool:
    """Phase 2: Generate scripts from scraped hooks."""
    console.print("\n[bold cyan]Phase 2: Generating scripts[/bold cyan]")
    console.print("─" * 40)

    if not ANTHROPIC_API_KEY:
        console.print("[red]ANTHROPIC_API_KEY not set in .env — skipping generation[/red]")
        return False

    success = _run_module("src.generators.script_generator")
    if not success:
        console.print("[red]Script generator failed[/red]")
    return success


def run_render() -> bool:
    """Phase 3: Render videos from scripts."""
    console.print("\n[bold cyan]Phase 3: Rendering videos[/bold cyan]")
    console.print("─" * 40)

    success = _run_module("src.renderers.video_builder")
    if not success:
        console.print("[red]Video renderer failed[/red]")
    return success


def run_scrape_products() -> bool:
    """Scrape products from Kalodata."""
    console.print("\n[bold cyan]Scraping products from Kalodata[/bold cyan]")
    console.print("─" * 40)

    if not KALODATA_EMAIL:
        console.print("[red]KALODATA_EMAIL not set in .env — skipping product scrape[/red]")
        return False

    success = _run_module("src.scrapers.kalodata_scraper")
    if not success:
        console.print("[red]Kalodata scraper failed[/red]")
    return success


def run_generate_images() -> bool:
    """Generate scene images with Nano Banana Pro."""
    console.print("\n[bold cyan]Generating scene images (Nano Banana Pro)[/bold cyan]")
    console.print("─" * 40)

    if not GOOGLE_AI_API_KEY:
        console.print("[red]GOOGLE_AI_API_KEY not set in .env — skipping[/red]")
        return False

    success = _run_module("src.renderers.image_generator")
    if not success:
        console.print("[red]Image generator failed[/red]")
    return success


def run_generate_clips() -> bool:
    """Generate video clips with Higgsfield."""
    console.print("\n[bold cyan]Generating video clips (Higgsfield)[/bold cyan]")
    console.print("─" * 40)

    if not MUAPI_API_KEY:
        console.print("[red]MUAPI_API_KEY not set in .env — skipping[/red]")
        return False

    success = _run_module("src.renderers.video_generator")
    if not success:
        console.print("[red]Video clip generator failed[/red]")
    return success


def _check_assets() -> None:
    """Log asset availability between pipeline stages."""
    console.print("\n[bold cyan]Asset Check[/bold cyan]")
    console.print("─" * 40)

    # Product images from Kalodata
    product_imgs = list(PRODUCT_IMAGES_DIR.glob("*.jpg")) + list(PRODUCT_IMAGES_DIR.glob("*.png"))
    if product_imgs:
        console.print(f"  Product images: [green]{len(product_imgs)} files[/green] in {PRODUCT_IMAGES_DIR}")
    else:
        console.print(f"  Product images: [yellow]EMPTY[/yellow] — {PRODUCT_IMAGES_DIR}")

    # Generated scene images
    image_dirs = [d for d in OUTPUT_IMAGES_DIR.iterdir() if d.is_dir()] if OUTPUT_IMAGES_DIR.exists() else []
    total_images = sum(len(list(d.glob("*.png")) + list(d.glob("*.jpg"))) for d in image_dirs)
    if total_images:
        console.print(f"  Scene images:   [green]{total_images} files[/green] across {len(image_dirs)} script(s)")
    else:
        console.print(f"  Scene images:   [yellow]EMPTY[/yellow] — {OUTPUT_IMAGES_DIR}")

    # Generated video clips
    clip_dirs = [d for d in OUTPUT_CLIPS_DIR.iterdir() if d.is_dir()] if OUTPUT_CLIPS_DIR.exists() else []
    total_clips = sum(len(list(d.glob("*.mp4"))) for d in clip_dirs)
    if total_clips:
        console.print(f"  Video clips:    [green]{total_clips} files[/green] across {len(clip_dirs)} script(s)")
    else:
        console.print(f"  Video clips:    [dim]none (Muapi skipped by default)[/dim]")

    console.print()


def run_product_pipeline() -> None:
    """Full product pipeline: scrape products → images → scripts → render.

    Skips Muapi clip generation by default — Ken Burns on Gemini images is
    free and produces good results. Use option 10 to generate clips separately.
    """
    config = load_pipeline_config()
    niche = config.get("niche", "unknown")
    console.print(f"\n[bold]Running product pipeline for niche: [cyan]{niche}[/cyan][/bold]")

    products_ok = run_scrape_products()
    if not products_ok:
        console.print("\n[yellow]Product scrape failed — generator will use existing data if available[/yellow]")

    generate_ok = run_generate()
    if not generate_ok:
        console.print("\n[yellow]Generation failed[/yellow]")

    images_ok = run_generate_images()

    _check_assets()

    render_ok = run_render()

    # Summary
    console.print("\n" + "=" * 40)
    console.print("[bold]Product Pipeline Summary[/bold]")
    for label, ok in [
        ("Products", products_ok), ("Scripts", generate_ok),
        ("Images", images_ok), ("Render", render_ok),
    ]:
        status = "[green]OK[/green]" if ok else "[red]FAILED[/red]"
        console.print(f"  {label}: {status}")
    console.print()


def _style_bible_status() -> tuple[bool, str]:
    """Check if a Style Bible exists and how old it is."""
    config = load_pipeline_config()
    niche = config.get("analyzer", {}).get("style_bible_niche", config.get("niche", "general"))
    sb_path = DATA_STYLE_BIBLES_DIR / f"{niche}_style_bible.json"

    if not sb_path.exists():
        return False, f"No Style Bible for '{niche}'"

    import datetime
    mtime = datetime.datetime.fromtimestamp(sb_path.stat().st_mtime)
    age = datetime.datetime.now() - mtime
    hours = age.total_seconds() / 3600

    if hours < 24:
        return True, f"Style Bible '{niche}' is {hours:.0f}h old (fresh)"
    else:
        return True, f"Style Bible '{niche}' is {hours / 24:.0f}d old (stale — will regenerate)"


def run_analyze_and_bible() -> bool:
    """Download top videos → analyze → generate Style Bible."""
    console.print("\n[bold cyan]Intelligence: Analyze trending videos[/bold cyan]")
    console.print("─" * 40)

    if not ANTHROPIC_API_KEY:
        console.print("[red]ANTHROPIC_API_KEY not set — analysis requires it[/red]")
        return False

    # Check if Style Bible is fresh enough to skip
    exists, status = _style_bible_status()
    console.print(f"  {status}")

    if exists:
        import datetime
        config = load_pipeline_config()
        niche = config.get("analyzer", {}).get("style_bible_niche", config.get("niche", "general"))
        sb_path = DATA_STYLE_BIBLES_DIR / f"{niche}_style_bible.json"
        mtime = datetime.datetime.fromtimestamp(sb_path.stat().st_mtime)
        age_hours = (datetime.datetime.now() - mtime).total_seconds() / 3600
        if age_hours < 24:
            console.print("  [green]Style Bible is fresh — skipping re-analysis[/green]")
            return True

    # Step 1: Download top videos
    console.print("\n  [bold]Step 1/3:[/bold] Downloading top videos for analysis...")
    try:
        from src.analyzers.video_downloader import download_top_videos
        downloaded = download_top_videos()
        if downloaded:
            console.print(f"  [green]Downloaded {len(downloaded)} videos[/green]")
        else:
            console.print("  [yellow]No new videos downloaded — using existing[/yellow]")
    except Exception as e:
        console.print(f"  [yellow]Download failed: {e} — using existing videos[/yellow]")

    # Step 2: Analyze all videos + generate Style Bible
    console.print("\n  [bold]Step 2/3:[/bold] Analyzing videos + generating Style Bible...")
    try:
        from src.analyzers.__main__ import run_full_pipeline
        run_full_pipeline()
    except Exception as e:
        console.print(f"  [red]Analysis failed: {e}[/red]")
        return False

    # Step 3: Run comparison (scraped vs rendered)
    console.print("\n  [bold]Step 3/3:[/bold] Comparing our videos against top performers...")
    try:
        from src.analyzers.comparison import compare_videos
        report = compare_videos()
        if report:
            gaps = report.get("gaps", [])
            console.print(f"  [green]Comparison complete — {len(gaps)} gaps identified[/green]")
            for gap in gaps[:3]:
                console.print(f"    [gold1]{gap.get('category', '')}[/gold1]: {gap.get('issue', '')}")
        else:
            console.print("  [yellow]Comparison skipped (need both scraped and rendered videos)[/yellow]")
    except Exception as e:
        console.print(f"  [yellow]Comparison failed: {e}[/yellow]")

    _, status = _style_bible_status()
    console.print(f"\n  {status}")
    return True


def run_smart_pipeline() -> None:
    """Intelligence-first pipeline: analyze → scrape → generate → images → render.

    This is the recommended way to run the factory. It ensures the script
    generator has Style Bible + comparison data before writing scripts,
    so the output actually matches what's working on TikTok.
    """
    config = load_pipeline_config()
    niche = config.get("niche", "unknown")
    console.print(f"\n[bold]Smart pipeline for niche: [cyan]{niche}[/cyan][/bold]")
    console.print("[dim]analyze trends → scrape data → generate scripts → render videos[/dim]\n")

    # 1. Intelligence: analyze top videos, build Style Bible, compare
    intel_ok = run_analyze_and_bible()

    # 2. Scrape fresh trends
    scrape_ok = run_scrape()
    if not scrape_ok:
        console.print("\n[yellow]Scrape failed — generator will use existing data[/yellow]")

    # 3. Generate scripts (now informed by Style Bible + comparison gaps)
    generate_ok = run_generate()
    if not generate_ok:
        console.print("\n[yellow]Generation failed[/yellow]")
        return

    # 4. Generate scene images
    images_ok = run_generate_images()

    _check_assets()

    # 5. Render
    render_ok = run_render()

    # Summary
    console.print("\n" + "=" * 40)
    console.print("[bold]Smart Pipeline Summary[/bold]")
    for label, ok in [
        ("Intelligence", intel_ok), ("Scrape", scrape_ok),
        ("Scripts", generate_ok), ("Images", images_ok), ("Render", render_ok),
    ]:
        status = "[green]OK[/green]" if ok else "[red]FAILED[/red]"
        console.print(f"  {label}: {status}")
    console.print()


def run_full() -> None:
    """Run the full pipeline: scrape → generate → render."""
    config = load_pipeline_config()
    niche = config.get("niche", "unknown")
    console.print(f"\n[bold]Running full pipeline for niche: [cyan]{niche}[/cyan][/bold]")

    scrape_ok = run_scrape()
    if not scrape_ok:
        console.print("\n[yellow]Scrape failed — generator will use existing data if available[/yellow]")

    generate_ok = run_generate()
    if not generate_ok:
        console.print("\n[yellow]Generation failed — renderer will use existing scripts if available[/yellow]")

    render_ok = run_render()

    # Summary
    console.print("\n" + "=" * 40)
    console.print("[bold]Pipeline Summary[/bold]")
    for label, ok in [("Scrape", scrape_ok), ("Generate", generate_ok), ("Render", render_ok)]:
        status = "[green]OK[/green]" if ok else "[red]FAILED[/red]"
        console.print(f"  {label}: {status}")
    console.print()


MENU = {
    "1": ("★ Smart pipeline (analyze → scrape → generate → render)", run_smart_pipeline),
    "2": ("Quick pipeline (scrape → generate → render, no analysis)", run_full),
    "3": ("Scrape only (Phase 1)", run_scrape),
    "4": ("Generate only (Phase 2)", run_generate),
    "5": ("Render only (Phase 3)", run_render),
    "6": ("Publish (Phase 4 — interactive)", lambda: _run_module("src.publishers.tiktok_publisher")),
    "7": ("Mission Control (web dashboard)", lambda: _run_module("src.dashboard")),
    "8": ("Scrape products (Kalodata)", run_scrape_products),
    "9": ("Full product pipeline (products → images → render)", run_product_pipeline),
    "10": ("Generate scene images (Nano Banana Pro)", run_generate_images),
    "11": ("Generate video clips (Higgsfield)", run_generate_clips),
    "12": ("Analyze videos (Video Analyzer)", lambda: _run_module("src.analyzers")),
    "13": ("Generate Style Bible only", lambda: (
        __import__("src.analyzers.style_bible", fromlist=["generate_style_bible"]).generate_style_bible()
    )),
    "14": ("Download top videos for analysis", lambda: (
        __import__("src.analyzers.video_downloader", fromlist=["download_top_videos"]).download_top_videos()
    )),
    "15": ("Niche Radar (scan & score niches)", lambda: _run_module("src.scrapers.niche_radar")),
    "16": ("Check pipeline assets", _check_assets),
    "q": ("Quit", None),
}


def main():
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]TikTok Content Factory[/bold cyan]  [dim]Pipeline Runner[/dim]",
            border_style="cyan",
        )
    )

    config = load_pipeline_config()
    console.print(f"  [dim]Niche: {config.get('niche', 'not set')}[/dim]")
    console.print()

    for key, (label, _) in MENU.items():
        style = "dim" if key == "q" else "white"
        console.print(f"  [{style}][bold]{key}[/bold]) {label}[/{style}]")

    console.print()
    choice = console.input("[bold cyan]Pick an option:[/bold cyan] ").strip()

    if choice not in MENU or choice == "q":
        console.print("[dim]Bye![/dim]")
        return

    label, action = MENU[choice]
    console.print(f"\n[bold]Running:[/bold] {label}")
    action()


if __name__ == "__main__":
    main()
