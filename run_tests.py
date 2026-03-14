"""Interactive test runner — one command to run any tests."""

import subprocess
import sys

from rich.console import Console
from rich.panel import Panel

console = Console()

MENU = {
    "1": ("All unit tests", ["pytest"]),
    "2": ("Templates tests", ["pytest", "tests/test_templates.py"]),
    "3": ("Script parsing tests", ["pytest", "tests/test_parse_scripts.py"]),
    "4": ("Data I/O tests", ["pytest", "tests/test_data_io.py"]),
    "5": ("Video builder tests", ["pytest", "tests/test_video_builder.py"]),
    "6": ("Publisher tests", ["pytest", "tests/test_tiktok_publisher.py", "tests/test_tiktok_api.py", "tests/test_oauth.py"]),
    "7": ("Pipeline config tests", ["pytest", "tests/test_pipeline_config.py"]),
    "8": ("Hook processor tests", ["pytest", "tests/test_hook_processor.py"]),
    "9": ("Dashboard tests", ["pytest", "tests/test_dashboard.py"]),
    "10": ("TTS tests", ["pytest", "tests/test_tts.py"]),
    "11": ("Kalodata scraper tests", ["pytest", "tests/test_kalodata_scraper.py"]),
    "12": ("Image generator tests", ["pytest", "tests/test_image_generator.py"]),
    "13": ("Video generator tests", ["pytest", "tests/test_video_generator.py"]),
    "14": ("Product templates tests", ["pytest", "tests/test_product_templates.py"]),
    "15": ("Frame extractor tests", ["pytest", "tests/test_frame_extractor.py"]),
    "16": ("Transcriber tests", ["pytest", "tests/test_transcriber.py"]),
    "17": ("Video analysis tests", ["pytest", "tests/test_video_analysis.py"]),
    "18": ("Account system tests", ["pytest", "tests/test_accounts.py"]),
    "19": ("Queue service tests", ["pytest", "tests/test_queue_service.py"]),
    "20": ("Product service tests", ["pytest", "tests/test_product_service.py"]),
    "21": ("Video downloader tests", ["pytest", "tests/test_video_downloader.py"]),
    "22": ("Publish service tests", ["pytest", "tests/test_publish_service.py"]),
    "23": ("Comparison tests", ["pytest", "tests/test_comparison.py"]),
    "24": ("Style overrides tests", ["pytest", "tests/test_style_overrides.py"]),
    "25": ("Niche Radar tests", ["pytest", "tests/test_niche_radar.py"]),
    "26": ("Screen recorder tests", ["pytest", "tests/test_screen_recorder.py"]),
    "27": ("Format router tests", ["pytest", "tests/test_format_router.py"]),
    "28": ("Integration tests (needs API key)", ["pytest", "-m", "integration"]),
    "29": ("Everything (unit + integration)", ["pytest", "-m", ""]),
    "q": ("Quit", []),
}


def main():
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]TikTok Factory[/bold cyan]  [dim]Test Runner[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    for key, (label, _) in MENU.items():
        style = "dim" if key == "q" else "white"
        console.print(f"  [{style}][bold]{key}[/bold]) {label}[/{style}]")

    console.print()
    choice = console.input("[bold cyan]Pick a test to run:[/bold cyan] ").strip()

    if choice not in MENU or choice == "q":
        console.print("[dim]Bye![/dim]")
        return

    label, cmd = MENU[choice]
    console.print(f"\n[bold]Running:[/bold] {label}\n")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
