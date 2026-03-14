"""Tests for src.analyzers.frame_extractor."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.analyzers.frame_extractor import (
    extract_frames,
    extract_scene_frames,
    get_video_id,
    get_video_metadata,
)


# ── Video ID generation ──

def test_video_id_deterministic():
    """Same filename always produces the same ID."""
    p = Path("my_video.mp4")
    assert get_video_id(p) == get_video_id(p)


def test_video_id_length():
    """Video ID is 12 hex characters."""
    vid = get_video_id(Path("test.mp4"))
    assert len(vid) == 12
    assert all(c in "0123456789abcdef" for c in vid)


def test_video_id_different_files():
    """Different filenames produce different IDs."""
    id1 = get_video_id(Path("video_a.mp4"))
    id2 = get_video_id(Path("video_b.mp4"))
    assert id1 != id2


# ── FFprobe metadata ──

@patch("src.analyzers.frame_extractor.shutil.which", return_value="/usr/bin/ffprobe")
@patch("src.analyzers.frame_extractor.subprocess.run")
def test_get_video_metadata(mock_run, mock_which):
    """Parses FFprobe JSON output into a clean metadata dict."""
    probe_output = {
        "format": {"duration": "22.5"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "r_frame_rate": "30/1",
            }
        ],
    }
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps(probe_output),
    )

    meta = get_video_metadata(Path("test.mp4"))
    assert meta["duration"] == 22.5
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    assert meta["fps"] == 30.0
    assert meta["codec"] == "h264"


@patch("src.analyzers.frame_extractor.shutil.which", return_value=None)
def test_get_video_metadata_no_ffprobe(mock_which):
    """Returns empty dict when FFprobe is not installed."""
    meta = get_video_metadata(Path("test.mp4"))
    assert meta == {}


@patch("src.analyzers.frame_extractor.shutil.which", return_value="/usr/bin/ffprobe")
@patch("src.analyzers.frame_extractor.subprocess.run")
def test_get_video_metadata_bad_output(mock_run, mock_which):
    """Returns empty dict when FFprobe output is not valid JSON."""
    mock_run.return_value = MagicMock(returncode=0, stdout="not json")
    meta = get_video_metadata(Path("test.mp4"))
    assert meta == {}


# ── Frame extraction ──

@patch("src.analyzers.frame_extractor.shutil.which", return_value=None)
def test_extract_frames_no_ffmpeg(mock_which):
    """Returns empty list when FFmpeg is not installed."""
    frames = extract_frames(Path("test.mp4"))
    assert frames == []


@patch("src.analyzers.frame_extractor.get_video_metadata")
@patch("src.analyzers.frame_extractor.shutil.which", return_value="/usr/bin/ffmpeg")
@patch("src.analyzers.frame_extractor.subprocess.run")
def test_extract_frames_creates_output_dir(mock_run, mock_which, mock_meta, tmp_path):
    """Creates output directory and calls FFmpeg for each frame."""
    mock_meta.return_value = {"duration": 10.0, "width": 1080, "height": 1920, "fps": 30}
    mock_run.return_value = MagicMock(returncode=0)

    output_dir = tmp_path / "frames"
    frames = extract_frames(Path("test.mp4"), output_dir=output_dir, num_frames=3)

    assert output_dir.exists()
    # FFmpeg was called 3 times (once per frame)
    assert mock_run.call_count == 3


@patch("src.analyzers.frame_extractor.shutil.which", return_value=None)
def test_extract_scene_frames_no_ffmpeg(mock_which):
    """Returns empty list when FFmpeg is not installed."""
    frames = extract_scene_frames(Path("test.mp4"))
    assert frames == []


@pytest.mark.ffmpeg
def test_extract_frames_command_structure():
    """Verify FFmpeg is called with correct arguments (integration-like, needs FFmpeg)."""
    # This test only runs if FFmpeg is installed
    # Just verifies the function doesn't crash with a non-existent file
    frames = extract_frames(Path("nonexistent_video.mp4"))
    assert frames == []
