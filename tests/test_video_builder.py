"""Tests for the video builder module (Phase 3)."""

import pytest

from src.renderers.video_builder import (
    calculate_timing,
    escape_drawtext,
    wrap_text,
)


# ── Unit tests: escape_drawtext ──

class TestEscapeDrawtext:
    def test_escapes_colons(self):
        assert escape_drawtext("time: 3:00") == "time\\: 3\\:00"

    def test_escapes_backslashes(self):
        assert escape_drawtext("path\\to\\file") == "path\\\\to\\\\file"

    def test_plain_text_passthrough(self):
        assert escape_drawtext("hello world") == "hello world"


# ── Unit tests: wrap_text ──

class TestWrapText:
    def test_short_text_passthrough(self):
        result = wrap_text("Short", 20)
        assert result == "Short"

    def test_long_text_wraps(self):
        result = wrap_text("This is a longer sentence that should wrap", 20)
        lines = result.split("\n")
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 20

    def test_empty_string(self):
        assert wrap_text("", 20) == ""


# ── Unit tests: calculate_timing ──

class TestCalculateTiming:
    def test_basic_timing(self):
        script = {"estimated_duration_sec": 15}
        timing = calculate_timing(script)
        assert timing["hook_duration"] == 3
        assert timing["cta_duration"] == 3
        assert timing["body_duration"] == 9
        assert timing["total_duration"] == 15

    def test_minimum_body_clamp(self):
        """Body should never go below MIN_BODY_DURATION (4s)."""
        script = {"estimated_duration_sec": 5}  # 5 - 3 - 3 = -1, clamped to 4
        timing = calculate_timing(script)
        assert timing["body_duration"] == 4
        assert timing["total_duration"] == 10  # 3 + 4 + 3

    def test_zero_duration(self):
        """Zero estimated duration should still clamp body to minimum."""
        script = {"estimated_duration_sec": 0}
        timing = calculate_timing(script)
        assert timing["body_duration"] == 4
        assert timing["total_duration"] == 10

    def test_missing_duration_uses_default(self):
        """Missing estimated_duration_sec should use default total."""
        timing = calculate_timing({})
        assert timing["hook_duration"] == 3
        assert timing["cta_duration"] == 3
        assert timing["body_duration"] >= 4


# ── Integration tests: FFmpeg rendering (auto-skipped if FFmpeg not installed) ──

@pytest.mark.ffmpeg
class TestRenderVideo:
    def test_renders_single_video(self, sample_script, tmp_path):
        from src.renderers.video_builder import render_video
        from src.utils.config import FONT_PATH

        if not FONT_PATH.exists():
            pytest.skip("Font file not found")

        output = tmp_path / "test_video.mp4"
        result = render_video(sample_script, output, FONT_PATH)

        assert result.exists()
        assert result.stat().st_size > 0

    def test_output_filename_format(self, sample_script, tmp_path):
        from src.renderers.video_builder import render_video
        from src.utils.config import FONT_PATH

        if not FONT_PATH.exists():
            pytest.skip("Font file not found")

        script_id = sample_script["script_id"]
        source_type = sample_script["source_type"]
        filename = f"{script_id[:8]}_{source_type}.mp4"
        output = tmp_path / filename

        render_video(sample_script, output, FONT_PATH)
        assert output.name == "a1b2c3d4_trending.mp4"
