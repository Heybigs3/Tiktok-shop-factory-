"""
video_analysis.py — Per-video multimodal analysis via Claude API.

Sends extracted frames + transcript to Claude's vision API for structured
analysis of each video's creative strategy.

Usage:
  python -m src.analyzers  # menu option 1 or 5
"""

import base64
import json
import re
from pathlib import Path

import anthropic
from rich import print as rprint

from src.analyzers.prompts import (
    VIDEO_ANALYSIS_SYSTEM_PROMPT,
    VIDEO_ANALYSIS_USER_TEMPLATE,
)
from src.utils.config import ANTHROPIC_API_KEY, DATA_ANALYSIS_DIR, load_pipeline_config
from src.utils.data_io import save_json


def _encode_frames(frame_paths: list[Path], max_width: int = 512) -> list[dict]:
    """
    Read frames, resize to max_width, and base64 encode for Claude API.

    Returns list of Claude API image content blocks.
    """
    import io

    try:
        from PIL import Image
    except ImportError:
        rprint("[red]Pillow not installed — run: pip install Pillow[/red]")
        return []

    encoded = []
    for path in frame_paths:
        try:
            img = Image.open(path)

            # Resize if wider than max_width (cost control)
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            # Encode to JPEG bytes
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            b64 = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")

            encoded.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": b64,
                },
            })
        except Exception as e:
            rprint(f"[yellow]Failed to encode {path.name}: {e}[/yellow]")

    return encoded


def _build_analysis_prompt(video_id: str, transcript: dict | None, metadata: dict) -> str:
    """Construct the user message text with video metadata and transcript."""
    if transcript and transcript.get("text"):
        transcript_section = f"Transcript:\n\"{transcript['text']}\""
        if transcript.get("segments"):
            lines = []
            for seg in transcript["segments"][:20]:  # Cap at 20 segments
                lines.append(f"  [{seg['start']:.1f}s-{seg['end']:.1f}s] {seg['text']}")
            transcript_section += "\n\nTimed segments:\n" + "\n".join(lines)
    else:
        transcript_section = "Transcript: (not available — analyze visuals only)"

    return VIDEO_ANALYSIS_USER_TEMPLATE.format(
        video_id=video_id,
        duration_s=metadata.get("duration", 0),
        width=metadata.get("width", 0),
        height=metadata.get("height", 0),
        fps=metadata.get("fps", 0),
        transcript_section=transcript_section,
    )


def analyze_video(
    video_id: str,
    frames: list[Path],
    transcript: dict | None,
    metadata: dict,
) -> dict | None:
    """
    Send frames + transcript to Claude for structured video analysis.

    Args:
        video_id: Unique identifier for the video
        frames: Paths to extracted frame images
        transcript: Whisper transcript dict, or None
        metadata: Video metadata from FFprobe

    Returns:
        Parsed analysis dict, or None on failure.
    """
    if not ANTHROPIC_API_KEY:
        rprint("[red]ANTHROPIC_API_KEY not set — cannot analyze[/red]")
        return None

    if not frames:
        rprint("[yellow]No frames to analyze[/yellow]")
        return None

    config = load_pipeline_config()
    model = config.get("analyzer", {}).get("analysis_model", "claude-haiku-4-5-20251001")

    # Build content blocks: text prompt + frame images
    prompt_text = _build_analysis_prompt(video_id, transcript, metadata)
    image_blocks = _encode_frames(frames)

    if not image_blocks:
        rprint("[red]No frames could be encoded[/red]")
        return None

    content = [{"type": "text", "text": prompt_text}] + image_blocks

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        rprint(f"[blue]Analyzing video {video_id} ({len(frames)} frames, model: {model})…[/blue]")
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=VIDEO_ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError as e:
        rprint(f"[red]Claude API error: {e}[/red]")
        return None

    raw_text = response.content[0].text
    usage = response.usage
    rprint(f"[dim]Tokens — input: {usage.input_tokens}, output: {usage.output_tokens}[/dim]")

    # Parse JSON response
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]

    try:
        analysis = json.loads(text)
    except json.JSONDecodeError as e:
        rprint(f"[red]Failed to parse analysis JSON: {e}[/red]")
        rprint(f"[dim]Raw response (first 300 chars): {raw_text[:300]}[/dim]")
        return None

    # Ensure video_id is set
    analysis["video_id"] = video_id

    return analysis


def analyze_and_save(
    video_id: str,
    frames: list[Path],
    transcript: dict | None,
    metadata: dict,
) -> dict | None:
    """Analyze a video and save results to data/analysis/."""
    analysis = analyze_video(video_id, frames, transcript, metadata)
    if analysis:
        save_json(analysis, f"analysis_{video_id}", DATA_ANALYSIS_DIR)
        rprint(f"[green]Analysis saved for video {video_id}[/green]")
    return analysis
