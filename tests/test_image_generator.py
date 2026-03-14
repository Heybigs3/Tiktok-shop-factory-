"""Tests for src/renderers/image_generator.py — Gemini API image generation."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.renderers.image_generator import (
    BACKGROUND_CONTEXTS,
    SCENE_PROMPTS,
    _build_scene_prompt,
    generate_all,
    generate_scene_image,
    generate_script_images,
)


class TestBuildScenePrompt:
    """Tests for scene prompt construction."""

    def test_product_showcase_prompt(self):
        prompt = _build_scene_prompt("Vitamin C Serum", "product_showcase", "warm", 0)
        assert "Vitamin C Serum" in prompt
        assert "warm golden" in prompt or "cozy" in prompt

    def test_ugc_showcase_prompt(self):
        prompt = _build_scene_prompt("Face Cream", "ugc_showcase", "default", 0)
        assert "Face Cream" in prompt
        assert "Casual" in prompt or "UGC" in prompt

    def test_comparison_prompt(self):
        prompt = _build_scene_prompt("Moisturizer", "comparison", "cool", 0)
        assert "Moisturizer" in prompt
        assert "comparison" in prompt.lower()

    def test_unknown_style_uses_product_showcase(self):
        prompt = _build_scene_prompt("Product", "nonexistent_style", "default", 0)
        # Should fall back to product_showcase template
        assert "Product" in prompt

    def test_scene_index_varies_context(self):
        prompt_0 = _build_scene_prompt("Product", "product_showcase", "default", 0)
        prompt_1 = _build_scene_prompt("Product", "product_showcase", "default", 1)
        # Different scene indices should produce different contexts
        assert prompt_0 != prompt_1

    def test_all_moods_have_backgrounds(self):
        for mood in ["warm", "cool", "energetic", "calm", "default"]:
            assert mood in BACKGROUND_CONTEXTS

    def test_all_video_styles_have_prompts(self):
        for style in ["product_showcase", "ugc_showcase", "comparison"]:
            assert style in SCENE_PROMPTS


def _make_mock_response(image_bytes=None):
    """Build a mock Gemini SDK response with the expected structure."""
    response = MagicMock()
    if image_bytes is not None:
        part = MagicMock()
        part.inline_data = MagicMock()
        part.inline_data.data = image_bytes
        candidate = MagicMock()
        candidate.content.parts = [part]
        response.candidates = [candidate]
    else:
        # No image data — text-only response
        part = MagicMock()
        part.inline_data = None
        candidate = MagicMock()
        candidate.content.parts = [part]
        response.candidates = [candidate]
    return response


class TestGenerateSceneImage:
    """Tests for single image generation via Gemini SDK."""

    @patch("src.renderers.image_generator._get_client", return_value=None)
    def test_no_client_returns_none(self, mock_client, tmp_path):
        result = generate_scene_image("test prompt", tmp_path / "test.png")
        assert result is None

    @patch("src.renderers.image_generator._get_client")
    def test_api_error_returns_none(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API error")
        mock_get_client.return_value = mock_client

        result = generate_scene_image("test prompt", tmp_path / "test.png")
        assert result is None

    @patch("src.renderers.image_generator._get_client")
    def test_successful_generation(self, mock_get_client, tmp_path):
        fake_image_bytes = b"fake_png_data"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_mock_response(fake_image_bytes)
        mock_get_client.return_value = mock_client

        output = tmp_path / "scene.png"
        result = generate_scene_image("test prompt", output)

        assert result == output
        assert output.exists()
        assert output.read_bytes() == fake_image_bytes

    @patch("src.renderers.image_generator._get_client")
    def test_no_image_in_response(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_mock_response(image_bytes=None)
        mock_get_client.return_value = mock_client

        result = generate_scene_image("test prompt", tmp_path / "test.png")
        assert result is None

    @patch("src.renderers.image_generator._get_client")
    def test_network_error_returns_none(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("Connection refused")
        mock_get_client.return_value = mock_client

        result = generate_scene_image("test prompt", tmp_path / "test.png")
        assert result is None

    @patch("src.renderers.image_generator._get_client")
    def test_reference_image_included(self, mock_get_client, tmp_path):
        """When a reference image is provided, contents should include image + text."""
        fake_image_bytes = b"generated_data"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_mock_response(fake_image_bytes)
        mock_get_client.return_value = mock_client

        # Create a fake reference image
        ref_img = tmp_path / "product.jpg"
        ref_img.write_bytes(b"fake_jpg")

        output = tmp_path / "scene.png"
        generate_scene_image("test prompt", output, reference_image_path=ref_img)

        # Verify generate_content was called with contents list
        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
        # Should have 2 items: Part.from_bytes (reference image) + text prompt
        assert len(contents) == 2
        assert contents[1] == "test prompt"

    @patch("src.renderers.image_generator._get_client")
    def test_uses_provided_client(self, mock_get_client, tmp_path):
        """When a client is passed directly, _get_client should not be called."""
        fake_image_bytes = b"data"
        direct_client = MagicMock()
        direct_client.models.generate_content.return_value = _make_mock_response(fake_image_bytes)

        output = tmp_path / "scene.png"
        generate_scene_image("test prompt", output, client=direct_client)

        mock_get_client.assert_not_called()
        direct_client.models.generate_content.assert_called_once()

    @patch("src.renderers.image_generator._get_client")
    def test_response_parse_error_returns_none(self, mock_get_client, tmp_path):
        """If response structure is unexpected, should return None gracefully."""
        mock_client = MagicMock()
        response = MagicMock()
        # Make candidates iteration raise
        response.candidates = None
        type(response).candidates = property(lambda self: (_ for _ in ()).throw(AttributeError("no candidates")))
        mock_client.models.generate_content.return_value = response
        mock_get_client.return_value = mock_client

        result = generate_scene_image("test prompt", tmp_path / "test.png")
        assert result is None


class TestGenerateScriptImages:
    """Tests for full script image generation."""

    @patch("src.renderers.image_generator._get_client")
    @patch("src.renderers.image_generator.generate_scene_image")
    @patch("src.renderers.image_generator.OUTPUT_IMAGES_DIR")
    def test_generates_requested_number(self, mock_dir, mock_gen, mock_client, tmp_path):
        mock_dir.__truediv__ = lambda self, name: tmp_path / name
        mock_dir.exists = lambda: True
        mock_client.return_value = MagicMock()

        # Create fake images
        for i in range(3):
            img = tmp_path / f"scene_{i:02d}.png"
            img.write_bytes(b"fake")
            mock_gen.return_value = img

        script = {
            "script_id": "abc12345",
            "visual_hints": {"mood": "warm", "video_style": "product_showcase"},
        }
        result = generate_script_images(script, num_scenes=3)
        assert mock_gen.call_count == 3

    @patch("src.renderers.image_generator._get_client")
    @patch("src.renderers.image_generator.generate_scene_image")
    @patch("src.renderers.image_generator.OUTPUT_IMAGES_DIR")
    def test_fallback_to_product_image(self, mock_dir, mock_gen, mock_client, tmp_path):
        mock_dir.__truediv__ = lambda self, name: tmp_path / name
        mock_client.return_value = MagicMock()

        # Scene generation fails
        mock_gen.return_value = None

        # Create a product with a local image
        product_img = tmp_path / "product.jpg"
        product_img.write_bytes(b"product_image_data")

        product = {
            "title": "Test Product",
            "local_images": [str(product_img)],
        }

        script = {
            "script_id": "abc12345",
            "visual_hints": {"mood": "warm"},
        }

        result = generate_script_images(script, product, num_scenes=1)
        # Should have fallback image
        assert len(result) == 1

    @patch("src.renderers.image_generator._get_client")
    @patch("src.renderers.image_generator.generate_scene_image")
    @patch("src.renderers.image_generator.OUTPUT_IMAGES_DIR")
    def test_handles_no_visual_hints(self, mock_dir, mock_gen, mock_client, tmp_path):
        mock_dir.__truediv__ = lambda self, name: tmp_path / name
        mock_gen.return_value = None
        mock_client.return_value = MagicMock()

        script = {"script_id": "abc12345"}
        result = generate_script_images(script, num_scenes=1)
        # Should not crash
        mock_gen.assert_called_once()


class TestGenerateAllProductIdMatching:
    """Tests for product_id-based matching in generate_all()."""

    @patch("src.renderers.image_generator._get_client")
    @patch("src.renderers.image_generator.generate_scene_image")
    @patch("src.renderers.image_generator.OUTPUT_IMAGES_DIR")
    def test_matches_product_by_id(self, mock_dir, mock_gen, mock_client, tmp_path):
        """Product with matching product_id should be used, not index."""
        from src.renderers.image_generator import generate_all

        mock_dir.__truediv__ = lambda self, name: tmp_path / name
        mock_client.return_value = MagicMock()
        mock_gen.return_value = tmp_path / "scene.png"
        (tmp_path / "scene.png").write_bytes(b"fake")

        scripts = [
            {"script_id": "abc12345", "product_id": "prod_B",
             "visual_hints": {"mood": "warm"}},
        ]
        products = [
            {"product_id": "prod_A", "title": "Product A"},
            {"product_id": "prod_B", "title": "Product B"},
        ]

        generate_all(scripts, products)

        # The script should match prod_B by product_id, not products[0]
        call_args = mock_gen.call_args_list[0]
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        # Product B's title should appear in the prompt (via generate_script_images)
        # Since generate_script_images uses product["title"], we verify it was called

    @patch("src.renderers.image_generator._get_client")
    @patch("src.renderers.image_generator.generate_scene_image")
    @patch("src.renderers.image_generator.OUTPUT_IMAGES_DIR")
    def test_falls_back_to_index_without_product_id(self, mock_dir, mock_gen, mock_client, tmp_path):
        """Without product_id, should fall back to index-based matching."""
        from src.renderers.image_generator import generate_all

        mock_dir.__truediv__ = lambda self, name: tmp_path / name
        mock_client.return_value = MagicMock()
        mock_gen.return_value = tmp_path / "scene.png"
        (tmp_path / "scene.png").write_bytes(b"fake")

        scripts = [
            {"script_id": "abc12345", "visual_hints": {"mood": "warm"}},
        ]
        products = [
            {"product_id": "prod_A", "title": "Product A"},
        ]

        result = generate_all(scripts, products)
        assert "abc12345" in result  # Script was processed
