"""Tests for src.publishers.tiktok_publisher — interactive CLI functions."""

from pathlib import Path

import pytest

from src.publishers.tiktok_publisher import (
    _find_script_for_video,
    _pick_privacy,
    _pick_interactions,
    _confirm_commercial_content,
    _confirm_post,
)


# ── _find_script_for_video ──

class TestFindScriptForVideo:

    def test_matches_by_id_prefix(self):
        scripts = [
            {"script_id": "a1b2c3d4-5678-9012-3456-abcdef", "hook": "First"},
            {"script_id": "e0f141c6-aaaa-bbbb-cccc-dddddd", "hook": "Second"},
        ]
        video = Path("output/videos/e0f141c6_trending.mp4")
        result = _find_script_for_video(video, scripts)
        assert result is not None
        assert result["hook"] == "Second"

    def test_no_match_returns_none(self):
        scripts = [{"script_id": "a1b2c3d4-5678", "hook": "Only one"}]
        video = Path("output/videos/ffffffff_trending.mp4")
        assert _find_script_for_video(video, scripts) is None

    def test_empty_scripts_list(self):
        video = Path("output/videos/abc12345_trending.mp4")
        assert _find_script_for_video(video, []) is None


# ── _pick_privacy ──

class TestPickPrivacy:

    def test_valid_selection(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "1")
        options = ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]
        assert _pick_privacy(options) == "PUBLIC_TO_EVERYONE"

    def test_returns_correct_option(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "2")
        options = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]
        assert _pick_privacy(options) == "MUTUAL_FOLLOW_FRIENDS"


# ── _pick_interactions ──

class TestPickInteractions:

    def test_all_off_by_default(self, monkeypatch):
        """All interactions off when user declines (N)."""
        monkeypatch.setattr("builtins.input", lambda _: "n")
        creator_info = {}
        result = _pick_interactions(creator_info)
        assert result["disable_comment"] is True
        assert result["disable_duet"] is True
        assert result["disable_stitch"] is True

    def test_enable_comments(self, monkeypatch):
        """Answering 'y' to comments should enable them (disable_comment=False)."""
        responses = iter(["y", "n", "n"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = _pick_interactions({})
        assert result["disable_comment"] is False
        assert result["disable_duet"] is True
        assert result["disable_stitch"] is True

    def test_disabled_by_creator(self, monkeypatch):
        """When the creator has duets disabled, we skip the prompt for that one."""
        responses = iter(["n", "n"])  # Only 2 prompts (duet skipped)
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        creator_info = {"duet_disabled": True}
        result = _pick_interactions(creator_info)
        assert result["disable_duet"] is True


# ── _confirm_commercial_content ──

class TestConfirmCommercialContent:

    def test_not_commercial(self, monkeypatch):
        """Answering 'n' to the first question skips everything."""
        monkeypatch.setattr("builtins.input", lambda _: "n")
        brand, organic = _confirm_commercial_content()
        assert brand is False
        assert organic is False

    def test_brand_content_yes(self, monkeypatch):
        """Commercial=yes, brand deal=yes, own business=no."""
        responses = iter(["y", "y", "n"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        brand, organic = _confirm_commercial_content()
        assert brand is True
        assert organic is False

    def test_brand_organic_yes(self, monkeypatch):
        """Commercial=yes, brand deal=no, own business=yes."""
        responses = iter(["y", "n", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        brand, organic = _confirm_commercial_content()
        assert brand is False
        assert organic is True

    def test_commercial_but_neither_selected_then_cancel(self, monkeypatch):
        """Commercial=yes, both=no, retry=no → falls back to non-commercial."""
        responses = iter(["y", "n", "n", "n"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        brand, organic = _confirm_commercial_content()
        assert brand is False
        assert organic is False


# ── _confirm_post ──

class TestConfirmPost:

    def test_confirm_yes(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "yes")
        assert _confirm_post(Path("test.mp4"), "SELF_ONLY", "My Video") is True

    def test_confirm_no(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "no")
        assert _confirm_post(Path("test.mp4"), "SELF_ONLY", "My Video") is False
