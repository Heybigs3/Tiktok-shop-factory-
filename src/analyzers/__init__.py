"""
analyzers — Video analysis pipeline for TikTok content intelligence.

Extracts frames + transcripts from TikTok videos, analyzes via Claude's
multimodal API, and synthesizes a Style Bible for the script generator.

Usage:
  python -m src.analyzers
"""

from src.analyzers.frame_extractor import (
    extract_frames,
    extract_scene_frames,
    get_video_id,
    get_video_metadata,
)
from src.analyzers.style_bible import generate_style_bible, load_style_bible
from src.analyzers.transcriber import transcribe
from src.analyzers.video_analysis import analyze_video
from src.analyzers.video_downloader import download_top_videos
from src.analyzers.comparison import compare_videos, load_comparison_report
from src.analyzers.style_overrides import get_render_overrides, get_prompt_overrides

__all__ = [
    "extract_frames",
    "extract_scene_frames",
    "get_video_id",
    "get_video_metadata",
    "transcribe",
    "analyze_video",
    "generate_style_bible",
    "load_style_bible",
    "download_top_videos",
    "compare_videos",
    "load_comparison_report",
    "get_render_overrides",
    "get_prompt_overrides",
]
