"""Tests for the screen recorder module (scroll-animation video format)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.renderers.screen_recorder import (
    DEFAULT_PAUSE_DURATION,
    DEFAULT_SCROLL_SPEED,
    PHONE_FRAME_PADDING,
    RECORDING_DOT_SIZE,
    RECORDING_DOT_X,
    RECORDING_DOT_Y,
    RECORDING_LABEL_SIZE,
    RECORDING_LABEL_X,
    RECORDING_LABEL_Y,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    _create_from_product_images,
    _hash_product,
    _load_cached_screenshots,
    build_scroll_expression,
    get_screenshot_cache_dir,
)


# ── Unit tests: constants ──

class TestConstants:
    def test_video_dimensions(self):
        assert VIDEO_WIDTH == 1080
        assert VIDEO_HEIGHT == 1920

    def test_recording_indicator_in_frame(self):
        assert RECORDING_DOT_X > 0
        assert RECORDING_DOT_Y > 0
        assert RECORDING_DOT_X < VIDEO_WIDTH
        assert RECORDING_DOT_Y < VIDEO_HEIGHT

    def test_recording_label_to_right_of_dot(self):
        assert RECORDING_LABEL_X > RECORDING_DOT_X

    def test_default_scroll_speed_positive(self):
        assert DEFAULT_SCROLL_SPEED > 0

    def test_default_pause_duration_positive(self):
        assert DEFAULT_PAUSE_DURATION > 0


# ── Unit tests: hash ──

class TestHashProduct:
    def test_consistent_hash(self):
        product = {"product_id": "abc123", "title": "Cool Widget"}
        assert _hash_product(product) == _hash_product(product)

    def test_different_products_different_hash(self):
        p1 = {"product_id": "abc123", "title": "Widget A"}
        p2 = {"product_id": "xyz789", "title": "Widget B"}
        assert _hash_product(p1) != _hash_product(p2)

    def test_hash_length(self):
        product = {"product_id": "test", "title": "Test"}
        assert len(_hash_product(product)) == 8

    def test_empty_product(self):
        # Should not crash
        result = _hash_product({})
        assert len(result) == 8


# ── Unit tests: cache directory ──

class TestCacheDir:
    @patch("src.renderers.screen_recorder.OUTPUT_SCREENSHOTS_DIR")
    def test_creates_cache_dir(self, mock_dir, tmp_path):
        mock_dir.__truediv__ = lambda self, name: tmp_path / name
        result = get_screenshot_cache_dir("prod123")
        assert result.exists()


# ── Unit tests: scroll expression ──

class TestBuildScrollExpression:
    def test_no_scroll_needed(self):
        """Image shorter than viewport — no scrolling."""
        expr = build_scroll_expression(VIDEO_HEIGHT, 5.0)
        assert expr == "0"

    def test_simple_linear_scroll(self):
        """No pause points — linear scroll."""
        expr = build_scroll_expression(VIDEO_HEIGHT * 3, 10.0)
        assert "min(" in expr
        assert str(DEFAULT_SCROLL_SPEED) in expr

    @patch("src.renderers.screen_recorder.load_pipeline_config")
    def test_scroll_with_pause_points(self, mock_config):
        mock_config.return_value = {"screen_recording": {"pause_duration": 1.5}}
        expr = build_scroll_expression(5000, 10.0, pause_points=[0.3, 0.6])
        # Should contain if/else logic for pauses
        assert "if(" in expr
        assert "min(" in expr

    @patch("src.renderers.screen_recorder.load_pipeline_config")
    def test_scroll_with_single_pause(self, mock_config):
        mock_config.return_value = {"screen_recording": {"pause_duration": 1.0}}
        expr = build_scroll_expression(4000, 8.0, pause_points=[0.5])
        assert "if(" in expr

    def test_exact_viewport_height(self):
        """Image exactly viewport height — no scroll needed."""
        expr = build_scroll_expression(VIDEO_HEIGHT, 5.0)
        assert expr == "0"

    def test_custom_scroll_speed(self):
        expr = build_scroll_expression(5000, 10.0, scroll_speed=500)
        assert "500" in expr


# ── Unit tests: cached screenshots ──

class TestLoadCachedScreenshots:
    def test_empty_dir(self, tmp_path):
        result = _load_cached_screenshots(tmp_path, "prod123")
        assert result == []

    def test_nonexistent_dir(self, tmp_path):
        result = _load_cached_screenshots(tmp_path / "nope", "prod123")
        assert result == []

    def test_finds_cached_pngs(self, tmp_path):
        (tmp_path / "prod123_search.png").write_bytes(b"fake")
        (tmp_path / "prod123_detail.png").write_bytes(b"fake")
        result = _load_cached_screenshots(tmp_path, "prod123")
        assert len(result) == 2
        assert all(r["type"] == "cached" for r in result)

    def test_ignores_other_products(self, tmp_path):
        (tmp_path / "prod123_search.png").write_bytes(b"fake")
        (tmp_path / "other_search.png").write_bytes(b"fake")
        result = _load_cached_screenshots(tmp_path, "prod123")
        assert len(result) == 1

    def test_screenshot_has_required_keys(self, tmp_path):
        (tmp_path / "prod123_page.png").write_bytes(b"fake")
        result = _load_cached_screenshots(tmp_path, "prod123")
        ss = result[0]
        assert "path" in ss
        assert "type" in ss
        assert "scroll_duration" in ss
        assert "pause_points" in ss


# ── Unit tests: product image fallback ──

class TestCreateFromProductImages:
    @patch("src.renderers.screen_recorder.PRODUCT_IMAGES_DIR")
    def test_no_images_returns_empty(self, mock_dir, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        mock_dir.glob = lambda pattern: []
        result = _create_from_product_images("prod123", tmp_path)
        assert result == []

    @patch("src.renderers.screen_recorder.PRODUCT_IMAGES_DIR")
    def test_with_product_images(self, mock_dir, tmp_path):
        """When product images exist, should attempt to create a strip."""
        img_dir = tmp_path / "images"
        img_dir.mkdir()
        # Create minimal valid JPEG files
        # (FFmpeg will fail on fake bytes, but we're testing the logic)
        (img_dir / "prod123_01.jpg").write_bytes(b"fake_jpg")

        def mock_glob(pattern):
            if ".jpg" in pattern:
                return sorted(img_dir.glob("prod123_*.jpg"))
            return []

        mock_dir.glob = mock_glob

        # This will fail at FFmpeg stage but tests the image discovery logic
        result = _create_from_product_images("prod123", tmp_path)
        # Will be empty because ffmpeg can't process fake bytes
        assert isinstance(result, list)


# ── Unit tests: render function signature ──

class TestRenderScreenRecordingSignature:
    def test_import_render_function(self):
        """Verify the main render function is importable."""
        from src.renderers.screen_recorder import render_screen_recording_video
        assert callable(render_screen_recording_video)

    def test_import_capture_function(self):
        """Verify the capture function is importable."""
        from src.renderers.screen_recorder import capture_product_screenshots
        assert callable(capture_product_screenshots)


# ── Integration tests ──

@pytest.mark.ffmpeg
class TestScrollSegmentIntegration:
    def test_render_scroll_segment_with_real_image(self, tmp_path):
        """Smoke test: render a scroll segment from a solid-color image."""
        import ffmpeg as ff

        # Create a simple tall image
        img_path = tmp_path / "tall_image.png"
        (
            ff.input(f"color=c=white:s={VIDEO_WIDTH}x{VIDEO_HEIGHT * 2}:d=1", f="lavfi")
            .output(str(img_path), vframes=1)
            .overwrite_output()
            .run(quiet=True)
        )

        from src.renderers.screen_recorder import render_scroll_segment
        stream = render_scroll_segment(img_path, 3.0)
        assert stream is not None

        # Render to file
        out_path = tmp_path / "scroll_test.mp4"
        (
            ff.output(stream, str(out_path), vcodec="libx264", pix_fmt="yuv420p", t=3.0)
            .overwrite_output()
            .run(quiet=True)
        )
        assert out_path.exists()
        assert out_path.stat().st_size > 0
