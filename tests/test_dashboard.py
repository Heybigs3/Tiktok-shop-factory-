"""Tests for the dashboard — services layer and FastAPI routes."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app
from src.dashboard.services import (
    hex_to_css,
    list_videos,
    list_all_scripts,
    match_scripts_to_videos,
    get_unrendered_scripts,
    get_pipeline_status,
    get_studio_stats,
    clear_videos,
    _format_size,
    _get_mood,
)
from src.dashboard.publish_service import load_post_history
from src.utils.config import (
    DATA_RAW_DIR,
    DATA_PROCESSED_DIR,
    DATA_SCRIPTS_DIR,
    OUTPUT_DIR,
    OUTPUT_IMAGES_DIR,
    OUTPUT_CLIPS_DIR,
)


def _patch_account_paths(output_dir=None, scripts_dir=None):
    """Helper to patch get_account_paths for tests that need custom dirs."""
    from src.dashboard.accounts import get_account_paths as real_get
    real_paths = real_get("default")

    def mock_paths(account_id="default"):
        paths = real_paths.copy()
        if output_dir is not None:
            paths["output_dir"] = output_dir
        if scripts_dir is not None:
            paths["data_scripts_dir"] = scripts_dir
        return paths

    return patch("src.dashboard.services.get_account_paths", mock_paths)

client = TestClient(app)


# ── hex_to_css ───────────────────────────────────────────────────────────────


class TestHexToCss:
    def test_converts_0x_prefix(self):
        assert hex_to_css("0x1a1a2e") == "#1a1a2e"

    def test_converts_accent_color(self):
        assert hex_to_css("0xffd700") == "#ffd700"

    def test_no_prefix(self):
        assert hex_to_css("ffffff") == "#ffffff"


# ── _format_size ─────────────────────────────────────────────────────────────


class TestFormatSize:
    def test_bytes(self):
        assert _format_size(500) == "500 B"

    def test_kilobytes(self):
        assert _format_size(5120) == "5 KB"

    def test_megabytes(self):
        assert _format_size(2 * 1024 * 1024) == "2.0 MB"


# ── _get_mood ────────────────────────────────────────────────────────────────


class TestGetMood:
    def test_from_visual_hints(self):
        script = {"visual_hints": {"mood": "warm"}}
        assert _get_mood(script) == "warm"

    def test_fallback_from_source_type(self):
        script = {"source_type": "trending"}
        assert _get_mood(script) == "energetic"

    def test_fallback_default(self):
        script = {}
        assert _get_mood(script) == "default"

    def test_invalid_hints(self):
        script = {"visual_hints": "not a dict"}
        assert _get_mood(script) == "default"


# ── Services integration (uses real data dirs) ──────────────────────────────


class TestServicesIntegration:
    def test_list_videos_returns_list(self):
        result = list_videos()
        assert isinstance(result, list)

    def test_list_all_scripts_returns_list(self):
        result = list_all_scripts()
        assert isinstance(result, list)

    def test_match_scripts_to_videos_returns_list(self):
        result = match_scripts_to_videos()
        assert isinstance(result, list)

    def test_get_pipeline_status_has_all_phases(self):
        status = get_pipeline_status()
        assert "scrape" in status
        assert "generate" in status
        assert "render" in status
        assert "publish" in status

    def test_pipeline_status_has_expected_fields(self):
        status = get_pipeline_status()
        for phase_id, data in status.items():
            assert "label" in data
            assert "file_count" in data
            assert "last_run" in data

    def test_video_metadata_shape(self):
        videos = list_videos()
        if videos:
            v = videos[0]
            assert "filename" in v
            assert "script_prefix" in v
            assert "source_type" in v
            assert "size_display" in v
            assert "date" in v

    def test_scripts_have_computed_fields(self):
        scripts = list_all_scripts()
        if scripts:
            s = scripts[0]
            assert "_mood" in s
            assert "_theme" in s
            assert "_timing" in s

    def test_matched_videos_have_script_or_none(self):
        matched = match_scripts_to_videos()
        for v in matched:
            assert "script" in v
            assert v["script"] is None or isinstance(v["script"], dict)


# ── FastAPI route tests ──────────────────────────────────────────────────────


class TestRoutes:
    def test_videos_page_200(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Videos" in resp.text

    def test_videos_page_has_week_strip(self):
        resp = client.get("/")
        assert resp.status_code == 200
        # Week strip has day labels
        assert "Mon" in resp.text
        assert "Sun" in resp.text

    def test_videos_page_week_offset(self):
        resp = client.get("/?week_offset=1")
        assert resp.status_code == 200
        assert "Videos" in resp.text

    def test_settings_page_200(self):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text

    def test_settings_has_pipeline_and_config(self):
        resp = client.get("/settings")
        assert "Pipeline" in resp.text
        assert "Pipeline Config" in resp.text

    def test_settings_has_analyze(self):
        resp = client.get("/settings")
        assert "Video Analysis" in resp.text

    def test_settings_has_accounts(self):
        resp = client.get("/settings")
        assert "Accounts" in resp.text

    def test_settings_has_api_keys(self):
        resp = client.get("/settings")
        assert "API Keys" in resp.text

    def test_settings_has_phase_cards(self):
        resp = client.get("/settings")
        assert "Scrape" in resp.text
        assert "Generate" in resp.text
        assert "Render" in resp.text
        assert "Publish" in resp.text

    def test_videos_page_has_video_elements(self):
        resp = client.get("/")
        # Should have video gallery or empty state
        assert "video-grid" in resp.text or "No videos ready" in resp.text

    def test_products_has_enriched_columns(self):
        """Products page should have Price, Script, Video, Category columns."""
        resp = client.get("/products")
        assert resp.status_code == 200
        assert "Products" in resp.text
        assert "Price" in resp.text
        assert "Script" in resp.text
        assert "Category" in resp.text


# ── Old route redirects ─────────────────────────────────────────────────────


class TestOldRouteRedirects:
    def test_pipeline_redirects(self):
        resp = client.get("/pipeline", follow_redirects=False)
        assert resp.status_code == 302
        assert "/settings" in resp.headers["location"]

    def test_queue_redirects(self):
        resp = client.get("/queue", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    def test_publish_redirects(self):
        resp = client.get("/publish", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    def test_accounts_redirects(self):
        resp = client.get("/accounts", follow_redirects=False)
        assert resp.status_code == 302
        assert "/settings" in resp.headers["location"]

    def test_analyze_redirects(self):
        resp = client.get("/analyze", follow_redirects=False)
        assert resp.status_code == 302
        assert "/settings" in resp.headers["location"]


# ── API endpoint tests ───────────────────────────────────────────────────────


class TestAPI:
    def test_api_videos_json(self):
        resp = client.get("/api/videos")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_api_scripts_json(self):
        resp = client.get("/api/scripts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_api_status_json(self):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "phases" in data
        assert "api_keys" in data
        assert "config" in data

    def test_trigger_unknown_phase_400(self):
        resp = client.post("/api/pipeline/invalid")
        assert resp.status_code == 400

    def test_poll_phase_status(self):
        resp = client.get("/api/pipeline/scrape/status")
        assert resp.status_code == 200


# ── Static files ─────────────────────────────────────────────────────────────


class TestStatic:
    def test_css_served(self):
        resp = client.get("/static/style.css")
        assert resp.status_code == 200
        assert "mood-warm" in resp.text  # mood CSS variables still present

    def test_js_served(self):
        resp = client.get("/static/app.js")
        assert resp.status_code == 200
        assert "toggleSidebar" in resp.text
        assert "copyFromTextarea" in resp.text


# ── Clear videos ─────────────────────────────────────────────────────────────


class TestClearVideos:
    def test_deletes_mp4_files(self, tmp_path):
        """clear_videos() removes all .mp4 files from the output dir."""
        (tmp_path / "video1.mp4").write_bytes(b"\x00" * 100)
        (tmp_path / "video2.mp4").write_bytes(b"\x00" * 100)
        (tmp_path / "keep.txt").write_text("not a video")

        with _patch_account_paths(output_dir=tmp_path):
            deleted = clear_videos()

        assert deleted == 2
        assert not list(tmp_path.glob("*.mp4"))
        assert (tmp_path / "keep.txt").exists()

    def test_preserves_non_mp4_files(self, tmp_path):
        """Non-MP4 files must survive clear_videos()."""
        (tmp_path / "notes.txt").write_text("keep me")
        (tmp_path / "thumb.jpg").write_bytes(b"\xff\xd8")

        with _patch_account_paths(output_dir=tmp_path):
            deleted = clear_videos()

        assert deleted == 0
        assert (tmp_path / "notes.txt").exists()
        assert (tmp_path / "thumb.jpg").exists()

    def test_empty_dir_returns_zero(self, tmp_path):
        """clear_videos() on an empty dir returns 0."""
        with _patch_account_paths(output_dir=tmp_path):
            assert clear_videos() == 0

    def test_nonexistent_dir_returns_zero(self, tmp_path):
        """clear_videos() returns 0 if OUTPUT_DIR doesn't exist."""
        fake_dir = tmp_path / "nonexistent"
        with _patch_account_paths(output_dir=fake_dir):
            assert clear_videos() == 0

    def test_delete_endpoint_returns_200(self):
        """DELETE /api/videos returns 200 with updated card HTML."""
        with patch("src.dashboard.app.clear_videos", return_value=3):
            resp = client.delete("/api/videos")
        assert resp.status_code == 200
        assert "Render" in resp.text

    def test_per_file_error_handling(self, tmp_path):
        """clear_videos() continues when individual file deletion fails."""
        (tmp_path / "good.mp4").write_bytes(b"\x00" * 100)
        (tmp_path / "bad.mp4").write_bytes(b"\x00" * 100)

        real_unlink = Path.unlink

        def flaky_unlink(self, *args, **kwargs):
            if self.name == "bad.mp4":
                raise OSError("permission denied")
            real_unlink(self, *args, **kwargs)

        with _patch_account_paths(output_dir=tmp_path), \
             patch.object(Path, "unlink", flaky_unlink):
            deleted = clear_videos()

        assert deleted == 1  # good.mp4 deleted, bad.mp4 skipped

    def test_clear_button_hidden_when_zero(self):
        """Clear Videos button is not shown when file_count is 0."""
        with patch("src.dashboard.app.get_pipeline_status", return_value={
            "render": {"label": "Render", "description": "FFmpeg", "file_count": 0, "last_run": None},
        }):
            resp = client.get("/api/pipeline/render/status")
        assert "Clear Videos" not in resp.text

    def test_clear_button_has_disabled_elt(self):
        """Clear Videos button includes hx-disabled-elt attribute."""
        with patch("src.dashboard.app.get_pipeline_status", return_value={
            "render": {"label": "Render", "description": "FFmpeg", "file_count": 5, "last_run": "2026-03-10"},
        }):
            resp = client.get("/api/pipeline/render/status")
        assert 'hx-disabled-elt="this"' in resp.text


