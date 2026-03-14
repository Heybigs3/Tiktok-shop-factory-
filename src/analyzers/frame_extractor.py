"""
frame_extractor.py — FFmpeg-based frame extraction from .mp4 files.

Extracts evenly-spaced or scene-change frames for Claude's multimodal analysis.
Frames saved to data/frames/{video_id}/ where video_id is a SHA-256 hash prefix.

Usage:
  python -m src.analyzers  # menu option 2
"""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from rich import print as rprint

from src.utils.config import DATA_FRAMES_DIR


def get_video_id(video_path: Path) -> str:
    """Generate a deterministic video ID from the filename (first 12 chars of SHA-256)."""
    name = video_path.name.encode("utf-8")
    return hashlib.sha256(name).hexdigest()[:12]


def get_video_metadata(video_path: Path) -> dict:
    """
    Get video metadata via FFprobe.

    Returns:
        Dict with duration, width, height, fps, codec keys.
        Returns empty dict if FFprobe fails.
    """
    if not shutil.which("ffprobe"):
        rprint("[red]FFprobe not found — install FFmpeg[/red]")
        return {}

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        rprint(f"[red]FFprobe failed for {video_path.name}[/red]")
        return {}

    if result.returncode != 0:
        return {}

    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    # Find the video stream
    video_stream = None
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        return {}

    # Parse FPS from r_frame_rate (e.g. "30/1")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    try:
        num, den = fps_str.split("/")
        fps = round(int(num) / int(den), 2)
    except (ValueError, ZeroDivisionError):
        fps = 30.0

    duration = float(probe.get("format", {}).get("duration", 0))

    return {
        "duration": duration,
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": fps,
        "codec": video_stream.get("codec_name", "unknown"),
    }


def extract_frames(video_path: Path, output_dir: Path | None = None, num_frames: int = 5) -> list[Path]:
    """
    Extract N evenly-spaced frames from a video.

    Args:
        video_path: Path to the .mp4 file
        output_dir: Where to save frames (defaults to data/frames/{video_id}/)
        num_frames: Number of frames to extract

    Returns:
        List of paths to extracted frame images.
    """
    if not shutil.which("ffmpeg"):
        rprint("[red]FFmpeg not found — install FFmpeg[/red]")
        return []

    video_id = get_video_id(video_path)
    if output_dir is None:
        output_dir = DATA_FRAMES_DIR / video_id
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = get_video_metadata(video_path)
    duration = metadata.get("duration", 0)
    if duration <= 0:
        rprint(f"[red]Cannot determine duration for {video_path.name}[/red]")
        return []

    # Calculate timestamps for evenly-spaced frames
    # Avoid the very start (0s) and end to get meaningful frames
    margin = min(0.5, duration * 0.05)
    interval = (duration - 2 * margin) / max(num_frames - 1, 1)
    timestamps = [margin + i * interval for i in range(num_frames)]

    frames = []
    for i, ts in enumerate(timestamps, 1):
        frame_path = output_dir / f"frame_{i:03d}.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{ts:.2f}",
                 "-i", str(video_path),
                 "-frames:v", "1", "-q:v", "2",
                 str(frame_path)],
                capture_output=True, timeout=15,
            )
            if frame_path.exists() and frame_path.stat().st_size > 0:
                frames.append(frame_path)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            rprint(f"[yellow]Failed to extract frame at {ts:.1f}s[/yellow]")

    rprint(f"[green]Extracted {len(frames)} frames from {video_path.name}[/green]")
    return frames


def extract_scene_frames(video_path: Path, output_dir: Path | None = None, threshold: float = 0.3) -> list[Path]:
    """
    Extract frames at scene change boundaries using FFmpeg scene detection.

    Args:
        video_path: Path to the .mp4 file
        output_dir: Where to save frames
        threshold: Scene change sensitivity (0.0-1.0, lower = more sensitive)

    Returns:
        List of paths to extracted frame images.
    """
    if not shutil.which("ffmpeg"):
        rprint("[red]FFmpeg not found — install FFmpeg[/red]")
        return []

    video_id = get_video_id(video_path)
    if output_dir is None:
        output_dir = DATA_FRAMES_DIR / video_id
    output_dir.mkdir(parents=True, exist_ok=True)

    frame_pattern = str(output_dir / "scene_%03d.jpg")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path),
             "-vf", f"select='gt(scene,{threshold})',showinfo",
             "-vsync", "vfr", "-q:v", "2",
             frame_pattern],
            capture_output=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        rprint(f"[yellow]Scene detection failed for {video_path.name}[/yellow]")
        return []

    frames = sorted(output_dir.glob("scene_*.jpg"))
    rprint(f"[green]Detected {len(frames)} scene changes in {video_path.name}[/green]")

    # If scene detection found too few or too many, fall back to even spacing
    if len(frames) < 2:
        rprint("[yellow]Few scene changes detected — falling back to even spacing[/yellow]")
        return extract_frames(video_path, output_dir)

    return frames
