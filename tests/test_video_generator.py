"""Tests for src/renderers/video_generator.py — Muapi video clip generation."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.renderers.video_generator import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    MOTION_PRESETS,
    _get_model_endpoint,
    _get_motion_preset,
    generate_clip,
    generate_script_clips,
)


class TestMotionPresets:
    """Tests for mood → motion preset mapping."""

    def test_all_moods_have_presets(self):
        for mood in ["energetic", "calm", "warm", "cool", "default"]:
            assert mood in MOTION_PRESETS

    def test_preset_has_required_keys(self):
        for mood, preset in MOTION_PRESETS.items():
            assert "prompt_suffix" in preset, f"Preset '{mood}' missing prompt_suffix"
            assert "duration" in preset, f"Preset '{mood}' missing duration"

    def test_get_motion_preset_known_mood(self):
        preset = _get_motion_preset("energetic")
        assert preset == MOTION_PRESETS["energetic"]

    def test_get_motion_preset_unknown_mood(self):
        preset = _get_motion_preset("mysterious")
        assert preset == MOTION_PRESETS["default"]

    def test_durations_are_reasonable(self):
        for mood, preset in MOTION_PRESETS.items():
            assert 3 <= preset["duration"] <= 10, f"Duration for '{mood}' out of range"


class TestModelEndpoints:
    """Tests for model name → Muapi endpoint mapping."""

    def test_auto_resolves_to_default(self):
        assert _get_model_endpoint("auto") == DEFAULT_MODEL

    def test_known_model(self):
        assert _get_model_endpoint("kling-v2.1") == "kling-v2.1-standard-i2v"

    def test_unknown_model_uses_default(self):
        assert _get_model_endpoint("nonexistent-model") == DEFAULT_MODEL

    def test_all_models_have_endpoints(self):
        for name, endpoint in AVAILABLE_MODELS.items():
            assert endpoint, f"Model '{name}' has empty endpoint"


class TestGenerateClip:
    """Tests for single clip generation via Muapi REST API."""

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "")
    def test_no_api_key_returns_none(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        result = generate_clip(img, tmp_path / "clip.mp4", image_url="https://example.com/img.jpg")
        assert result is None

    def test_missing_image_and_no_url_returns_none(self, tmp_path):
        result = generate_clip(
            tmp_path / "nonexistent.png",
            tmp_path / "clip.mp4",
        )
        assert result is None

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "test_key")
    @patch("src.renderers.video_generator.requests.post")
    @patch("src.renderers.video_generator.requests.get")
    def test_successful_generation(self, mock_get, mock_post, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake_image")

        # Mock submit response
        mock_submit_resp = MagicMock()
        mock_submit_resp.status_code = 200
        mock_submit_resp.json.return_value = {"request_id": "req_abc123"}
        mock_post.return_value = mock_submit_resp

        # Mock poll response (completed immediately)
        mock_poll_resp = MagicMock()
        mock_poll_resp.json.return_value = {
            "status": "completed",
            "outputs": ["https://cdn.muapi.ai/video.mp4"],
        }

        # Mock video download
        mock_dl_resp = MagicMock()
        mock_dl_resp.status_code = 200
        mock_dl_resp.content = b"fake_video_data"

        mock_get.side_effect = [mock_poll_resp, mock_dl_resp]

        output = tmp_path / "clip.mp4"
        result = generate_clip(
            img, output, mood="warm",
            image_url="https://example.com/product.jpg",
        )

        assert result == output
        assert output.exists()
        assert output.read_bytes() == b"fake_video_data"

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "test_key")
    @patch("src.renderers.video_generator.requests.post")
    def test_submit_error_returns_none(self, mock_post, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": "Internal server error"}
        mock_post.return_value = mock_resp

        result = generate_clip(
            img, tmp_path / "clip.mp4",
            image_url="https://example.com/img.jpg",
        )
        assert result is None

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "test_key")
    @patch("src.renderers.video_generator.requests.post")
    @patch("src.renderers.video_generator.requests.get")
    def test_job_failure_returns_none(self, mock_get, mock_post, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")

        mock_submit = MagicMock()
        mock_submit.status_code = 200
        mock_submit.json.return_value = {"request_id": "req_fail123"}
        mock_post.return_value = mock_submit

        mock_poll = MagicMock()
        mock_poll.json.return_value = {"status": "failed", "error": "Model error"}
        mock_get.return_value = mock_poll

        result = generate_clip(
            img, tmp_path / "clip.mp4",
            image_url="https://example.com/img.jpg",
        )
        assert result is None

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "test_key")
    @patch("src.renderers.video_generator.requests.post")
    def test_network_error_returns_none(self, mock_post, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        mock_post.side_effect = Exception("Connection refused")

        result = generate_clip(
            img, tmp_path / "clip.mp4",
            image_url="https://example.com/img.jpg",
        )
        assert result is None

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "test_key")
    def test_no_image_url_returns_none(self, tmp_path):
        """Muapi requires a URL — local-only images should fail gracefully."""
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")

        result = generate_clip(img, tmp_path / "clip.mp4")
        assert result is None


class TestGenerateScriptClips:
    """Tests for full script clip generation."""

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "")
    def test_no_api_key_returns_empty(self):
        script = {"script_id": "abc12345", "visual_hints": {"mood": "warm"}}
        result = generate_script_clips(script, [Path("img.png")])
        assert result == []

    def test_no_images_returns_empty(self):
        script = {"script_id": "abc12345"}
        result = generate_script_clips(script, [])
        assert result == []

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "test_key")
    @patch("src.renderers.video_generator.generate_clip")
    @patch("src.renderers.video_generator.OUTPUT_CLIPS_DIR")
    def test_generates_clips_for_each_image(self, mock_dir, mock_gen_clip, tmp_path):
        mock_dir.__truediv__ = lambda self, name: tmp_path / name

        clip1 = tmp_path / "clip_00.mp4"
        clip2 = tmp_path / "clip_01.mp4"
        clip1.write_bytes(b"clip1")
        clip2.write_bytes(b"clip2")
        mock_gen_clip.side_effect = [clip1, clip2]

        img1 = tmp_path / "scene_00.png"
        img2 = tmp_path / "scene_01.png"
        img1.write_bytes(b"img1")
        img2.write_bytes(b"img2")

        script = {
            "script_id": "abc12345",
            "visual_hints": {"mood": "energetic"},
        }

        result = generate_script_clips(
            script, [img1, img2],
            image_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        assert len(result) == 2
        assert mock_gen_clip.call_count == 2

    @patch("src.renderers.video_generator.MUAPI_API_KEY", "test_key")
    @patch("src.renderers.video_generator.generate_clip")
    @patch("src.renderers.video_generator.OUTPUT_CLIPS_DIR")
    def test_partial_failure_continues(self, mock_dir, mock_gen_clip, tmp_path):
        """If some clips fail, the rest should still be generated."""
        mock_dir.__truediv__ = lambda self, name: tmp_path / name

        clip1 = tmp_path / "clip_00.mp4"
        clip1.write_bytes(b"clip1")
        mock_gen_clip.side_effect = [clip1, None]  # Second fails

        img1 = tmp_path / "scene_00.png"
        img2 = tmp_path / "scene_01.png"
        img1.write_bytes(b"img1")
        img2.write_bytes(b"img2")

        script = {"script_id": "abc12345", "visual_hints": {"mood": "calm"}}
        result = generate_script_clips(script, [img1, img2])
        assert len(result) == 1  # Only successful clip
