"""Tests for the format router in video_builder."""

from unittest.mock import patch

import pytest

from src.renderers.video_builder import (
    ALL_RENDER_FORMATS,
    PRODUCT_STYLES,
    select_render_format,
)


# ── Unit tests: explicit video_style routing ──

class TestExplicitVideoStyle:
    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_screen_recording_style(self, mock_config):
        mock_config.return_value = {
            "format_router": {"screen_recording_enabled": True}
        }
        script = {"visual_hints": {"video_style": "screen_recording"}}
        assert select_render_format(script) == "screen_recording"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_screen_recording_disabled(self, mock_config):
        """When screen_recording_enabled is False, should not pick screen_recording."""
        mock_config.return_value = {
            "format_router": {"screen_recording_enabled": False}
        }
        script = {"visual_hints": {"video_style": "screen_recording"}}
        result = select_render_format(script)
        assert result != "screen_recording"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_ugc_avatar_with_heygen_enabled(self, mock_config):
        mock_config.return_value = {
            "format_router": {"heygen_enabled": True}
        }
        script = {"visual_hints": {"video_style": "ugc_avatar"}}
        assert select_render_format(script) == "ugc_avatar"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_ugc_avatar_without_heygen(self, mock_config):
        """When HeyGen is not enabled, ugc_avatar should fall through."""
        mock_config.return_value = {
            "format_router": {"heygen_enabled": False}
        }
        script = {"visual_hints": {"video_style": "ugc_avatar"}}
        result = select_render_format(script)
        assert result != "ugc_avatar"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_product_showcase_style(self, mock_config):
        mock_config.return_value = {"format_router": {}}
        script = {"visual_hints": {"video_style": "product_showcase"}}
        assert select_render_format(script) == "product_showcase"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_ugc_showcase_style(self, mock_config):
        mock_config.return_value = {"format_router": {}}
        script = {"visual_hints": {"video_style": "ugc_showcase"}}
        assert select_render_format(script) == "ugc_showcase"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_comparison_style(self, mock_config):
        mock_config.return_value = {"format_router": {}}
        script = {"visual_hints": {"video_style": "comparison"}}
        assert select_render_format(script) == "comparison"


# ── Unit tests: fallback logic ──

class TestFallbackLogic:
    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_no_hints_no_product_returns_standard(self, mock_config):
        mock_config.return_value = {
            "format_router": {"default_format": "standard"}
        }
        result = select_render_format({})
        assert result == "standard"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_product_id_without_images_returns_product_showcase(self, mock_config):
        mock_config.return_value = {
            "format_router": {"screen_recording_enabled": True}
        }
        script = {"product_id": "prod123"}
        with patch("src.utils.config.PRODUCT_IMAGES_DIR") as mock_dir:
            mock_dir.glob = lambda pattern: []
            result = select_render_format(script)
        assert result == "product_showcase"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_config_default_format_respected(self, mock_config):
        mock_config.return_value = {
            "format_router": {"default_format": "product_showcase"}
        }
        result = select_render_format({})
        assert result == "product_showcase"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_invalid_default_format_returns_standard(self, mock_config):
        mock_config.return_value = {
            "format_router": {"default_format": "nonexistent_format"}
        }
        result = select_render_format({})
        assert result == "standard"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_empty_config(self, mock_config):
        mock_config.return_value = {}
        result = select_render_format({})
        assert result == "standard"


# ── Unit tests: product with images → format weight distribution ──

class TestFormatWeights:
    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_product_with_images_uses_weights(self, mock_config):
        """When product images exist, format should be one of the weighted options."""
        mock_config.return_value = {
            "format_router": {
                "screen_recording_enabled": True,
                "format_weights": {
                    "product_showcase": 0.5,
                    "screen_recording": 0.5,
                },
            }
        }
        script = {"product_id": "prod123"}
        with patch("src.utils.config.PRODUCT_IMAGES_DIR") as mock_dir:
            mock_dir.glob = lambda pattern: ["/fake/prod123_01.jpg"]

            # Run multiple times — should get both formats due to random weights
            results = set()
            for _ in range(50):
                results.add(select_render_format(script))

            assert "product_showcase" in results or "screen_recording" in results

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_all_weight_to_showcase(self, mock_config):
        """100% weight to product_showcase should always return it."""
        mock_config.return_value = {
            "format_router": {
                "screen_recording_enabled": True,
                "format_weights": {
                    "product_showcase": 1.0,
                    "screen_recording": 0.0,
                },
            }
        }
        script = {"product_id": "prod123"}
        with patch("src.utils.config.PRODUCT_IMAGES_DIR") as mock_dir:
            mock_dir.glob = lambda pattern: ["/fake/prod123_01.jpg"]

            for _ in range(10):
                assert select_render_format(script) == "product_showcase"


# ── Unit tests: ALL_RENDER_FORMATS constant ──

class TestRenderFormatsConstant:
    def test_includes_all_product_styles(self):
        for style in PRODUCT_STYLES:
            assert style in ALL_RENDER_FORMATS

    def test_includes_screen_recording(self):
        assert "screen_recording" in ALL_RENDER_FORMATS

    def test_includes_ugc_avatar(self):
        assert "ugc_avatar" in ALL_RENDER_FORMATS

    def test_includes_standard(self):
        assert "standard" in ALL_RENDER_FORMATS


# ── Unit tests: product dict as separate argument ──

class TestProductArgument:
    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_product_dict_overrides_script(self, mock_config):
        """Product dict's product_id should be used when script has none."""
        mock_config.return_value = {
            "format_router": {"screen_recording_enabled": False}
        }
        script = {}
        product = {"product_id": "prod456"}
        result = select_render_format(script, product)
        assert result == "product_showcase"

    @patch("src.renderers.video_builder.load_pipeline_config")
    def test_none_product(self, mock_config):
        mock_config.return_value = {
            "format_router": {"default_format": "standard"}
        }
        result = select_render_format({}, None)
        assert result == "standard"