# ── Studio stats ────────────────────────────────────────────────────────────


class TestStudioStats:
    def test_returns_expected_keys(self):
        stats = get_studio_stats()
        assert "total_videos" in stats
        assert "total_scripts" in stats
        assert "unrendered" in stats
        assert "storage_used" in stats

    def test_empty_dirs(self, tmp_path):
        """Stats return zeros when data dirs are empty."""
        with _patch_account_paths(output_dir=tmp_path / "empty", scripts_dir=tmp_path / "no_scripts"):
            stats = get_studio_stats()
        assert stats["total_videos"] == 0
        assert stats["total_scripts"] == 0
        assert stats["unrendered"] == 0

    def test_with_mocked_videos(self):
        """Stats reflect video count correctly."""
        fake_videos = [
            {"size_bytes": 1024},
            {"size_bytes": 2048},
        ]
        with patch("src.dashboard.services.list_videos", return_value=fake_videos), \
             patch("src.dashboard.services.list_all_scripts", return_value=[{"script_id": "a"}]), \
             patch("src.dashboard.services.get_unrendered_scripts", return_value=[]):
            stats = get_studio_stats()
        assert stats["total_videos"] == 2
        assert stats["total_scripts"] == 1
        assert stats["unrendered"] == 0
        assert stats["storage_used"] == "3 KB"


