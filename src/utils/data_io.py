"""
data_io.py — Helpers for saving and loading JSON data with timestamps.

Every scrape saves a timestamped JSON file so you can:
  - Track what was scraped and when
  - Compare trends over time
  - Never accidentally overwrite previous data

Usage:
  from src.utils.data_io import save_json, load_json, list_data_files

  save_json(data, "hashtags", config.DATA_RAW_DIR)
  # Creates: data/raw/hashtags_2026-03-08_143022.json
"""

import json
from datetime import datetime
from pathlib import Path

from rich import print as rprint


def save_json(data: list | dict, prefix: str, directory: Path) -> Path:
    """
    Save data as a timestamped JSON file.

    Args:
        data: The Python object to serialize (list or dict)
        prefix: Descriptive name for the file (e.g., "trending_videos")
        directory: Which folder to save into (e.g., DATA_RAW_DIR)

    Returns:
        Path to the saved file

    Example:
        path = save_json(videos, "trending_videos", DATA_RAW_DIR)
        # → data/raw/trending_videos_2026-03-08_143022.json
    """
    # Create a timestamp string: YYYY-MM-DD_HHMMSS
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.json"
    filepath = directory / filename

    # Ensure the directory exists
    directory.mkdir(parents=True, exist_ok=True)

    # Write JSON with pretty formatting (indent=2) for readability
    # ensure_ascii=False lets emojis and non-English text save correctly
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    rprint(f"[green]Saved:[/green] {filepath} ({len(data) if isinstance(data, list) else 1} items)")
    return filepath


def load_json(filepath: Path) -> list | dict:
    """
    Load and parse a JSON file.

    Args:
        filepath: Path to the JSON file

    Returns:
        Parsed Python object (list or dict)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_data_files(directory: Path, prefix: str = "") -> list[Path]:
    """
    List all JSON files in a directory, optionally filtered by prefix.
    Returns files sorted newest-first (by filename timestamp).

    Args:
        directory: Folder to scan
        prefix: Optional filter — only return files starting with this string

    Returns:
        List of Path objects, newest first
    """
    if not directory.exists():
        return []

    files = sorted(
        [f for f in directory.glob("*.json") if f.name.startswith(prefix or "")],
        reverse=True,  # newest first (timestamp in filename = alphabetical = chronological)
    )
    return files


def load_latest(directory: Path, prefix: str) -> list | dict | None:
    """
    Load the most recent JSON file matching a prefix.

    Args:
        directory: Folder to search
        prefix: File prefix to match (e.g., "trending_videos")

    Returns:
        Parsed data, or None if no matching file exists
    """
    files = list_data_files(directory, prefix)
    if not files:
        rprint(f"[yellow]No files found matching '{prefix}' in {directory}[/yellow]")
        return None

    rprint(f"[blue]Loading latest:[/blue] {files[0].name}")
    return load_json(files[0])


# ── Quick test: run this file directly ──
if __name__ == "__main__":
    from src.utils.config import DATA_RAW_DIR

    # Save a test file
    test_data = [{"test": True, "message": "data_io is working!"}]
    path = save_json(test_data, "test", DATA_RAW_DIR)

    # Load it back
    loaded = load_json(path)
    rprint("[bold]Loaded back:[/bold]", loaded)

    # List files
    rprint("[bold]Files in raw/:[/bold]", list_data_files(DATA_RAW_DIR))
