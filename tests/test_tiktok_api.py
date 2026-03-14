"""Tests for src.publishers.tiktok_api — TikTok Content Posting API client."""

from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from src.publishers.tiktok_api import (
    _headers,
    query_creator_info,
    init_video_post,
    upload_video_file,
    check_post_status,
)


# ── Headers ──

class TestHeaders:

    def test_bearer_format(self):
        h = _headers("tok_abc")
        assert h["Authorization"] == "Bearer tok_abc"

    def test_content_type(self):
        h = _headers("tok_abc")
        assert "application/json" in h["Content-Type"]


# ── query_creator_info ──

class TestQueryCreatorInfo:

    @patch("src.publishers.tiktok_api.requests.post")
    def test_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "error": {"code": "ok"},
                "data": {"creator_nickname": "TestUser", "privacy_level_options": ["PUBLIC_TO_EVERYONE"]},
            },
        )
        result = query_creator_info("tok")
        assert result["creator_nickname"] == "TestUser"

    @patch("src.publishers.tiktok_api.requests.post")
    def test_http_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401, text="Unauthorized")
        assert query_creator_info("tok") is None

    @patch("src.publishers.tiktok_api.requests.post")
    def test_api_error(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"error": {"code": "invalid_token", "message": "bad"}},
        )
        assert query_creator_info("tok") is None


# ── init_video_post ──

class TestInitVideoPost:

    def _make_tmp_video(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 1024)
        return video

    @patch("src.publishers.tiktok_api.requests.post")
    def test_success(self, mock_post, tmp_path):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "error": {"code": "ok"},
                "data": {"publish_id": "pub123", "upload_url": "https://upload.example.com"},
            },
        )
        video = self._make_tmp_video(tmp_path)
        result = init_video_post("tok", video, "My Title", "PUBLIC_TO_EVERYONE")
        assert result["publish_id"] == "pub123"

    @patch("src.publishers.tiktok_api.requests.post")
    def test_payload_has_aigc(self, mock_post, tmp_path):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"error": {"code": "ok"}, "data": {}},
        )
        video = self._make_tmp_video(tmp_path)
        init_video_post("tok", video, "Title", "SELF_ONLY")

        # Inspect the payload sent to TikTok
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["post_info"]["is_aigc"] is True

    @patch("src.publishers.tiktok_api.requests.post")
    def test_title_truncation(self, mock_post, tmp_path):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"error": {"code": "ok"}, "data": {}},
        )
        video = self._make_tmp_video(tmp_path)
        long_title = "A" * 3000
        init_video_post("tok", video, long_title, "SELF_ONLY")

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert len(payload["post_info"]["title"]) == 2200

    @patch("src.publishers.tiktok_api.requests.post")
    def test_http_error(self, mock_post, tmp_path):
        mock_post.return_value = MagicMock(status_code=500, text="Server error")
        video = self._make_tmp_video(tmp_path)
        assert init_video_post("tok", video, "Title", "SELF_ONLY") is None


# ── upload_video_file ──

class TestUploadVideoFile:

    def _make_tmp_video(self, tmp_path, size=2048):
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * size)
        return video

    @patch("src.publishers.tiktok_api.requests.put")
    def test_success(self, mock_put, tmp_path):
        mock_put.return_value = MagicMock(status_code=201)
        video = self._make_tmp_video(tmp_path)
        assert upload_video_file("https://upload.example.com", video) is True

    @patch("src.publishers.tiktok_api.requests.put")
    def test_content_range_header(self, mock_put, tmp_path):
        mock_put.return_value = MagicMock(status_code=200)
        video = self._make_tmp_video(tmp_path, size=5000)
        upload_video_file("https://upload.example.com", video)

        call_kwargs = mock_put.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["Content-Range"] == "bytes 0-4999/5000"

    @patch("src.publishers.tiktok_api.requests.put")
    def test_failure(self, mock_put, tmp_path):
        mock_put.return_value = MagicMock(status_code=403, text="Forbidden")
        video = self._make_tmp_video(tmp_path)
        assert upload_video_file("https://upload.example.com", video) is False


# ── check_post_status ──

class TestCheckPostStatus:

    @patch("src.publishers.tiktok_api.requests.post")
    def test_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "error": {"code": "ok"},
                "data": {"status": "PUBLISH_COMPLETE"},
            },
        )
        result = check_post_status("tok", "pub123")
        assert result["status"] == "PUBLISH_COMPLETE"

    @patch("src.publishers.tiktok_api.requests.post")
    def test_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        assert check_post_status("tok", "pub123") is None