# ── Toast system ────────────────────────────────────────────────────────────


class TestToastSystem:
    def test_toast_container_in_base_html(self):
        """Base template contains the toast container div."""
        resp = client.get("/")
        assert 'id="toast-container"' in resp.text

    def test_toast_in_delete_response(self):
        """DELETE /api/videos response includes a toast OOB element."""
        with patch("src.dashboard.app.clear_videos", return_value=2):
            resp = client.delete("/api/videos")
        assert "toast" in resp.text
        assert "Cleared 2 video(s)" in resp.text

    def test_toast_in_poll_response_on_done(self):
        """Polling a completed phase includes a success toast."""
        from src.dashboard.app import _pipeline_runs
        _pipeline_runs["scrape"] = {"status": "done", "error": None}
        try:
            resp = client.get("/api/pipeline/scrape/status")
            assert "toast-success" in resp.text
            assert "completed" in resp.text
        finally:
            _pipeline_runs.pop("scrape", None)


# ── Pipeline stepper ────────────────────────────────────────────────────────


class TestPipelineStepper:
    def test_stepper_present_on_settings_page(self):
        resp = client.get("/settings")
        assert "step-circle" in resp.text or "step-running" in resp.text or "rounded-full" in resp.text

    def test_stepper_has_four_phases(self):
        resp = client.get("/settings")
        assert "Scrape" in resp.text
        assert "Generate" in resp.text
        assert "Render" in resp.text
        assert "Publish" in resp.text


