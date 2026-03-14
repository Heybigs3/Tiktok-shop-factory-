"""Tests for src.analyzers.style_overrides — the feedback loop bridge."""

import json
from pathlib import Path
from unittest.mock import patch

from src.analyzers.style_overrides import (
    _extract_color_overrides,
    _extract_content_overrides,
    _extract_timing_overrides,
    get_prompt_overrides,
    get_render_overrides,
)


# ── Color extraction ──

def test_color_overrides_from_comparison_report():
    """Extracts hex colors from comparison report's color palette gap."""
    report = {
        "gaps": [
            {
                "category": "Color Palette",
                "scraped_value": "Warm, skin-toned neutrals (#8B7355, #D4A574) with bright accent greens (#22c85c)",
                "fix": "Switch to warm neutrals and skin tones with bright green/pink accents",
            }
        ]
    }
    colors = _extract_color_overrides(report, None)
    assert colors["bg"] == "0x8B7355"
    assert colors["accent"] == "0xD4A574"


def test_color_overrides_from_style_bible():
    """Falls back to Style Bible when no comparison report."""
    bible = {
        "visual_style": {
            "dominant_colors": ["#D4A574", "#E8D4D8"],
            "accent_colors": ["#22c85c"],
        }
    }
    colors = _extract_color_overrides(None, bible)
    assert colors["bg"] == "0xD4A574"
    assert colors["accent"] == "0x22c85c"


def test_color_overrides_empty():
    """Returns empty dict when no data."""
    assert _extract_color_overrides(None, None) == {}


def test_color_overrides_adds_white_text():
    """Automatically adds white text color when bg is overridden."""
    report = {
        "gaps": [{"category": "Color", "scraped_value": "#AABBCC", "fix": "use it"}]
    }
    colors = _extract_color_overrides(report, None)
    assert colors.get("text") == "0xffffff"


# ── Timing extraction ──

def test_timing_overrides_from_comparison():
    """Extracts target duration and hook length from comparison gaps."""
    report = {
        "gaps": [
            {
                "category": "Content Length",
                "fix": "Extend videos to 60-75s to allow proper storytelling",
            },
            {
                "category": "Hook Strength",
                "fix": "Shorten hooks to 2-3s max, diversify types",
            },
        ]
    }
    timing = _extract_timing_overrides(report, None)
    assert timing["target_min_duration"] == 60
    assert timing["target_max_duration"] == 75
    assert timing["target_hook_duration"] == 2.0


def test_timing_overrides_cut_frequency():
    """Extracts target cuts from visual dynamism gap."""
    report = {
        "gaps": [
            {
                "category": "Visual Dynamism",
                "fix": "Increase cut frequency to 15+ per video, target 3-5s per cut maximum",
            }
        ]
    }
    timing = _extract_timing_overrides(report, None)
    assert timing["target_cuts"] == 15


def test_timing_overrides_from_style_bible():
    """Falls back to Style Bible for timing."""
    bible = {
        "structure_patterns": {"avg_duration_s": 70},
        "hook_patterns": {"avg_duration_s": 2.5},
    }
    timing = _extract_timing_overrides(None, bible)
    assert timing["target_min_duration"] == 56  # 70 * 0.8
    assert timing["target_hook_duration"] == 2.5


# ── Content extraction ──

def test_content_overrides_music():
    """Detects music recommendation from audio gap."""
    report = {
        "gaps": [{"category": "Audio Strategy", "fix": "Add trending music to 80%+ of videos"}]
    }
    content = _extract_content_overrides(report)
    assert content["music_recommended"] is True


def test_content_overrides_text_overlays():
    """Extracts target text overlay count."""
    report = {
        "gaps": [{"category": "Text Overlays", "fix": "Double text overlay frequency to 8+ per video"}]
    }
    content = _extract_content_overrides(report)
    assert content["target_text_overlays"] == 8


def test_content_overrides_empty():
    """Returns empty dict when no report."""
    assert _extract_content_overrides(None) == {}


# ── Full get_render_overrides ──

def test_get_render_overrides_with_data(tmp_path):
    """Returns complete overrides dict when comparison report exists."""
    report = {
        "gaps": [
            {"category": "Color Palette", "scraped_value": "#AABBCC #112233", "fix": "use warm"},
            {"category": "Content Length", "fix": "Extend to 60-75s for storytelling"},
        ]
    }
    report_path = tmp_path / "comparison_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with patch("src.analyzers.style_overrides.DATA_ANALYSIS_DIR", tmp_path), \
         patch("src.analyzers.style_overrides.DATA_STYLE_BIBLES_DIR", tmp_path):
        # Clear cache
        if hasattr(get_render_overrides, "_cache"):
            delattr(get_render_overrides, "_cache")
        overrides = get_render_overrides()

    assert overrides["source"] == "comparison_report"
    assert overrides["colors"]["bg"] == "0xAABBCC"
    assert overrides["timing"]["target_min_duration"] == 60


def test_get_render_overrides_no_data(tmp_path):
    """Returns source='none' when no analysis data exists."""
    with patch("src.analyzers.style_overrides.DATA_ANALYSIS_DIR", tmp_path), \
         patch("src.analyzers.style_overrides.DATA_STYLE_BIBLES_DIR", tmp_path):
        overrides = get_render_overrides()
    assert overrides["source"] == "none"


# ── Prompt overrides ──

def test_get_prompt_overrides_with_report(tmp_path):
    """Returns formatted prompt text from comparison report."""
    report = {
        "overall_verdict": "Our videos are boring",
        "gaps": [
            {"category": "Hook Strength", "issue": "Hooks are too slow", "fix": "Shorten to 2-3s"},
        ],
        "priority_fixes": ["Increase cut frequency", "Extend video length"],
    }
    report_path = tmp_path / "comparison_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with patch("src.analyzers.style_overrides.DATA_ANALYSIS_DIR", tmp_path):
        result = get_prompt_overrides()

    assert result is not None
    assert "Hook Strength" in result
    assert "Hooks are too slow" in result
    assert "Increase cut frequency" in result
    assert "boring" in result


def test_get_prompt_overrides_no_report(tmp_path):
    """Returns None when no comparison report exists."""
    with patch("src.analyzers.style_overrides.DATA_ANALYSIS_DIR", tmp_path):
        assert get_prompt_overrides() is None
