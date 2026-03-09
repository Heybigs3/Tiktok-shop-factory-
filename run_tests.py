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
    "6": ("Integration tests (needs API key)", ["pytest", "-m", "integration"]),
    "7": ("Everything (unit + integration)", ["pytest", "-m", ""]),
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
