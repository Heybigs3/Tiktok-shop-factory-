"""Tests for the publish service — post history, ready-to-post, captions, notes."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.dashboard.publish_service import (
    _history_path,
    _notes_path,
    load_post_history,
    _save_post_history,
    record_post,
    get_posts_today,
    get_ready_to_post,
    build_caption,
    load_posting_notes,
    save_posting_notes,
)
from src.utils.config import PROJECT_ROOT
from src.dashboard.accounts import DATA_ACCOUNTS_DIR


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_history(tmp_path):
    """Patch _history_path to use a temp directory."""
    path = tmp_path / "post_history.json"
    with patch("src.dashboard.publish_service._history_path", return_value=path):
        yield path


@pytest.fixture
def tmp_notes(tmp_path):
    """Patch _notes_path to use a temp directory."""
    path = tmp_path / "posting_notes.json"
    with patch("src.dashboard.publish_service._notes_path", return_value=path):
        yield path


def _make_video(filename="vid_trending.mp4", script_id="abc12345", script=None):
    """Create a minimal video dict matching match_scripts_to_videos() output."""
    s = script or {
        "script_id": script_id,
        "hook": "Test hook text",
        "body": "Body text here",
        "cta": "Shop now!",
        "suggested_hashtags": ["fyp", "skincare"],
    }
    return {
        "filename": filename,
        "path": Path(f"output/videos/{filename}"),
        "script_prefix": script_id[:8],
        "source_type": "trending",
        "size_bytes": 5000,
        "size_display": "5 KB",
        "date": "2026-03-12 14:30",
        "mtime": None,
        "mood": "warm",
        "theme": {},
        "script": s,
    }


# ── Path resolution ──────────────────────────────────────────────────────────


class TestHistoryPath:
    def test_history_path_default(self):
        path = _history_path("default")
        assert path == PROJECT_ROOT / "data" / "post_history.json"

    def test_history_path_custom(self):
        path = _history_path("abc123")
        assert path == DATA_ACCOUNTS_DIR / "abc123" / "post_history.json"


class TestNotesPath:
    def test_notes_path_default(self):
        path = _notes_path("default")
        assert path == PROJECT_ROOT / "data" / "posting_notes.json"

    def test_notes_path_custom(self):
        path = _notes_path("abc123")
        assert path == DATA_ACCOUNTS_DIR / "abc123" / "posting_notes.json"


# ── Post history ──────────────────────────────────────────────────────────────


class TestPostHistory:
    def test_load_empty_history(self, tmp_history):
        """Returns [] when no file exists."""
        assert load_post_history("default") == []

    def test_record_post(self, tmp_history):
        """Creates record with correct fields."""
        record = record_post(
            "default",
            video_filename="vid_trending.mp4",
            script_id="abc12345",
            caption_used="Check this out! #fyp",
        )
        assert record["video_filename"] == "vid_trending.mp4"
        assert record["script_id"] == "abc12345"
        assert record["caption_used"] == "Check this out! #fyp"
        assert record["status"] == "posted"
        assert record["post_id"]  # non-empty
        assert record["posted_at"]  # non-empty

        # Verify it was saved
        history = load_post_history("default")
        assert len(history) == 1
        assert history[0]["post_id"] == record["post_id"]

    def test_record_post_skipped(self, tmp_history):
        """Status 'skipped' recorded correctly."""
        record = record_post(
            "default",
            video_filename="bad_vid.mp4",
            status="skipped",
            notes="Low quality",
        )
        assert record["status"] == "skipped"
        assert record["notes"] == "Low quality"

    def test_multiple_records(self, tmp_history):
        """History accumulates."""
        record_post("default", video_filename="vid1.mp4")
        record_post("default", video_filename="vid2.mp4")
        record_post("default", video_filename="vid3.mp4")
        history = load_post_history("default")
        assert len(history) == 3

    def test_record_post_with_queue(self, tmp_history):
        """Updates queue item status to 'posted' when queue_id provided."""
        with patch("src.dashboard.publish_service.update_queue_item") as mock_update:
            record = record_post(
                "default",
                video_filename="vid.mp4",
                queue_id="q123",
                status="posted",
            )
        mock_update.assert_called_once_with("default", "q123", {"status": "posted"})
        assert record["queue_id"] == "q123"

    def test_record_post_no_queue_no_update(self, tmp_history):
        """No queue update when queue_id is empty."""
        with patch("src.dashboard.publish_service.update_queue_item") as mock_update:
            record_post("default", video_filename="vid.mp4")
        mock_update.assert_not_called()


# ── Posts today ──────────────────────────────────────────────────────────────


class TestPostsToday:
    def test_get_posts_today_empty(self, tmp_history):
        """Returns 0 when no history."""
        assert get_posts_today("default") == 0

    def test_get_posts_today(self, tmp_history):
        """Counts only today's posts."""
        today = datetime.now(timezone.utc).date().isoformat()
        history = [
            {"video_filename": "a.mp4", "posted_at": f"{today}T10:00:00+00:00", "status": "posted"},
            {"video_filename": "b.mp4", "posted_at": f"{today}T14:00:00+00:00", "status": "posted"},
            {"video_filename": "c.mp4", "posted_at": "2025-01-01T10:00:00+00:00", "status": "posted"},
        ]
        _save_post_history("default", history)
        assert get_posts_today("default") == 2


