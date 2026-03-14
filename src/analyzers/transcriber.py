"""
transcriber.py — Audio transcription via Whisper CLI subprocess.

Runs Whisper as a subprocess (NOT as a Python import) to avoid the 2GB
torch dependency in our main virtualenv. Falls back gracefully if
whisper is not installed.

Usage:
  python -m src.analyzers  # menu option 3
"""

import json
import shutil
import subprocess
from pathlib import Path

from rich import print as rprint

from src.utils.config import DATA_TRANSCRIPTS_DIR, load_pipeline_config


def _whisper_available() -> bool:
    """Check if Whisper CLI is available."""
    return shutil.which("whisper") is not None


def extract_audio(video_path: Path, output_path: Path | None = None) -> Path | None:
    """
    Extract audio from a video file as WAV using FFmpeg.

    Returns:
        Path to extracted WAV file, or None on failure.
    """
    if not shutil.which("ffmpeg"):
        rprint("[red]FFmpeg not found — install FFmpeg[/red]")
        return None

    if output_path is None:
        output_path = DATA_TRANSCRIPTS_DIR / f"{video_path.stem}.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path),
             "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
             str(output_path)],
            capture_output=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        rprint(f"[red]Audio extraction failed for {video_path.name}[/red]")
        return None

    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    return None


def transcribe(video_path: Path) -> dict | None:
    """
    Transcribe a video's audio using Whisper CLI.

    Returns:
        Dict with "text" (full transcript) and "segments" (timed segments),
        or None if transcription fails or Whisper is not installed.
    """
    if not _whisper_available():
        rprint("[yellow]Whisper not installed — skipping transcription[/yellow]")
        rprint("[dim]Install with: pip install openai-whisper[/dim]")
        return None

    # Extract audio first
    audio_path = extract_audio(video_path)
    if not audio_path:
        return None

    config = load_pipeline_config()
    model = config.get("analyzer", {}).get("whisper_model", "base")

    # Output directory for Whisper JSON
    output_dir = DATA_TRANSCRIPTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        rprint(f"[blue]Transcribing {video_path.name} with Whisper ({model})…[/blue]")
        subprocess.run(
            ["whisper", str(audio_path),
             "--model", model,
             "--output_format", "json",
             "--output_dir", str(output_dir)],
            capture_output=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        rprint(f"[red]Whisper timed out for {video_path.name}[/red]")
        return None
    except FileNotFoundError:
        rprint("[red]Whisper command not found[/red]")
        return None

    # Load Whisper's JSON output
    json_path = output_dir / f"{audio_path.stem}.json"
    if not json_path.exists():
        rprint(f"[yellow]Whisper produced no output for {video_path.name}[/yellow]")
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            result = json.load(f)
    except json.JSONDecodeError:
        rprint(f"[red]Failed to parse Whisper output for {video_path.name}[/red]")
        return None
    finally:
        # Clean up intermediate WAV file
        if audio_path.exists():
            audio_path.unlink()

    transcript = {
        "text": result.get("text", ""),
        "segments": [
            {
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", ""),
            }
            for seg in result.get("segments", [])
        ],
    }

    rprint(f"[green]Transcribed {video_path.name}: {len(transcript['text'])} chars[/green]")
    return transcript
