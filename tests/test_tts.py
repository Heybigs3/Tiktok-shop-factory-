"""Tests for src/renderers/tts.py — ElevenLabs TTS integration."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.renderers.tts import (
    get_voice_for_mood,
    generate_speech,
    generate_script_audio,
    get_audio_duration,
    _get_voice_id,
)


class TestGetVoiceForMood:
    """Tests for mood → voice mapping."""

    def test_warm_mood(self):
        voice = get_voice_for_mood("warm")
        assert voice == "Jessica"

    def test_cool_mood(self):
        voice = get_voice_for_mood("cool")
        assert voice == "Eric"

    def test_energetic_mood(self):
        voice = get_voice_for_mood("energetic")
        assert voice == "Liam"

    def test_calm_mood(self):
        voice = get_voice_for_mood("calm")
        assert voice == "River"

    def test_unknown_mood_uses_default(self):
        voice = get_voice_for_mood("mysterious")
        assert voice == "Sarah"

    def test_default_mood(self):
        voice = get_voice_for_mood("default")
        assert voice == "Sarah"


class TestGetVoiceId:
    """Tests for voice name → ID lookup."""

    @patch("src.renderers.tts.requests.get")
    def test_fetches_and_caches_voices(self, mock_get):
        """First call fetches from API, subsequent calls use cache."""
        import src.renderers.tts as tts_module
        tts_module._voice_cache = None  # Reset cache

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "voices": [
                {"name": "Rachel", "voice_id": "rachel_123"},
                {"name": "Adam", "voice_id": "adam_456"},
            ]
        }
        mock_get.return_value = mock_resp

        result = _get_voice_id("Rachel")
        assert result == "rachel_123"

        # Second call should use cache (no new HTTP request)
        result2 = _get_voice_id("Adam")
        assert result2 == "adam_456"
        assert mock_get.call_count == 1  # Only fetched once

        tts_module._voice_cache = None  # Clean up

    @patch("src.renderers.tts.requests.get")
    def test_returns_none_for_unknown_voice(self, mock_get):
        import src.renderers.tts as tts_module
        tts_module._voice_cache = None

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "voices": [{"name": "Rachel", "voice_id": "rachel_123"}]
        }
        mock_get.return_value = mock_resp

        result = _get_voice_id("NonExistent")
        assert result is None

        tts_module._voice_cache = None

    @patch("src.renderers.tts.requests.get")
    def test_api_failure_returns_none(self, mock_get):
        import src.renderers.tts as tts_module
        tts_module._voice_cache = None

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        result = _get_voice_id("Rachel")
        assert result is None

        tts_module._voice_cache = None


class TestGenerateSpeech:
    """Tests for the generate_speech function."""

    def test_empty_text_returns_none(self):
        result = generate_speech("")
        assert result is None

    def test_whitespace_text_returns_none(self):
        result = generate_speech("   ")
        assert result is None

    @patch("src.renderers.tts.ELEVENLABS_API_KEY", "")
    def test_no_api_key_returns_none(self):
        result = generate_speech("Hello world")
        assert result is None

    @patch("src.renderers.tts.ELEVENLABS_API_KEY", "test_key")
    @patch("src.renderers.tts._get_voice_id")
    @patch("src.renderers.tts.requests.post")
    def test_successful_generation(self, mock_post, mock_voice_id, tmp_path):
        mock_voice_id.return_value = "voice_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake_audio_data"
        mock_post.return_value = mock_resp

        output = tmp_path / "test.mp3"
        result = generate_speech("Hello world", output_path=output)

        assert result == output
        assert output.exists()
        assert output.read_bytes() == b"fake_audio_data"

    @patch("src.renderers.tts.ELEVENLABS_API_KEY", "test_key")
    @patch("src.renderers.tts._get_voice_id")
    @patch("src.renderers.tts.requests.post")
    def test_api_error_returns_none(self, mock_post, mock_voice_id):
        mock_voice_id.return_value = "voice_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"detail": {"message": "Unauthorized"}}
        mock_post.return_value = mock_resp

        result = generate_speech("Hello world")
        assert result is None


class TestGenerateScriptAudio:
    """Tests for full script TTS generation."""

    @patch("src.renderers.tts.load_pipeline_config")
    def test_disabled_returns_none(self, mock_config):
        mock_config.return_value = {"tts": {"enabled": False}}
        result = generate_script_audio({"hook": "Test", "body": "Body", "cta": "CTA"})
        assert result is None

    @patch("src.renderers.tts.ELEVENLABS_API_KEY", "")
    @patch("src.renderers.tts.load_pipeline_config")
    def test_no_key_returns_none(self, mock_config):
        mock_config.return_value = {"tts": {"enabled": True}}
        result = generate_script_audio({"hook": "Test", "body": "Body", "cta": "CTA"})
        assert result is None

    @patch("src.renderers.tts.ELEVENLABS_API_KEY", "test_key")
    @patch("src.renderers.tts.generate_speech")
    @patch("src.renderers.tts.get_audio_duration")
    @patch("src.renderers.tts.load_pipeline_config")
    def test_successful_generation(self, mock_config, mock_duration, mock_speech, tmp_path):
        mock_config.return_value = {
            "tts": {
                "enabled": True,
                "voice_map": {"warm": "Rachel", "default": "Rachel"},
            }
        }

        # Create fake audio files
        hook_audio = tmp_path / "hook.mp3"
        body_audio = tmp_path / "body.mp3"
        cta_audio = tmp_path / "cta.mp3"
        for f in (hook_audio, body_audio, cta_audio):
            f.write_bytes(b"fake")

        mock_speech.side_effect = [hook_audio, body_audio, cta_audio]
        mock_duration.side_effect = [2.5, 12.0, 3.0]

        script = {
            "hook": "Did you know?",
            "body": "Here is the secret.",
            "cta": "Follow now",
            "visual_hints": {"mood": "warm"},
            "script_id": "abc12345",
        }

        result = generate_script_audio(script, output_dir=tmp_path)

        assert result is not None
        assert "durations" in result
        assert result["durations"]["hook"] == 2.5
        assert result["durations"]["body"] == 12.0
        assert result["durations"]["cta"] == 3.0

    @patch("src.renderers.tts.ELEVENLABS_API_KEY", "test_key")
    @patch("src.renderers.tts.generate_speech")
    @patch("src.renderers.tts.load_pipeline_config")
    def test_partial_failure_cleans_up(self, mock_config, mock_speech, tmp_path):
        """If one section fails, previously generated audio is cleaned up."""
        mock_config.return_value = {
            "tts": {
                "enabled": True,
                "voice_map": {"default": "Rachel"},
            }
        }

        hook_audio = tmp_path / "hook.mp3"
        hook_audio.write_bytes(b"fake")

        # Hook succeeds, body fails
        mock_speech.side_effect = [hook_audio, None]

        script = {
            "hook": "Test hook",
            "body": "Test body",
            "cta": "Test cta",
            "script_id": "abc12345",
        }

        result = generate_script_audio(script, output_dir=tmp_path)
        assert result is None
        # Hook audio should be cleaned up
        assert not hook_audio.exists()


class TestGetAudioDuration:
    """Tests for audio duration detection."""

    @patch("src.renderers.tts.subprocess.run")
    def test_ffprobe_success(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="12.345\n")
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"x" * 16000)

        duration = get_audio_duration(audio)
        assert duration == 12.345

    @patch("src.renderers.tts.subprocess.run")
    def test_ffprobe_failure_falls_back_to_estimate(self, mock_run, tmp_path):
        mock_run.side_effect = FileNotFoundError()
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"x" * 32000)

        duration = get_audio_duration(audio)
        assert duration == 2.0  # 32000 / 16000
