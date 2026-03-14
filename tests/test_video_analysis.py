"""Tests for src.analyzers.video_analysis and src.analyzers.style_bible."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.analyzers.video_analysis import _build_analysis_prompt, _encode_frames, analyze_video
from src.analyzers.style_bible import _aggregate_stats, generate_style_bible, load_style_bible


# ── Shared fixtures ──

@pytest.fixture
def sample_analysis_json():
    """Single video analysis matching the output schema."""
    return {
        "video_id": "abc123def456",
        "hook": {"text": "Stop scrolling if you have acne", "duration_s": 2.1, "type": "pattern_interrupt"},
        "structure": {"total_duration_s": 22, "num_cuts": 8, "avg_cut_duration_s": 2.75},
        "text_overlays": [
            {"text": "This routine changed everything", "position": "upper_center", "appears_at": 0.0, "font_size_estimate": "large"}
        ],
        "color_palette": {"dominant": "#F5E6D3", "accent": "#FF6B6B", "text": "#FFFFFF"},
        "audio": {"has_music": True, "has_voiceover": True, "energy_pattern": "spike-dip-steady-spike"},
        "cta": {"text": "Follow for part 2", "position": "center_lower", "type": "follow"},
        "engagement_factors": ["pattern_interrupt", "social_proof", "curiosity"],
        "overall_quality_score": 85,
    }


@pytest.fixture
def sample_transcript():
    """Whisper transcript dict."""
    return {
        "text": "Stop scrolling if you have acne. This routine changed everything.",
        "segments": [
            {"start": 0.0, "end": 2.5, "text": "Stop scrolling if you have acne."},
            {"start": 2.5, "end": 8.0, "text": "This routine changed everything."},
        ],
    }


@pytest.fixture
def sample_metadata():
    """Video metadata dict."""
    return {"duration": 22.0, "width": 1080, "height": 1920, "fps": 30.0, "codec": "h264"}


# ── Frame encoding ──

def test_encode_frames_with_tiny_images(tmp_path):
    """Encodes small test images to base64."""
    # Create tiny test JPEG files
    from PIL import Image
    frames = []
    for i in range(3):
        p = tmp_path / f"frame_{i}.jpg"
        img = Image.new("RGB", (100, 100), color=(i * 50, 100, 200))
        img.save(p, "JPEG")
        frames.append(p)

    encoded = _encode_frames(frames)
    assert len(encoded) == 3
    assert encoded[0]["type"] == "image"
    assert encoded[0]["source"]["media_type"] == "image/jpeg"
    assert len(encoded[0]["source"]["data"]) > 0  # Base64 string is non-empty


def test_encode_frames_resizes_large_images(tmp_path):
    """Images wider than 512px are resized down."""
    from PIL import Image
    p = tmp_path / "wide.jpg"
    img = Image.new("RGB", (1920, 1080), color=(255, 0, 0))
    img.save(p, "JPEG")

    encoded = _encode_frames([p], max_width=512)
    assert len(encoded) == 1
    # The encoded image should be smaller than original
    # (We can't easily check pixel dimensions from base64, but we can check it succeeded)
    assert encoded[0]["source"]["data"]


def test_encode_frames_skips_invalid(tmp_path):
    """Skips files that can't be opened as images."""
    p = tmp_path / "bad.jpg"
    p.write_text("not an image")

    encoded = _encode_frames([p])
    assert len(encoded) == 0


def test_encode_frames_empty_list():
    """Returns empty list for empty input."""
    assert _encode_frames([]) == []


# ── Analysis prompt building ──

def test_build_analysis_prompt_with_transcript(sample_transcript, sample_metadata):
    """Prompt includes transcript text and timed segments."""
    prompt = _build_analysis_prompt("abc123", sample_transcript, sample_metadata)
    assert "abc123" in prompt
    assert "Stop scrolling" in prompt
    assert "22.0s" in prompt
    assert "1080x1920" in prompt


def test_build_analysis_prompt_no_transcript(sample_metadata):
    """Prompt handles missing transcript gracefully."""
    prompt = _build_analysis_prompt("abc123", None, sample_metadata)
    assert "not available" in prompt
    assert "abc123" in prompt