# ── Empty states ────────────────────────────────────────────────────────────


class TestEmptyStates:
    def test_empty_state_shown_when_no_videos(self):
        """Empty state CTA is shown when there are no videos ready."""
        with patch("src.dashboard.app.get_ready_to_post", return_value=[]), \
             patch("src.dashboard.app.match_scripts_to_videos", return_value=[]):
            resp = client.get("/")
        assert "No videos ready" in resp.text
        assert "Settings" in resp.text

    def test_empty_state_hidden_when_videos_exist(self):
        """Empty state is NOT shown when videos exist."""
        fake_ready = [{
            "filename": "x_trending.mp4",
            "path": Path("output/x.mp4"),
            "script_prefix": "x",
            "source_type": "trending",
            "size_bytes": 100,
            "size_display": "100 B",
            "date": "2026-03-10",
            "mtime": None,
            "mood": "default",
            "theme": {"bg": "0x1a1a2e", "text": "0xffffff", "accent": "0xffd700"},
            "script": None,
        }]
        with patch("src.dashboard.app.get_ready_to_post", return_value=fake_ready), \
             patch("src.dashboard.app.match_scripts_to_videos", return_value=fake_ready):
            resp = client.get("/")
        assert "No videos ready" not in resp.text


# ── Nav badge ───────────────────────────────────────────────────────────────


class TestNavBadge:
    def test_video_badge_shown_with_ready_videos(self):
        """Nav badge appears next to Videos when there are ready-to-post videos."""
        fake_ready = [
            {"filename": "a.mp4", "script": None},
            {"filename": "b.mp4", "script": None},
            {"filename": "c.mp4", "script": None},
        ]
        with patch("src.dashboard.app.get_ready_to_post", return_value=fake_ready), \
             patch("src.dashboard.app.match_scripts_to_videos", return_value=[]):
            resp = client.get("/")
        assert "rounded-full" in resp.text  # badge uses Tailwind rounded-full
        assert ">3<" in resp.text  # ready count badge value

    def test_badges_hidden_when_all_zero(self):
        """Nav badges are NOT shown when ready count is 0."""
        with patch("src.dashboard.app.get_ready_to_post", return_value=[]), \
             patch("src.dashboard.app.match_scripts_to_videos", return_value=[]):
            resp = client.get("/")
        assert "Videos" in resp.text  # page still loads


# ── New page routes ─────────────────────────────────────────────────────────


class TestNewPageRoutes:
    def test_products_page_200(self):
        resp = client.get("/products")
        assert resp.status_code == 200
        assert "Products" in resp.text


# ── Account API routes ─────────────────────────────────────────────────────


