"""services.py — Data layer for the dashboard.

Wraps existing data_io/config functions and adds script/video matching.
All path-dependent functions accept an optional account_id parameter
for multi-account support.
"""

import os
from datetime import datetime
from pathlib import Path

from src.utils.config import (
    DATA_RAW_DIR,
    DATA_PROCESSED_DIR,
    DATA_SCRIPTS_DIR,
    OUTPUT_DIR,
    check_api_keys,
    load_pipeline_config,
)
from src.utils.data_io import list_data_files, load_json
from src.renderers.video_builder import COLOR_THEMES, calculate_timing
from src.dashboard.accounts import get_account_paths, get_account_config


# ── Path helper ─────────────────────────────────────────────────────────────

def _paths(account_id: str = "default") -> dict[str, Path]:
    """Resolve dirs for the given account."""
    return get_account_paths(account_id)


# ── Video + Script matching ──────────────────────────────────────────────────

def list_videos(account_id: str = "default") -> list[dict]:
    """List all rendered MP4 videos with metadata."""
    output_dir = _paths(account_id)["output_dir"]
    if not output_dir.exists():
        return []

    videos = []
    for path in sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        size_bytes = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime)

        # Parse filename: {script_id_prefix}_{source_type}.mp4
        stem = path.stem  # e.g. "2285a3cf_trending"
        parts = stem.rsplit("_", 1)
        script_prefix = parts[0] if len(parts) == 2 else stem
        source_type = parts[1] if len(parts) == 2 else "unknown"

        videos.append({
            "filename": path.name,
            "path": path,
            "script_prefix": script_prefix,
            "source_type": source_type,
            "size_bytes": size_bytes,
            "size_display": _format_size(size_bytes),
            "date": mtime.strftime("%Y-%m-%d %H:%M"),
            "mtime": mtime,
        })

    return videos


def list_all_scripts(account_id: str = "default") -> list[dict]:
    """Load scripts from ALL script files, deduped by script_id (newest first)."""
    scripts_dir = _paths(account_id)["data_scripts_dir"]
    files = list_data_files(scripts_dir, "scripts")
    if not files:
        return []

    seen_ids: set[str] = set()
    all_scripts: list[dict] = []

    for f in files:  # Already newest-first from list_data_files
        data = load_json(f)
        if not isinstance(data, list):
            continue
        for script in data:
            sid = script.get("script_id", "")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                script["_mood"] = _get_mood(script)
                script["_theme"] = _get_theme_colors(script)
                script["_timing"] = calculate_timing(script)
                script["_hashtags"] = script.get("suggested_hashtags", [])
                script["_source_file"] = f.name
                all_scripts.append(script)

    return all_scripts


def match_scripts_to_videos(account_id: str = "default") -> list[dict]:
    """Match videos to their source scripts. Returns enriched video dicts."""
    videos = list_videos(account_id)
    scripts = list_all_scripts(account_id)

    # Build lookup: first 8 chars of script_id → script
    script_lookup: dict[str, dict] = {}
    for s in scripts:
        sid = s.get("script_id", "")
        if sid:
            script_lookup[sid[:8]] = s

    for video in videos:
        prefix = video["script_prefix"]
        script = script_lookup.get(prefix)
        if script:
            video["script"] = script
            video["mood"] = script["_mood"]
            video["theme"] = script["_theme"]
        else:
            video["script"] = None
            video["mood"] = "default"
            video["theme"] = COLOR_THEMES["default"]

    return videos


def get_unrendered_scripts(account_id: str = "default") -> list[dict]:
    """Find scripts that don't have a corresponding video file."""
    videos = list_videos(account_id)
    scripts = list_all_scripts(account_id)

    rendered_prefixes = {v["script_prefix"] for v in videos}

    unrendered = []
    for s in scripts:
        sid = s.get("script_id", "")
        if sid and sid[:8] not in rendered_prefixes:
            unrendered.append(s)

    return unrendered


def get_pipeline_status(account_id: str = "default") -> dict:
    """Get status info for each pipeline phase."""
    paths = _paths(account_id)
    phases = {
        "scrape": {
            "label": "Scrape",
            "description": "TikTok trends & ads",
            "dir": paths["data_raw_dir"],
            "prefix": "",
        },
        "generate": {
            "label": "Generate",
            "description": "AI scripts from hooks",
            "dir": paths["data_scripts_dir"],
            "prefix": "scripts",
        },
        "render": {
            "label": "Render",
            "description": "FFmpeg video output",
            "dir": paths["output_dir"],
            "prefix": "",
        },
        "publish": {
            "label": "Publish",
            "description": "TikTok upload",
            "dir": None,
            "prefix": "",
        },
    }

    status = {}
    for phase_id, info in phases.items():
        phase_data = {
            "label": info["label"],
            "description": info["description"],
            "file_count": 0,
            "last_run": None,
        }

        if info["dir"] and info["dir"].exists():
            if phase_id == "render":
                files = list(info["dir"].glob("*.mp4"))
            else:
                files = list_data_files(info["dir"], info["prefix"])

            phase_data["file_count"] = len(files)

            if files:
                newest = max(files, key=lambda f: f.stat().st_mtime)
                mtime = datetime.fromtimestamp(newest.stat().st_mtime)
                phase_data["last_run"] = mtime.strftime("%Y-%m-%d %H:%M")

        status[phase_id] = phase_data

    return status


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_size(size_bytes: int) -> str:
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes > 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def _get_mood(script: dict) -> str:
    hints = script.get("visual_hints", {})
    if isinstance(hints, dict):
        mood = hints.get("mood", "")
        if mood in COLOR_THEMES:
            return mood
    # Fallback from source_type
    source_map = {"trending": "energetic", "ad": "warm", "mixed": "cool"}
    return source_map.get(script.get("source_type", ""), "default")


def _get_theme_colors(script: dict) -> dict:
    mood = _get_mood(script)
    return COLOR_THEMES.get(mood, COLOR_THEMES["default"])


def get_studio_stats(account_id: str = "default") -> dict:
    """Aggregate KPI stats for the Studio page hero row."""
    videos = list_videos(account_id)
    scripts = list_all_scripts(account_id)
    unrendered = get_unrendered_scripts(account_id)
    total_size = sum(v["size_bytes"] for v in videos)
    return {
        "total_videos": len(videos),
        "total_scripts": len(scripts),
        "unrendered": len(unrendered),
        "storage_used": _format_size(total_size),
    }


def clear_videos(account_id: str = "default") -> int:
    """Delete all .mp4 files in the account's output dir. Returns count of deleted files."""
    output_dir = _paths(account_id)["output_dir"]
    if not output_dir.exists():
        return 0

    deleted = 0
    for path in output_dir.glob("*.mp4"):
        try:
            path.unlink()
            deleted += 1
        except OSError:
            continue

    return deleted


def hex_to_css(hex_str: str) -> str:
    """Convert '0x1a1a2e' format to '#1a1a2e' CSS format."""
    return "#" + hex_str.replace("0x", "")