def test_build_analysis_prompt_empty_transcript(sample_metadata):
    """Prompt handles empty transcript dict."""
    prompt = _build_analysis_prompt("abc123", {"text": "", "segments": []}, sample_metadata)
    assert "not available" in prompt


# ── Video analysis (mocked API) ──

@patch("src.analyzers.video_analysis.ANTHROPIC_API_KEY", "test-key")
@patch("src.analyzers.video_analysis.load_pipeline_config")
@patch("src.analyzers.video_analysis._encode_frames")
@patch("src.analyzers.video_analysis.anthropic.Anthropic")
def test_analyze_video_returns_parsed_json(
    mock_client_cls, mock_encode, mock_config, sample_analysis_json, sample_metadata, tmp_path
):
    """Parses Claude's JSON response into analysis dict."""
    mock_config.return_value = {"analyzer": {"analysis_model": "claude-haiku-4-5-20251001"}}
    mock_encode.return_value = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "abc"}}]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(sample_analysis_json))]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=200)
    mock_client_cls.return_value.messages.create.return_value = mock_response

    frames = [tmp_path / "frame.jpg"]
    result = analyze_video("abc123def456", frames, None, sample_metadata)

    assert result is not None
    assert result["video_id"] == "abc123def456"
    assert result["hook"]["type"] == "pattern_interrupt"
    assert result["overall_quality_score"] == 85


@patch("src.analyzers.video_analysis.ANTHROPIC_API_KEY", "")
def test_analyze_video_no_api_key(sample_metadata, tmp_path):
    """Returns None when API key is not set."""
    result = analyze_video("abc123", [tmp_path / "f.jpg"], None, sample_metadata)
    assert result is None


def test_analyze_video_no_frames(sample_metadata):
    """Returns None when no frames are provided."""
    result = analyze_video("abc123", [], None, sample_metadata)
    assert result is None


# ── Style Bible aggregation ──

def test_aggregate_stats_empty():
    """Returns fallback message for empty analyses."""
    result = _aggregate_stats([])
    assert "No analyses" in result


def test_aggregate_stats_with_data(sample_analysis_json):
    """Aggregates stats from multiple analyses."""
    analyses = [sample_analysis_json, sample_analysis_json]
    result = _aggregate_stats(analyses)

    assert "Hook Type Distribution" in result
    assert "pattern_interrupt" in result
    assert "Audio" in result
    assert "Engagement Factors" in result


# ── Style Bible loading ──

def test_load_style_bible_no_file():
    """Returns None when no Style Bible file exists."""
    with patch("src.analyzers.style_bible.DATA_STYLE_BIBLES_DIR", Path("/nonexistent")):
        result = load_style_bible("test_niche")
    assert result is None


def test_load_style_bible_reads_json(tmp_path):
    """Loads and formats a Style Bible from JSON."""
    sb = {
        "hook_patterns": {
            "top_types": [{"type": "question", "frequency_pct": 40}],
            "avg_duration_s": 2.5,
        },
        "visual_style": {
            "dominant_colors": ["#F5E6D3"],
        },
        "engagement_factors": [
            {"factor": "social_proof", "frequency_pct": 60},
        ],
        "top_recommendations": ["Use questions as hooks"],
    }
    json_path = tmp_path / "skincare_style_bible.json"
    json_path.write_text(json.dumps(sb), encoding="utf-8")

    with patch("src.analyzers.style_bible.DATA_STYLE_BIBLES_DIR", tmp_path):
        result = load_style_bible("skincare")

    assert result is not None
    assert "question" in result
    assert "social_proof" in result
    assert "Use questions as hooks" in result


# ── Style Bible generation (mocked API) ──

@patch("src.analyzers.style_bible.ANTHROPIC_API_KEY", "")
def test_generate_style_bible_no_api_key():
    """Returns None when API key is not set."""
    result = generate_style_bible([{"hook": {"type": "test"}}])
    assert result is None


@patch("src.analyzers.style_bible.ANTHROPIC_API_KEY", "test-key")
def test_generate_style_bible_no_analyses():
    """Returns None when no analyses are provided."""
    result = generate_style_bible([])
    assert result is None
