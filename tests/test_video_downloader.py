"""Tests for src.analyzers.video_downloader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.analyzers.video_downloader import (
    _download_single,
    _get_output_filename,
    _rank_videos,
    _yt_dlp_available,
    download_top_videos,
)


# ── yt-dlp availability ──

@patch("src.analyzers.video_downloader.shutil.which", return_value="/usr/bin/yt-dlp")
def test_yt_dlp_available_true(mock_which):
    """Returns True when yt-dlp is on PATH."""
    assert _yt_dlp_available() is True
    mock_which.assert_called_once_with("yt-dlp")


@patch("src.analyzers.video_downloader.shutil.which", return_value=None)
def test_yt_dlp_available_false(mock_which):
    """Returns False when yt-dlp is not installed."""
    assert _yt_dlp_available() is False


# ── Video ranking ──

def test_rank_videos_sorts_by_engagement():
    """Videos are sorted by engagement rate (likes+shares+comments)/plays."""
    videos = [
        {"webVideoUrl": "https://tiktok.com/1", "id": "1", "playCount": 1000, "diggCount": 10, "shareCount": 5, "commentCount": 5},
        {"webVideoUrl": "https://tiktok.com/2", "id": "2", "playCount": 1000, "diggCount": 100, "shareCount": 50, "commentCount": 50},
        {"webVideoUrl": "https://tiktok.com/3", "id": "3", "playCount": 1000, "diggCount": 50, "shareCount": 20, "commentCount": 10},
    ]
    ranked = _rank_videos(videos)
    assert len(ranked) == 3
    # Highest engagement first: (100+50+50)/1000 = 0.2
    assert ranked[0]["id"] == "2"
    assert ranked[1]["id"] == "3"
    assert ranked[2]["id"] == "1"


def test_rank_videos_filters_missing_urls():
    """Videos without webVideoUrl or videoUrl are excluded."""
    videos = [
        {"id": "1", "playCount": 1000, "diggCount": 50},  # No URL
        {"webVideoUrl": "https://tiktok.com/2", "id": "2", "playCount": 1000, "diggCount": 50, "shareCount": 0, "commentCount": 0},
    ]
    ranked = _rank_videos(videos)
    assert len(ranked) == 1
    assert ranked[0]["id"] == "2"


def test_rank_videos_filters_zero_plays():
    """Videos with zero plays are excluded (avoids division by zero)."""
    videos = [
        {"webVideoUrl": "https://tiktok.com/1", "id": "1", "playCount": 0, "diggCount": 50},
    ]
    ranked = _rank_videos(videos)
    assert len(ranked) == 0


# ── Output filename ──

def test_get_output_filename_with_author_meta():
    """Handles authorMeta.name field from Apify."""
    video = {"id": "abc123", "authorMeta": {"name": "skincare_guru"}}
    assert _get_output_filename(video) == "abc123_skincare_guru.mp4"


def test_get_output_filename_with_flat_author():
    """Handles flat author field from Apify."""
    video = {"id": "def456", "author": "beauty_tips"}
    assert _get_output_filename(video) == "def456_beauty_tips.mp4"


# ── Single download ──

@patch("src.analyzers.video_downloader.subprocess.run")
def test_download_single_success(mock_run, tmp_path):
    """Returns True when yt-dlp succeeds."""
    output = tmp_path / "video.mp4"
    output.write_bytes(b"fake video data")
    mock_run.return_value = MagicMock(returncode=0)
    assert _download_single("https://tiktok.com/v/1", output) is True


@patch("src.analyzers.video_downloader.subprocess.run", side_effect=TimeoutError)
def test_download_single_timeout(mock_run, tmp_path):
    """Returns False when download times out."""
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="yt-dlp", timeout=120)
    output = tmp_path / "video.mp4"
    assert _download_single("https://tiktok.com/v/1", output) is False


# ── Main download function ──

@patch("src.analyzers.video_downloader._yt_dlp_available", return_value=False)
def test_download_top_videos_no_ytdlp(mock_available):
    """Returns empty list when yt-dlp is not installed."""
    result = download_top_videos()
    assert result == []


@patch("src.analyzers.video_downloader._yt_dlp_available", return_value=True)
@patch("src.analyzers.video_downloader.load_pipeline_config", return_value={"analyzer": {}})
@patch("src.analyzers.video_downloader.load_latest", return_value=None)
def test_download_top_videos_no_data(mock_load, mock_config, mock_available):
    """Returns empty list when no trending data exists."""
    result = download_top_videos()
    assert result == []


@patch("src.analyzers.video_downloader._yt_dlp_available", return_value=True)
@patch("src.analyzers.video_downloader.load_pipeline_config", return_value={"analyzer": {"download_top_n": 5}})
@patch("src.analyzers.video_downloader.load_latest")
@patch("src.analyzers.video_downloader._download_single", return_value=True)
@patch("src.analyzers.video_downloader.time.sleep")
def test_download_top_videos_skips_existing(mock_sleep, mock_dl, mock_load, mock_config, mock_available, tmp_path):
    """Skips videos that are already downloaded."""
    mock_load.return_value = [
        {"webVideoUrl": "https://tiktok.com/1", "id": "vid1", "author": "user1",
         "playCount": 1000, "diggCount": 50, "shareCount": 10, "commentCount": 5},
    ]

    # Pre-create the file to simulate already downloaded
    with patch("src.analyzers.video_downloader.VIDEOS_DIR", tmp_path):
        existing = tmp_path / "vid1_user1.mp4"
        existing.write_bytes(b"existing video")

        result = download_top_videos()

    assert len(result) == 1
    # _download_single should NOT have been called since the file exists
    mock_dl.assert_not_called()
