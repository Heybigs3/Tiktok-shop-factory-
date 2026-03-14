"""Tests for src.analyzers.transcriber."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.analyzers.transcriber import extract_audio, transcribe


# ── Audio extraction ──

@patch("src.analyzers.transcriber.shutil.which", return_value=None)
def test_extract_audio_no_ffmpeg(mock_which):
    """Returns None when FFmpeg is not installed."""
    result = extract_audio(Path("test.mp4"))
    assert result is None


@patch("src.analyzers.transcriber.shutil.which", return_value="/usr/bin/ffmpeg")
@patch("src.analyzers.transcriber.subprocess.run")
def test_extract_audio_creates_wav(mock_run, mock_which, tmp_path):
    """Creates a WAV file in the output directory."""
    output_path = tmp_path / "audio.wav"
    # Simulate FFmpeg creating the file
    mock_run.return_value = MagicMock(returncode=0)
    output_path.write_bytes(b"RIFF" + b"\x00" * 100)  # Fake WAV header

    result = extract_audio(Path("test.mp4"), output_path=output_path)
    assert result == output_path


@patch("src.analyzers.transcriber.shutil.which", return_value="/usr/bin/ffmpeg")
@patch("src.analyzers.transcriber.subprocess.run")
def test_extract_audio_returns_none_on_empty(mock_run, mock_which, tmp_path):
    """Returns None when FFmpeg produces no output."""
    output_path = tmp_path / "audio.wav"
    mock_run.return_value = MagicMock(returncode=0)
    # Don't create the file — simulates FFmpeg failure
    result = extract_audio(Path("test.mp4"), output_path=output_path)
    assert result is None


# ── Transcription ──

@patch("src.analyzers.transcriber._whisper_available", return_value=False)
def test_transcribe_no_whisper(mock_available):
    """Returns None and warns when Whisper is not installed."""
    result = transcribe(Path("test.mp4"))
    assert result is None


@patch("src.analyzers.transcriber._whisper_available", return_value=True)
@patch("src.analyzers.transcriber.extract_audio")
def test_transcribe_no_audio(mock_extract, mock_available):
    """Returns None when audio extraction fails."""
    mock_extract.return_value = None
    result = transcribe(Path("test.mp4"))
    assert result is None


@patch("src.analyzers.transcriber.load_pipeline_config", return_value={"analyzer": {"whisper_model": "base"}})
@patch("src.analyzers.transcriber._whisper_available", return_value=True)
@patch("src.analyzers.transcriber.extract_audio")
@patch("src.analyzers.transcriber.subprocess.run")
def test_transcribe_parses_whisper_output(mock_run, mock_extract, mock_available, mock_config, tmp_path):
    """Parses Whisper JSON output into text + segments."""
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"audio data")
    mock_extract.return_value = audio_path

    # Simulate Whisper writing JSON output
    whisper_output = {
        "text": "Stop scrolling if you have acne",
        "segments": [
            {"start": 0.0, "end": 2.5, "text": "Stop scrolling"},
            {"start": 2.5, "end": 5.0, "text": "if you have acne"},
        ],
    }

    mock_run.return_value = MagicMock(returncode=0)

    # Whisper writes to DATA_TRANSCRIPTS_DIR/{stem}.json — mock the path
    with patch("src.analyzers.transcriber.DATA_TRANSCRIPTS_DIR", tmp_path):
        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(whisper_output), encoding="utf-8")

        result = transcribe(Path("test.mp4"))

    assert result is not None
    assert result["text"] == "Stop scrolling if you have acne"
    assert len(result["segments"]) == 2
    assert result["segments"][0]["start"] == 0.0
    assert result["segments"][0]["text"] == "Stop scrolling"
