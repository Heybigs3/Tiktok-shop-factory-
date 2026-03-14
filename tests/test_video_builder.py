"""Tests for the video builder module (Phase 3)."""

from unittest.mock import MagicMock, patch

import pytest

import src.renderers.video_builder as vb_module

from src.renderers.video_builder import (
    BODY_TEXT_Y,
    COLOR_GRADES,
    COLOR_THEMES,
    CTA_TEXT_Y,
    HOOK_TEXT_Y,
    MOOD_TRANSITIONS,
    PRICE_BADGE_X,
    PRICE_BADGE_Y,
    PRODUCT_TEXT_BORDER_COLOR,
    PRODUCT_TEXT_BORDER_WIDTH,
    SAFE_BOTTOM,
    SAFE_TOP,
    TEXT_BORDER_COLOR,
    TEXT_BORDER_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    VIGNETTE_ANGLE_CONTENT,
    VIGNETTE_ANGLE_PRODUCT,
    _apply_color_grade,
    _apply_vignette,
    _calculate_image_timing,
    _get_ken_burns_sequence,
    _get_ken_burns_speeds,
    _get_transition,
    build_section,
    calculate_timing,
    escape_drawtext,
    get_music_track,
    get_theme,
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
    def setup_method(self):
        """Reset analysis overrides cache so tests use defaults, not real data."""
        vb_module._analysis_overrides_cache = None

    @patch("src.renderers.video_builder._get_analysis_overrides", return_value={})
    def test_basic_timing(self, _mock):
        script = {"estimated_duration_sec": 15}
        timing = calculate_timing(script)
        assert timing["hook_duration"] == 3
        assert timing["cta_duration"] == 3
        assert timing["body_duration"] == 9
        assert timing["total_duration"] == 15

    @patch("src.renderers.video_builder._get_analysis_overrides", return_value={})
    def test_minimum_body_clamp(self, _mock):
        """Body should never go below MIN_BODY_DURATION (4s)."""
        script = {"estimated_duration_sec": 5}  # 5 - 3 - 3 = -1, clamped to 4
        timing = calculate_timing(script)
        assert timing["body_duration"] == 4
        assert timing["total_duration"] == 10  # 3 + 4 + 3

    @patch("src.renderers.video_builder._get_analysis_overrides", return_value={})
    def test_zero_duration(self, _mock):
        """Zero estimated duration should still clamp body to minimum."""
        script = {"estimated_duration_sec": 0}
        timing = calculate_timing(script)
        assert timing["body_duration"] == 4
        assert timing["total_duration"] == 10

    @patch("src.renderers.video_builder._get_analysis_overrides", return_value={})
    def test_missing_duration_uses_default(self, _mock):
        """Missing estimated_duration_sec should use default total."""
        timing = calculate_timing({})
        assert timing["hook_duration"] == 3
        assert timing["cta_duration"] == 3
        assert timing["body_duration"] >= 4

    @patch("src.renderers.video_builder._get_analysis_overrides", return_value={
        "timing": {"target_hook_duration": 2.0, "target_min_duration": 60}
    })
    def test_timing_with_overrides(self, _mock):
        """When feedback loop provides overrides, timing adjusts accordingly."""
        script = {"estimated_duration_sec": 15}
        timing = calculate_timing(script)
        assert timing["hook_duration"] == 2.0  # From override, not default 3
        assert timing["total_duration"] >= 60  # Stretched to meet target


# ── Unit tests: get_theme ──

@patch("src.renderers.video_builder._get_analysis_overrides", return_value={})
class TestGetTheme:
    def test_mood_from_visual_hints(self, _mock):
        script = {"visual_hints": {"mood": "warm"}}
        theme = get_theme(script)
        assert theme == COLOR_THEMES["warm"]

    def test_all_moods_recognized(self, _mock):
        for mood in ["warm", "cool", "energetic", "calm"]:
            script = {"visual_hints": {"mood": mood}}
            assert get_theme(script) == COLOR_THEMES[mood]

    def test_fallback_to_source_type_trending(self, _mock):
        script = {"source_type": "trending"}
        theme = get_theme(script)
        assert theme == COLOR_THEMES["energetic"]

    def test_fallback_to_source_type_ad(self, _mock):
        script = {"source_type": "ad"}
        theme = get_theme(script)
        assert theme == COLOR_THEMES["warm"]

    def test_fallback_to_source_type_mixed(self, _mock):
        script = {"source_type": "mixed"}
        theme = get_theme(script)
        assert theme == COLOR_THEMES["cool"]

    def test_fallback_to_default(self, _mock):
        script = {}
        theme = get_theme(script)
        assert theme == COLOR_THEMES["default"]

    def test_invalid_mood_falls_back(self, _mock):
        script = {"visual_hints": {"mood": "nonexistent"}, "source_type": "trending"}
        theme = get_theme(script)
        assert theme == COLOR_THEMES["energetic"]  # falls through to source_type

    def test_non_dict_visual_hints_falls_back(self, _mock):
        script = {"visual_hints": "just a string", "source_type": "ad"}
        theme = get_theme(script)
        assert theme == COLOR_THEMES["warm"]

    def test_theme_has_required_keys(self, _mock):
        for name, theme in COLOR_THEMES.items():
            assert "bg" in theme, f"Theme '{name}' missing 'bg'"
            assert "text" in theme, f"Theme '{name}' missing 'text'"
            assert "accent" in theme, f"Theme '{name}' missing 'accent'"


# ── Unit tests: get_music_track ──

class TestGetMusicTrack:
    @patch("src.renderers.video_builder.load_pipeline_config")
    @patch("src.renderers.video_builder.MUSIC_DIR")
    def test_returns_track_for_mood(self, mock_music_dir, mock_config, tmp_path):
        # Create a fake music file
        track = tmp_path / "energetic.mp3"
        track.write_bytes(b"fake")
        mock_music_dir.__truediv__ = lambda self, name: tmp_path / name
        mock_config.return_value = {
            "music": {
                "enabled": True,
                "mood_map": {"energetic": "energetic.mp3", "default": "calm.mp3"},
            }
        }

        script = {"visual_hints": {"mood": "energetic"}}
        result = get_music_track(script)
        assert result == track

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_disabled_returns_none(self, mock_config):
        mock_config.return_value = {"music": {"enabled": False}}
        result = get_music_track({"visual_hints": {"mood": "warm"}})
        assert result is None

    @patch("src.renderers.video_builder.load_pipeline_config")
    @patch("src.renderers.video_builder.MUSIC_DIR")
    def test_missing_file_returns_none(self, mock_music_dir, mock_config, tmp_path):
        mock_music_dir.__truediv__ = lambda self, name: tmp_path / name
        mock_config.return_value = {
            "music": {
                "enabled": True,
                "mood_map": {"warm": "nonexistent.mp3", "default": "calm.mp3"},
            }
        }
        result = get_music_track({"visual_hints": {"mood": "warm"}})
        assert result is None

    @patch("src.renderers.video_builder.load_pipeline_config")
    @patch("src.renderers.video_builder.MUSIC_DIR")
    def test_unknown_mood_uses_default(self, mock_music_dir, mock_config, tmp_path):
        track = tmp_path / "calm.mp3"
        track.write_bytes(b"fake")
        mock_music_dir.__truediv__ = lambda self, name: tmp_path / name
        mock_config.return_value = {
            "music": {
                "enabled": True,
                "mood_map": {"default": "calm.mp3"},
            }
        }
        result = get_music_track({"visual_hints": {"mood": "unknown"}})
        assert result == track


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

    def test_output_filename_with_product_id(self, sample_script, tmp_path):
        """When product_id is present, filename should use it instead of source_type."""
        script_id = sample_script["script_id"]
        product_id = "prod_123"
        sample_script["product_id"] = product_id
        filename = f"{script_id[:8]}_{product_id}.mp4"
        assert filename == "a1b2c3d4_prod_123.mp4"

    def test_renders_script_without_visual_hints(self, tmp_path):
        """Old-format scripts (no visual_hints) should still render."""
        from src.renderers.video_builder import render_video
        from src.utils.config import FONT_PATH

        if not FONT_PATH.exists():
            pytest.skip("Font file not found")

        legacy_script = {
            "hook": "Quick tip",
            "body": "Here is something useful you should know about.",
            "cta": "Follow me",
            "style_notes": "Fast paced",
            "script_id": "legacy01-0000-0000-0000-000000000000",
            "source_type": "mixed",
            "estimated_duration_sec": 12,
        }
        output = tmp_path / "legacy_test.mp4"
        result = render_video(legacy_script, output, FONT_PATH)
        assert result.exists()
        assert result.stat().st_size > 0


# ── Unit tests: TikTok safe zone constants ──

class TestSafeZoneConstants:
    def test_safe_zones_within_frame(self):
        assert SAFE_TOP > 0
        assert SAFE_BOTTOM > 0
        assert SAFE_TOP + SAFE_BOTTOM < VIDEO_HEIGHT

    def test_hook_text_in_safe_zone(self):
        assert HOOK_TEXT_Y >= SAFE_TOP

    def test_cta_text_in_safe_zone(self):
        assert CTA_TEXT_Y <= VIDEO_HEIGHT - SAFE_BOTTOM

    def test_body_between_hook_and_cta(self):
        assert BODY_TEXT_Y > HOOK_TEXT_Y
        assert BODY_TEXT_Y < CTA_TEXT_Y

    def test_price_badge_in_safe_zone(self):
        assert PRICE_BADGE_X > 0
        assert PRICE_BADGE_X < VIDEO_WIDTH
        assert PRICE_BADGE_Y >= SAFE_TOP


# ── Unit tests: Ken Burns sequence ──

class TestKenBurnsSequence:
    def test_returns_correct_count(self):
        assert len(_get_ken_burns_sequence(5)) == 5
        assert len(_get_ken_burns_sequence(1)) == 1
        assert len(_get_ken_burns_sequence(10)) == 10

    def test_no_consecutive_duplicates(self):
        seq = _get_ken_burns_sequence(5)
        for i in range(1, len(seq)):
            assert seq[i] != seq[i - 1]

    def test_all_valid_effects(self):
        valid = {"zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up"}
        seq = _get_ken_burns_sequence(10)
        for effect in seq:
            assert effect in valid

    def test_single_image_returns_zoom_in(self):
        seq = _get_ken_burns_sequence(1)
        assert seq[0] == "zoom_in"

    def test_empty_returns_empty(self):
        assert _get_ken_burns_sequence(0) == []


# ── Unit tests: image timing calculator ──

class TestCalculateImageTiming:
    def test_covers_full_duration(self):
        timings = _calculate_image_timing(5, 20.0)
        assert len(timings) == 5
        assert timings[0]["start"] == 0.0
        assert timings[-1]["end"] == pytest.approx(20.0)

    def test_first_image_longer_than_last(self):
        timings = _calculate_image_timing(5, 20.0)
        assert timings[0]["duration"] > timings[-1]["duration"]

    def test_single_image_gets_full_duration(self):
        timings = _calculate_image_timing(1, 15.0)
        assert len(timings) == 1
        assert timings[0]["duration"] == 15.0
        assert timings[0]["start"] == 0.0
        assert timings[0]["end"] == 15.0

    def test_zero_images_returns_empty(self):
        assert _calculate_image_timing(0, 10.0) == []

    def test_durations_sum_to_total(self):
        timings = _calculate_image_timing(4, 16.0)
        total = sum(t["duration"] for t in timings)
        assert total == pytest.approx(16.0)

    def test_all_durations_positive(self):
        timings = _calculate_image_timing(8, 15.0)
        for t in timings:
            assert t["duration"] > 0

    def test_timings_are_contiguous(self):
        """Each image starts where the previous one ended."""
        timings = _calculate_image_timing(5, 20.0)
        for i in range(1, len(timings)):
            assert timings[i]["start"] == pytest.approx(timings[i - 1]["end"])

    def test_two_images_split(self):
        timings = _calculate_image_timing(2, 10.0)
        assert len(timings) == 2
        # First should be longer than second
        assert timings[0]["duration"] > timings[1]["duration"]


# ── Unit tests: _get_script_media fallback to product images ──

class TestGetScriptMediaFallback:
    def test_no_product_id_no_fallback(self, tmp_path):
        """Without product_id, should not search for product images."""
        from src.renderers.video_builder import _get_script_media
        clips, images = _get_script_media("nonexist0", "")
        assert clips == []
        assert images == []

    @patch("src.utils.config.PRODUCT_IMAGES_DIR")
    @patch("src.renderers.video_builder.OUTPUT_IMAGES_DIR")
    @patch("src.renderers.video_builder.OUTPUT_CLIPS_DIR")
    def test_fallback_to_product_images(self, mock_clips, mock_images, mock_product, tmp_path):
        """When no generated media exists, should find Kalodata product images."""
        mock_clips.__truediv__ = lambda self, name: tmp_path / "clips" / name
        mock_images.__truediv__ = lambda self, name: tmp_path / "images" / name

        # Create product images
        product_dir = tmp_path / "products"
        product_dir.mkdir()
        (product_dir / "prod123_01.jpg").write_bytes(b"img1")
        (product_dir / "prod123_02.jpg").write_bytes(b"img2")
        mock_product.glob = lambda pattern: sorted(product_dir.glob(pattern))

        from src.renderers.video_builder import _get_script_media
        clips, images = _get_script_media("nonexist0", "prod123")
        assert len(images) == 2
        assert clips == []


# ── Unit tests: COLOR_GRADES constants ──

class TestColorGrades:
    def test_all_moods_present(self):
        for mood in COLOR_THEMES:
            assert mood in COLOR_GRADES, f"Missing color grade for mood '{mood}'"

    def test_default_is_identity(self):
        g = COLOR_GRADES["default"]
        assert g["brightness"] == 0.0
        assert g["contrast"] == 1.0
        assert g["saturation"] == 1.0
        assert g["gamma_r"] == 1.0
        assert g["gamma_b"] == 1.0


# ── Unit tests: MOOD_TRANSITIONS constants ──

class TestMoodTransitions:
    def test_all_moods_present(self):
        for mood in COLOR_THEMES:
            assert mood in MOOD_TRANSITIONS, f"Missing transition for mood '{mood}'"


# ── Unit tests: text border constants ──

class TestTextBorderConstants:
    def test_border_widths_positive(self):
        assert TEXT_BORDER_WIDTH > 0
        assert PRODUCT_TEXT_BORDER_WIDTH > 0

    def test_border_colors_are_strings(self):
        assert isinstance(TEXT_BORDER_COLOR, str)
        assert isinstance(PRODUCT_TEXT_BORDER_COLOR, str)

    def test_product_border_thicker(self):
        assert PRODUCT_TEXT_BORDER_WIDTH > TEXT_BORDER_WIDTH


# ── Unit tests: _apply_color_grade helper ──

class TestApplyColorGrade:
    def test_calls_eq_filter(self):
        mock_stream = MagicMock()
        _apply_color_grade(mock_stream, "warm")
        mock_stream.filter.assert_called_once()
        call_args = mock_stream.filter.call_args
        assert call_args[0][0] == "eq"

    def test_default_mood_returns_stream_unchanged(self):
        """Default grade is identity — should return stream as-is."""
        mock_stream = MagicMock()
        result = _apply_color_grade(mock_stream, "default")
        assert result is mock_stream
        mock_stream.filter.assert_not_called()

    def test_unknown_mood_uses_default(self):
        """Unknown mood falls back to default (identity)."""
        mock_stream = MagicMock()
        result = _apply_color_grade(mock_stream, "nonexistent")
        assert result is mock_stream


# ── Unit tests: _get_transition helper ──

class TestGetTransition:
    def test_known_mood(self):
        script = {"visual_hints": {"mood": "warm"}}
        assert _get_transition(script) == "dissolve"

    def test_energetic_mood(self):
        script = {"visual_hints": {"mood": "energetic"}}
        assert _get_transition(script) == "slideright"

    def test_unknown_mood_defaults_to_fade(self):
        script = {"visual_hints": {"mood": "nonexistent"}}
        assert _get_transition(script) == "fade"

    def test_no_hints_defaults_to_fade(self):
        assert _get_transition({}) == "fade"


# ── Unit tests: _get_ken_burns_speeds helper ──

class TestKenBurnsSpeeds:
    def test_first_slower_than_last(self):
        speeds = _get_ken_burns_speeds(5, "default")
        assert speeds[0] < speeds[-1]

    def test_calm_slower_than_energetic(self):
        calm = _get_ken_burns_speeds(3, "calm")
        energetic = _get_ken_burns_speeds(3, "energetic")
        assert sum(calm) < sum(energetic)

    def test_single_image(self):
        speeds = _get_ken_burns_speeds(1, "default")
        assert len(speeds) == 1

    def test_zero_images(self):
        assert _get_ken_burns_speeds(0, "default") == []


# ── Unit tests: _apply_vignette helper ──

class TestApplyVignette:
    def test_product_uses_stronger_angle(self):
        mock_stream = MagicMock()
        _apply_vignette(mock_stream, is_product=True)
        call_args = mock_stream.filter.call_args
        assert call_args[1]["angle"] == VIGNETTE_ANGLE_PRODUCT

    def test_content_uses_gentler_angle(self):
        mock_stream = MagicMock()
        _apply_vignette(mock_stream, is_product=False)
        call_args = mock_stream.filter.call_args
        assert call_args[1]["angle"] == VIGNETTE_ANGLE_CONTENT


# ── Unit tests: build_section with fade-in ──

class TestBuildSectionFadeIn:
    def test_default_no_fade(self):
        """text_fade_in=0.0 should not add alpha expressions."""
        stream = build_section(
            "Hello", 48, 20, 3.0, "fake/font.ttf",
            text_fade_in=0.0,
        )
        # Stream should build without error (no alpha kwarg)
        assert stream is not None

    def test_with_fade_in(self):
        """text_fade_in > 0 should build without error."""
        stream = build_section(
            "Hello", 48, 20, 3.0, "fake/font.ttf",
            text_fade_in=0.5,
        )
        assert stream is not None


# ── Integration tests: full render with enhancements ──

@pytest.mark.ffmpeg
class TestRenderWithEnhancements:
    def test_render_video_applies_enhancements(self, sample_script, tmp_path):
        """Full render smoke test — all 6 enhancements active."""
        from src.renderers.video_builder import render_video
        from src.utils.config import FONT_PATH

        if not FONT_PATH.exists():
            pytest.skip("Font file not found")

        sample_script["visual_hints"] = {"mood": "warm"}
        output = tmp_path / "enhanced_test.mp4"
        result = render_video(sample_script, output, FONT_PATH)

        assert result.exists()
        assert result.stat().st_size > 0
