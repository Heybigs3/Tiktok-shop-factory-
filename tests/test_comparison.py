"""Tests for src.analyzers.comparison."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.analyzers.comparison import (
    _summarize_set,
    load_comparison_report,
    load_rendered_analyses,
    load_scraped_analyses,
)


# ── Loading analyses by source ──

@patch("src.analyzers.comparison._get_video_ids")
@patch("src.analyzers.comparison._load_all_analyses")
def test_load_scraped_analyses(mock_load, mock_ids):
    """Returns only analyses matching videos/ directory video IDs."""
    mock_ids.return_value = {"abc123", "def456"}
    mock_load.return_value = {
        "abc123": {"video_id": "abc123", "hook": {"type": "listicle"}},
        "def456": {"video_id": "def456", "hook": {"type": "before_after"}},
        "ghi789": {"video_id": "ghi789", "hook": {"type": "question"}},  # not in scraped
    }
    result = load_scraped_analyses()
    assert len(result) == 2
    video_ids = {a["video_id"] for a in result}
    assert "abc123" in video_ids
    assert "def456" in video_ids
    assert "ghi789" not in video_ids


@patch("src.analyzers.comparison._get_video_ids")
@patch("src.analyzers.comparison._load_all_analyses")
def test_load_rendered_analyses(mock_load, mock_ids):
    """Returns only analyses matching output/videos/ directory video IDs."""
    mock_ids.return_value = {"xyz999"}
    mock_load.return_value = {
        "abc123": {"video_id": "abc123"},
        "xyz999": {"video_id": "xyz999"},
    }
    result = load_rendered_analyses()
    assert len(result) == 1
    assert result[0]["video_id"] == "xyz999"


# ── Summary generation ──

def test_summarize_set_empty():
    """Returns a message when no analyses available."""
    result = _summarize_set([], "TEST")
    assert "No analyses available" in result


def test_summarize_set_with_data():
    """Produces summary with hook, structure, and audio info."""
    analyses = [
        {
            "hook": {"type": "listicle", "duration_s": 2.5},
            "structure": {"total_duration_s": 60, "num_cuts": 15, "avg_cut_duration_s": 4.0},
            "audio": {"has_music": True, "has_voiceover": False},
            "color_palette": {"dominant": "#E8D4D8", "accent": "#FFB6C1"},
            "overall_quality_score": 80,
            "text_overlays": [{"text": "test"}] * 5,
            "engagement_factors": ["authenticity", "music"],
            "cta": {"type": "shop_now"},
        },
        {
            "hook": {"type": "before_after", "duration_s": 3.0},
            "structure": {"total_duration_s": 90, "num_cuts": 20, "avg_cut_duration_s": 4.5},
            "audio": {"has_music": False, "has_voiceover": True},
            "color_palette": {"dominant": "#D9A89F", "accent": "#22DD22"},
            "overall_quality_score": 70,
            "text_overlays": [{"text": "test"}] * 8,
            "engagement_factors": ["before_after", "music"],
            "cta": {"type": "comment"},
        },
    ]
    result = _summarize_set(analyses, "SCRAPED")
    assert "SCRAPED (2 videos)" in result
    assert "listicle" in result
    assert "Music: 1/2" in result


# ── Report loading ──

def test_load_comparison_report_missing():
    """Returns None when no report exists."""
    with patch("src.analyzers.comparison.DATA_ANALYSIS_DIR", Path("/nonexistent")):
        result = load_comparison_report()
        assert result is None


def test_load_comparison_report_exists(tmp_path):
    """Loads and returns existing comparison report."""
    report = {"overall_verdict": "test", "gaps": []}
    report_path = tmp_path / "comparison_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with patch("src.analyzers.comparison.DATA_ANALYSIS_DIR", tmp_path):
        result = load_comparison_report()
        assert result is not None
        assert result["overall_verdict"] == "test"