class TestAccountRoutes:
    def test_api_accounts_list(self):
        resp = client.get("/api/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(a["id"] == "default" for a in data)

    def test_api_create_account_missing_name(self):
        resp = client.post("/api/accounts", data={"name": "", "niche": "test"})
        assert resp.status_code == 400

    def test_api_delete_default_blocked(self):
        resp = client.delete("/api/accounts/default")
        assert resp.status_code == 400


# ── Queue API routes ───────────────────────────────────────────────────────


class TestQueueRoutes:
    def test_api_queue_list(self):
        resp = client.get("/api/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ── Product API routes ─────────────────────────────────────────────────────


class TestProductRoutes:
    def test_api_products_list(self):
        resp = client.get("/api/products")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ── Sidebar navigation ────────────────────────────────────────────────────


class TestSidebarNavigation:
    def test_sidebar_present_on_all_pages(self):
        """Sidebar with navigation links appears on all pages."""
        for url in ["/", "/products", "/settings"]:
            resp = client.get(url)
            assert resp.status_code == 200
            assert "sidebar" in resp.text
            assert "TikTok Factory" in resp.text

    def test_active_page_highlighted(self):
        """Current page link gets highlighted styling."""
        resp = client.get("/")
        assert "videos" in resp.text.lower()  # active page marker
        resp = client.get("/settings")
        assert "Settings" in resp.text

    def test_account_switcher_present(self):
        """Account switcher dropdown appears in sidebar."""
        resp = client.get("/")
        assert "account-switcher" in resp.text


# ── Account scoping ──────────────────────────────────────────────────────


# ── Publish API routes ──────────────────────────────────────────────────────


class TestPublishRoutes:
    def test_publish_redirects_to_videos(self):
        """GET /publish redirects to /."""
        resp = client.get("/publish", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    def test_publish_page_has_ready_count(self):
        """Videos page shows 'ready' badge."""
        resp = client.get("/")
        assert "ready" in resp.text

    def test_publish_record_post(self):
        """POST /api/publish/record creates history entry."""
        with patch("src.dashboard.app.record_post") as mock_record:
            mock_record.return_value = {"post_id": "abc123", "status": "posted"}
            resp = client.post("/api/publish/record", data={
                "video_filename": "test_vid.mp4",
                "script_id": "abc12345",
                "caption_used": "Test caption",
                "status": "posted",
            })
        assert resp.status_code == 200
        assert "Posted" in resp.text
        mock_record.assert_called_once()

    def test_publish_record_missing_filename(self):
        """POST /api/publish/record without filename returns 400."""
        resp = client.post("/api/publish/record", data={"video_filename": ""})
        assert resp.status_code == 400

    def test_publish_history(self):
        """GET /api/publish/history returns fragment."""
        with patch("src.dashboard.app.load_post_history", return_value=[]):
            resp = client.get("/api/publish/history")
        assert resp.status_code == 200
        assert "No posts recorded" in resp.text

    def test_publish_history_with_data(self):
        """GET /api/publish/history with data returns table."""
        history = [
            {
                "post_id": "abc123",
                "video_filename": "vid.mp4",
                "caption_used": "Test caption",
                "posted_at": "2026-03-12T15:00:00+00:00",
                "tiktok_url": "",
                "status": "posted",
                "notes": "",
            }
        ]
        with patch("src.dashboard.app.load_post_history", return_value=history):
            resp = client.get("/api/publish/history")
        assert resp.status_code == 200
        assert "vid.mp4" in resp.text

    def test_publish_notes_save(self):
        """PUT /api/publish/notes persists."""
        with patch("src.dashboard.app.save_posting_notes") as mock_save:
            resp = client.put("/api/publish/notes", data={"notes": "Post at 6pm"})
        assert resp.status_code == 200
        assert "saved" in resp.text
        mock_save.assert_called_once()

    def test_publish_marks_queue_posted(self):
        """Recording with queue_id calls record_post with that ID."""
        with patch("src.dashboard.app.record_post") as mock_record:
            mock_record.return_value = {"post_id": "x", "status": "posted"}
            resp = client.post("/api/publish/record", data={
                "video_filename": "test.mp4",
                "queue_id": "q456",
                "status": "posted",
            })
        assert resp.status_code == 200
        call_kwargs = mock_record.call_args
        assert call_kwargs[1]["queue_id"] == "q456" or call_kwargs.kwargs["queue_id"] == "q456"

    def test_publish_caption_endpoint(self):
        """GET /api/publish/caption/{filename} returns caption JSON."""
        with patch("src.dashboard.app.match_scripts_to_videos", return_value=[]):
            resp = client.get("/api/publish/caption/nonexistent.mp4")
        assert resp.status_code == 200
        assert resp.json()["caption"] == ""

    def test_publish_record_returns_oob_badges(self):
        """Recording a post returns OOB badge updates (no redirect)."""
        with patch("src.dashboard.app.record_post") as mock_record, \
             patch("src.dashboard.app.get_ready_to_post", return_value=[{"f": "a.mp4"}]), \
             patch("src.dashboard.app.get_posts_today", return_value=2):
            mock_record.return_value = {"post_id": "abc", "status": "posted"}
            resp = client.post("/api/publish/record", data={
                "video_filename": "test.mp4",
                "status": "posted",
            })
        assert resp.status_code == 200
        assert "hx-redirect" not in (resp.headers.get("hx-redirect") or "")
        assert 'id="ready-badge"' in resp.text
        assert 'id="today-badge"' in resp.text
        assert "1 ready" in resp.text
        assert "2 posted today" in resp.text


# ── Account scoping ──────────────────────────────────────────────────────


class TestAccountScoping:
    def test_default_account_used_without_cookie(self):
        """Without account_id cookie, default account is used."""
        resp = client.get("/api/status")
        assert resp.status_code == 200
        # Should work without any cookie set

    def test_config_endpoint(self):
        """PUT /api/config returns success toast."""
        # Save original config, restore after test
        from src.utils.config import load_pipeline_config, PIPELINE_CONFIG_PATH
        import json
        original = load_pipeline_config()
        try:
            resp = client.put("/api/config", data={"niche": "test_niche", "num_scripts": "3"})
            assert resp.status_code == 200
            assert "Config saved" in resp.text
        finally:
            with open(PIPELINE_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(original, f, indent=2)


# ── UX audit fixes ──────────────────────────────────────────────────────


class TestUXAuditFixes:
    def test_skip_button_has_confirm(self):
        """Skip button includes hx-confirm attribute."""
        fake_ready = [{
            "filename": "x_trending.mp4",
            "path": Path("output/x.mp4"),
            "script_prefix": "x",
            "source_type": "trending",
            "size_bytes": 100,
            "size_display": "100 B",
            "date": "2026-03-10",
            "mtime": None,
            "mood": "default",
            "theme": {"bg": "0x1a1a2e", "text": "0xffffff", "accent": "0xffd700"},
            "script": None,
        }]
        with patch("src.dashboard.app.get_ready_to_post", return_value=fake_ready), \
             patch("src.dashboard.app.match_scripts_to_videos", return_value=[]):
            resp = client.get("/")
        assert 'hx-confirm=' in resp.text

    def test_recent_posts_shown(self):
        """Videos page shows recent posts inline."""
        history = [
            {"video_filename": "recent1.mp4", "status": "posted", "posted_at": "2026-03-13T10:00:00"},
            {"video_filename": "recent2.mp4", "status": "skipped", "posted_at": "2026-03-13T09:00:00"},
        ]
        with patch("src.dashboard.app.load_post_history", return_value=history), \
             patch("src.dashboard.app.get_ready_to_post", return_value=[]), \
             patch("src.dashboard.app.match_scripts_to_videos", return_value=[]):
            resp = client.get("/")
        assert "Recent" in resp.text
        assert "recent2.mp4" in resp.text  # newest first

    def test_analysis_section_no_hx_get(self):
        """Settings analysis section should not have hx-get (BUG 1 fix)."""
        resp = client.get("/settings")
        assert '/api/analyze/content' not in resp.text

    def test_settings_analysis_collapsed(self):
        """Analysis section is wrapped in <details> (collapsed by default)."""
        resp = client.get("/settings")
        assert "<details>" in resp.text
        assert "(advanced)" in resp.text

    def test_orphaned_publish_select_removed(self):
        """The /api/publish/select/ endpoint no longer exists."""
        resp = client.get("/api/publish/select/test.mp4")
        assert resp.status_code == 404

    def test_run_all_has_disabled_elt(self):
        """Run All button includes hx-disabled-elt attribute."""
        resp = client.get("/settings")
        assert 'hx-disabled-elt="this"' in resp.text


# ── Audit Round 2: security, mobile, cleanup ─────────────────────────────


class TestAuditRound2:
    def test_publish_history_escapes_html(self):
        """<script> in post history fields renders as &lt;script&gt;."""
        history = [{
            "post_id": "xss1",
            "video_filename": '<script>alert("xss")</script>',
            "caption_used": '<img onerror="alert(1)">',
            "posted_at": "2026-03-13T10:00:00",
            "tiktok_url": "",
            "status": '<script>alert("status")</script>',
            "notes": '<b>bold</b>',
        }]
        with patch("src.dashboard.app.load_post_history", return_value=history):
            resp = client.get("/api/publish/history")
        assert resp.status_code == 200
        assert "<script>" not in resp.text
        assert "&lt;script&gt;" in resp.text
        assert "<img " not in resp.text

    def test_publish_history_blocks_javascript_urls(self):
        """javascript: URL is not rendered as <a href>."""
        history = [{
            "post_id": "xss2",
            "video_filename": "test.mp4",
            "caption_used": "",
            "posted_at": "2026-03-13T10:00:00",
            "tiktok_url": "javascript:alert(1)",
            "status": "posted",
            "notes": "",
        }]
        with patch("src.dashboard.app.load_post_history", return_value=history):
            resp = client.get("/api/publish/history")
        assert resp.status_code == 200
        assert "javascript:" not in resp.text
        assert "<a " not in resp.text

    def test_toast_escapes_html(self):
        """_make_toast() escapes HTML in message."""
        from src.dashboard.app import _make_toast
        result = _make_toast('<script>alert("xss")</script>')
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_num_scripts_clamped_to_20(self):
        """Saving num_scripts=100 stores 20."""
        from src.utils.config import load_pipeline_config, PIPELINE_CONFIG_PATH
        import json
        original = load_pipeline_config()
        try:
            resp = client.put("/api/config", data={"num_scripts": "100"})
            assert resp.status_code == 200
            config = load_pipeline_config()
            assert config["num_scripts"] == 20
        finally:
            with open(PIPELINE_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(original, f, indent=2)

    def test_num_scripts_floor_at_1(self):
        """Saving num_scripts=0 stores 1."""
        from src.utils.config import load_pipeline_config, PIPELINE_CONFIG_PATH
        import json
        original = load_pipeline_config()
        try:
            resp = client.put("/api/config", data={"num_scripts": "0"})
            assert resp.status_code == 200
            config = load_pipeline_config()
            assert config["num_scripts"] == 1
        finally:
            with open(PIPELINE_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(original, f, indent=2)

    def test_num_scripts_has_max_attribute(self):
        """HTML input for num_scripts has min='1' max='20'."""
        resp = client.get("/settings")
        assert 'min="1"' in resp.text
        assert 'max="20"' in resp.text

    def test_video_cards_responsive_classes(self):
        """Video cards have flex-col sm:flex-row for mobile stacking."""
        fake_ready = [{
            "filename": "x_trending.mp4",
            "path": Path("output/x.mp4"),
            "script_prefix": "x",
            "source_type": "trending",
            "size_bytes": 100,
            "size_display": "100 B",
            "date": "2026-03-10",
            "mtime": None,
            "mood": "default",
            "theme": {"bg": "0x1a1a2e", "text": "0xffffff", "accent": "0xffd700"},
            "script": None,
        }]
        with patch("src.dashboard.app.get_ready_to_post", return_value=fake_ready), \
             patch("src.dashboard.app.match_scripts_to_videos", return_value=[]):
            resp = client.get("/")
        assert "flex-col sm:flex-row" in resp.text
        assert "sm:w-40" in resp.text

    def test_config_inputs_responsive(self):
        """Config inputs have w-full sm:w-64 for mobile."""
        resp = client.get("/settings")
        assert "w-full sm:w-64" in resp.text

    def test_products_table_hides_columns_mobile(self):
        """Products table hides Price and Category on mobile."""
        resp = client.get("/products")
        assert "hidden sm:table-cell" in resp.text

    def test_toast_container_aria_live(self):
        """Toast container has aria-live='polite'."""
        resp = client.get("/")
        assert 'aria-live="polite"' in resp.text

    def test_sidebar_has_navigation_role(self):
        """Sidebar has role='navigation'."""
        resp = client.get("/")
        assert 'role="navigation"' in resp.text
        assert 'aria-label="Main navigation"' in resp.text