# ── Ready to post ────────────────────────────────────────────────────────────


class TestReadyToPost:
    def test_get_ready_to_post(self, tmp_history):
        """Filters out already-posted videos."""
        videos = [_make_video("vid1.mp4", "aaa11111"), _make_video("vid2.mp4", "bbb22222")]
        history = [{"video_filename": "vid1.mp4", "status": "posted", "posted_at": "2026-03-12T10:00:00+00:00"}]
        _save_post_history("default", history)

        with patch("src.dashboard.publish_service.match_scripts_to_videos", return_value=videos), \
             patch("src.dashboard.publish_service.load_queue", return_value=[]):
            ready = get_ready_to_post("default")

        assert len(ready) == 1
        assert ready[0]["filename"] == "vid2.mp4"

    def test_get_ready_to_post_all_posted(self, tmp_history):
        """Returns empty when everything posted."""
        videos = [_make_video("vid1.mp4", "aaa11111")]
        history = [{"video_filename": "vid1.mp4", "status": "posted", "posted_at": "2026-03-12T10:00:00+00:00"}]
        _save_post_history("default", history)

        with patch("src.dashboard.publish_service.match_scripts_to_videos", return_value=videos), \
             patch("src.dashboard.publish_service.load_queue", return_value=[]):
            ready = get_ready_to_post("default")

        assert ready == []

    def test_ready_excludes_skipped(self, tmp_history):
        """Skipped videos still excluded from ready list."""
        videos = [_make_video("vid1.mp4", "aaa11111")]
        history = [{"video_filename": "vid1.mp4", "status": "skipped", "posted_at": "2026-03-12T10:00:00+00:00"}]
        _save_post_history("default", history)

        with patch("src.dashboard.publish_service.match_scripts_to_videos", return_value=videos), \
             patch("src.dashboard.publish_service.load_queue", return_value=[]):
            ready = get_ready_to_post("default")

        assert ready == []


# ── Caption builder ──────────────────────────────────────────────────────────


class TestBuildCaption:
    def test_build_caption_full(self):
        """Hook + CTA + hashtags assembled correctly."""
        script = {
            "hook": "You won't believe this!",
            "cta": "Shop now!",
            "suggested_hashtags": ["fyp", "skincare", "trending"],
        }
        caption = build_caption(script)
        assert "You won't believe this!" in caption
        assert "Shop now!" in caption
        assert "#fyp" in caption
        assert "#skincare" in caption
        assert "#trending" in caption

    def test_build_caption_no_hashtags(self):
        """Handles missing suggested_hashtags."""
        script = {"hook": "Big news!", "cta": "Link in bio"}
        caption = build_caption(script)
        assert "Big news!" in caption
        assert "Link in bio" in caption
        assert "#" not in caption

    def test_build_caption_no_cta(self):
        """Handles missing CTA."""
        script = {"hook": "Watch this!", "suggested_hashtags": ["fyp"]}
        caption = build_caption(script)
        assert "Watch this!" in caption
        assert "#fyp" in caption
        # No CTA line
        assert caption.count("\n\n") == 1  # hook, then hashtags

    def test_build_caption_empty_script(self):
        """Handles completely empty script."""
        assert build_caption({}) == ""

    def test_build_caption_hashtags_with_hash_prefix(self):
        """Doesn't double-hash tags that already have #."""
        script = {"hook": "Hi", "suggested_hashtags": ["#fyp", "test"]}
        caption = build_caption(script)
        assert "#fyp" in caption
        assert "##fyp" not in caption


# ── Posting notes ────────────────────────────────────────────────────────────


class TestPostingNotes:
    def test_load_posting_notes_empty(self, tmp_notes):
        """Returns '' when no file."""
        assert load_posting_notes("default") == ""

    def test_save_and_load_notes(self, tmp_notes):
        """Round-trip persistence."""
        save_posting_notes("default", "Post at 6pm EST. Use David's phone.")
        loaded = load_posting_notes("default")
        assert loaded == "Post at 6pm EST. Use David's phone."

    def test_overwrite_notes(self, tmp_notes):
        """Notes are overwritten, not appended."""
        save_posting_notes("default", "First note")
        save_posting_notes("default", "Updated note")
        assert load_posting_notes("default") == "Updated note"
