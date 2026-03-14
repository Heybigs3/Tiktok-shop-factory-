"""analyzer_service.py — Data layer for the Analyze dashboard page.

Loads style bible, per-video analyses, and comparison reports
for display on the dashboard.
"""

import json
from pathlib import Path

from src.analyzers.comparison import (
    load_comparison_report,
    load_rendered_analyses,
    load_scraped_analyses,
)
from src.analyzers.frame_extractor import get_video_id
from src.utils.config import (
    DATA_ANALYSIS_DIR,
    DATA_STYLE_BIBLES_DIR,
    OUTPUT_DIR,
    VIDEOS_DIR,
    load_pipeline_config,
)


# TODO: Accept account_id, use account-scoped paths
def get_style_bible() -> dict | None:
    """Load the current style bible as a dict."""
    config = load_pipeline_config()
    niche = config.get("analyzer", {}).get(
        "style_bible_niche", config.get("niche", "general")
    )
    json_path = DATA_STYLE_BIBLES_DIR / f"{niche}_style_bible.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# TODO: Accept account_id, use account-scoped paths
def get_comparison_report() -> dict | None:
    """Load the latest comparison report."""
    return load_comparison_report()


def _video_info(directory: Path) -> list[dict]:
    """Get basic info about video files in a directory."""
    if not directory.exists():
        return []
    videos = []
    for f in sorted(directory.glob("*.mp4")):
        vid = get_video_id(f)
        videos.append({
            "filename": f.name,
            "video_id": vid,
            "size_mb": f.stat().st_size / (1024 * 1024),
        })
    return videos


def get_scraped_videos_info() -> list[dict]:
    """Info about scraped video files."""
    return _video_info(VIDEOS_DIR)


def get_rendered_videos_info() -> list[dict]:
    """Info about our rendered video files."""
    return _video_info(OUTPUT_DIR)


def get_analysis_stats() -> dict:
    """Get aggregate stats for the Analyze page header."""
    scraped = load_scraped_analyses()
    rendered = load_rendered_analyses()
    report = load_comparison_report()

    scraped_scores = [a.get("overall_quality_score", 0) for a in scraped if a.get("overall_quality_score")]
    rendered_scores = [a.get("overall_quality_score", 0) for a in rendered if a.get("overall_quality_score")]

    return {
        "scraped_count": len(scraped),
        "rendered_count": len(rendered),
        "scraped_avg_score": round(sum(scraped_scores) / len(scraped_scores)) if scraped_scores else 0,
        "rendered_avg_score": round(sum(rendered_scores) / len(rendered_scores)) if rendered_scores else 0,
        "num_gaps": len(report.get("gaps", [])) if report else 0,
        "has_report": report is not None,
        "has_style_bible": get_style_bible() is not None,
    }


def get_scraped_analysis_details() -> list[dict]:
    """Load scraped analyses with key fields for display."""
    return _format_analyses(load_scraped_analyses())


def get_rendered_analysis_details() -> list[dict]:
    """Load rendered analyses with key fields for display."""
    return _format_analyses(load_rendered_analyses())


def _format_analyses(analyses: list[dict]) -> list[dict]:
    """Extract display-friendly fields from analysis dicts."""
    results = []
    for a in analyses:
        results.append({
            "video_id": a.get("video_id", "?"),
            "hook_type": a.get("hook", {}).get("type", "?"),
            "hook_text": a.get("hook", {}).get("text", "")[:60],
            "hook_duration": a.get("hook", {}).get("duration_s", 0),
            "num_cuts": a.get("structure", {}).get("num_cuts", 0),
            "duration": a.get("structure", {}).get("total_duration_s", 0),
            "avg_cut": a.get("structure", {}).get("avg_cut_duration_s", 0),
            "dominant_color": a.get("color_palette", {}).get("dominant", ""),
            "accent_color": a.get("color_palette", {}).get("accent", ""),
            "has_music": a.get("audio", {}).get("has_music", False),
            "has_voiceover": a.get("audio", {}).get("has_voiceover", False),
            "cta_type": a.get("cta", {}).get("type", "?"),
            "quality_score": a.get("overall_quality_score", 0),
            "engagement_factors": a.get("engagement_factors", [])[:3],
        })
    return results
